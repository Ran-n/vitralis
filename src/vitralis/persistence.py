#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.127720
Revised: 2026/11/14 18:18:37.367578

The data folder (``%APPDATA%\\Vitralis``) and the drawings kept in it: ``strokes.json``, the strokes of every
screen under the screen's top-left corner (``"x,y"``), and one file per named snapshot in ``snapshots``.

Every file is written whole to a temporary file and then put in place (``os.replace``), so a crash never leaves
half a file. ``strokes.json`` is read once and kept in memory: each stroke drawn saves it, and reading it back
every time would cost more the more is drawn. A damaged entry is skipped and logged, never drawn.

Nothing here makes the UI wait for the disk while it draws: ``strokes.json`` (and ``settings.json``, through
``write_in_background``) is written by ``BackgroundWriter`` on a thread of its own, and the snapshots are saved,
read and deleted by whoever calls, which the Snapshots window does off the UI thread.
"""

import filecmp
import json
import logging
import os
import re
import secrets
import shutil
import threading
from pathlib import Path

from PyQt6.QtCore import QRect

from vitralis.models import Stroke

logger = logging.getLogger("vitralis.persistence")

DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "Vitralis"
"""Made when something is first written into it, never by importing this module (the tests import it too)."""
STROKES_FILE = DATA_DIR / "strokes.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"

PRIMARY_KEY = "0,0"
"""The screen whose strokes the first versions saved as a bare list."""
DAMAGED_SUFFIX = ".damaged"
"""A ``strokes.json`` that can't be read is kept under this name before a new one replaces it."""

_SAFE_NAME = re.compile(r"[^\w\- ]+")
_RESERVED_NAME = re.compile(r"(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])", re.IGNORECASE)
"""File names Windows keeps for its devices, whatever their extension: no file can be made under them."""
FLUSH_SECONDS = 10.0
"""How long quitting waits for the writes still on their way to the disk."""

_strokes: dict[str, list] | None = None
"""``strokes.json`` as last read or written; ``None`` until first needed."""
_strokes_unreadable = False
"""Whether ``strokes.json`` exists but couldn't be read: it is then never written over, until it can be."""


class SnapshotError(Exception):
    """A snapshot couldn't be saved, read or deleted; the message is a one-line reason for the log."""


def write_json_atomic(path: Path, data: object, indent: int | None = 2) -> None:
    """Write ``data`` to ``path`` whole or not at all; ``OSError`` when it can't be written."""
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(data, indent=indent), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as ex:
            logger.warning("couldn't delete %s: %s", temporary, ex)
        raise


class BackgroundWriter:
    """Writes JSON files off the calling thread, one at a time. Of several versions of a file waiting, only the
    latest is written: each one is the whole file. A failure is logged; the caller already moved on.

    The thread lives only while something waits and isn't a daemon, so Python doesn't exit before the last
    write is on the disk, whichever way the app quits.

    What is handed over must not change afterwards: it is turned into text on the writer's thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._waiting: dict[Path, tuple[object, int | None]] = {}
        self._thread: threading.Thread | None = None

    def write(self, path: Path, data: object, indent: int | None = 2) -> None:
        with self._lock:
            self._waiting[path] = (data, indent)
            if self._thread is None:
                self._thread = threading.Thread(target=self._drain, name="vitralis-writer")
                self._thread.start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._waiting:
                    self._thread = None
                    return
                path = next(iter(self._waiting))
                data, indent = self._waiting.pop(path)
            try:
                write_json_atomic(path, data, indent)
            except OSError as ex:
                logger.error("couldn't save %s: %s", path, ex)
            except Exception:  # data that can't be JSON: a bug, which must not end the writes after it
                logger.exception("couldn't save %s", path)

    def flush(self, timeout: float | None = None) -> bool:
        """Wait until nothing is left to write; whether that happened within ``timeout`` seconds."""
        with self._lock:
            thread = self._thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(timeout)
        return not thread.is_alive()


_writer = BackgroundWriter()


def write_in_background(path: Path, data: object, indent: int | None = 2) -> None:
    """Write ``data`` to ``path`` without waiting for the disk; ``data`` must not change afterwards."""
    _writer.write(path, data, indent)


def flush_writes(timeout: float | None = None) -> bool:
    """Wait for every background write; whether they all ended within ``timeout`` seconds."""
    return _writer.flush(timeout)


def screen_key(geo: QRect) -> str:
    return f"{geo.x()},{geo.y()}"


def _parse_strokes(entries: object, source: str) -> list[Stroke]:
    """The readable strokes of a saved list; the damaged ones are counted in one warning."""
    if not isinstance(entries, list):
        logger.warning("%s: expected a list of strokes, found %s", source, type(entries).__name__)
        return []
    strokes: list[Stroke] = []
    damaged = 0
    for entry in entries:
        try:
            strokes.append(Stroke.from_dict(entry))
        except ValueError as ex:
            damaged += 1
            logger.debug("%s: skipping a stroke: %s", source, ex)
    if damaged:
        logger.warning("%s: skipped %d damaged stroke(s)", source, damaged)
    return strokes


# --- strokes ------------------------------------------------------------------------------------------------


def _read_strokes_file() -> dict[str, list]:
    """What ``strokes.json`` holds. A file whose content is damaged is copied aside and counts as empty; a file
    that can't be read at all (held by another program, no permission) counts as empty too, but is marked
    unreadable: its drawings may be whole, so nothing is written over it until it can be read."""
    global _strokes_unreadable
    _strokes_unreadable = False
    if not STROKES_FILE.exists():
        return {}
    try:
        raw = STROKES_FILE.read_bytes()
    except OSError as ex:
        logger.error("couldn't read %s, starting without drawings and leaving the file as it is: %s", STROKES_FILE, ex)
        _strokes_unreadable = True
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as ex:
        logger.error("%s is damaged, starting without drawings: %s", STROKES_FILE, ex)
        keep_damaged(STROKES_FILE)
        return {}
    if isinstance(data, list):  # the first versions' format: the primary screen's strokes
        return {PRIMARY_KEY: data}
    if isinstance(data, dict):
        return data
    logger.error("%s holds neither screens nor strokes, starting without drawings", STROKES_FILE)
    keep_damaged(STROKES_FILE)
    return {}


def keep_damaged(path: Path) -> None:
    """Copy a file that can't be understood aside, so the next save doesn't destroy what might still be
    recovered from it."""
    kept = path.with_name(path.name + DAMAGED_SUFFIX)
    try:
        number = 1
        while kept.exists():  # an earlier copy is never written over; the same content isn't kept twice
            if filecmp.cmp(path, kept, shallow=False):
                return
            number += 1
            kept = path.with_name(f"{path.name}{DAMAGED_SUFFIX}.{number}")
        shutil.copyfile(path, kept)
        logger.info("kept the unreadable file as %s", kept)
    except OSError as ex:
        logger.warning("couldn't keep the unreadable file as %s: %s", kept, ex)


def strokes_unreadable() -> bool:
    """Whether ``strokes.json`` couldn't be read, so that drawings aren't being saved."""
    return _strokes_unreadable


def _all_strokes() -> dict[str, list]:
    global _strokes
    if _strokes is None:
        _strokes = _read_strokes_file()
    return _strokes


def forget_strokes() -> None:
    """Read ``strokes.json`` again at the next use, once what was saved is in it (for tests, which look at the
    file and change it behind the app's back)."""
    global _strokes, _strokes_unreadable
    flush_writes()
    _strokes = None
    _strokes_unreadable = False


def load_strokes_for(geo: QRect) -> list[Stroke]:
    key = screen_key(geo)
    return _parse_strokes(_all_strokes().get(key, []), f"{STROKES_FILE.name} [{key}]")


def save_strokes_for(geo: QRect, strokes: list[Stroke]) -> None:
    """Save one screen's strokes, without waiting for the disk (a failure is logged and the drawing stays on
    screen). Every save hands the writer a table of its own with this screen's list made anew, and the lists
    of the other screens are only ever replaced, never changed: the writer reads them from its thread."""
    data = _all_strokes()
    if _strokes_unreadable and not _read_again(data):
        logger.error("not saving the drawings: %s still can't be read, and may hold earlier ones", STROKES_FILE)
        return
    data[screen_key(geo)] = [s.to_dict() for s in strokes]
    write_in_background(STROKES_FILE, dict(data), indent=None)


def _read_again(data: dict[str, list]) -> bool:
    """Try the file that couldn't be read at start once more, before the first save since; whether it can be
    written over now. What it holds is copied aside (the screens were drawn on without it) and its other
    screens' drawings are taken into ``data``, so the save keeps them."""
    found = _read_strokes_file()
    if _strokes_unreadable:
        return False
    if found:
        keep_damaged(STROKES_FILE)
    for key, entries in found.items():
        data.setdefault(key, entries)
    return True


# --- snapshots ----------------------------------------------------------------------------------------------


def _snapshot_path(name: str) -> Path:
    safe = _SAFE_NAME.sub("_", name).strip()
    if _RESERVED_NAME.fullmatch(safe):
        safe = f"_{safe}"
    return SNAPSHOTS_DIR / f"{safe}.json"


def list_snapshots() -> list[str]:
    """Snapshot names sorted alphabetically; none (and an error in the log) when the folder can't be read."""
    try:
        return sorted(f.stem for f in SNAPSHOTS_DIR.iterdir() if f.suffix == ".json")
    except FileNotFoundError:  # none was ever saved
        return []
    except OSError as ex:
        logger.error("couldn't list the snapshots in %s: %s", SNAPSHOTS_DIR, ex)
        return []


def save_snapshot(name: str, screens: dict[str, list[Stroke]]) -> None:
    """Save a named snapshot of all screens' strokes; ``SnapshotError`` when it can't be written."""
    path = _snapshot_path(name)
    data = {key: [s.to_dict() for s in strokes] for key, strokes in screens.items()}
    try:
        write_json_atomic(path, data, indent=None)
    except OSError as ex:
        logger.error("couldn't save the snapshot %s: %s", path, ex)
        raise SnapshotError(f"{path}: {ex}") from ex
    logger.info("saved the snapshot %s", path.name)


def load_snapshot(name: str) -> dict[str, list[Stroke]]:
    """A named snapshot as screen key → strokes; ``SnapshotError`` when it is missing or can't be read."""
    path = _snapshot_path(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        logger.error("couldn't read the snapshot %s: %s", path, ex)
        raise SnapshotError(f"{path}: {ex}") from ex
    if not isinstance(data, dict):
        logger.error("the snapshot %s doesn't hold screens", path)
        raise SnapshotError(f"{path}: not a snapshot")
    return {key: _parse_strokes(entries, f"{path.name} [{key}]") for key, entries in data.items()}


def delete_snapshot(name: str) -> None:
    """Delete a named snapshot (one already gone is fine); ``SnapshotError`` when it can't be deleted."""
    path = _snapshot_path(name)
    try:
        path.unlink(missing_ok=True)
    except OSError as ex:
        logger.error("couldn't delete the snapshot %s: %s", path, ex)
        raise SnapshotError(f"{path}: {ex}") from ex
    logger.info("deleted the snapshot %s", path.name)
