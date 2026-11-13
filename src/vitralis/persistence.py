#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.127720
Revised: 2026/11/14 00:23:16.023234

The data folder (``%APPDATA%\\Vitralis``) and the drawings kept in it: ``strokes.json``, the strokes of every
screen under the screen's top-left corner (``"x,y"``), and one file per named snapshot in ``snapshots``.

Every file is written whole to a temporary file and then put in place (``os.replace``), so a crash never leaves
half a file. ``strokes.json`` is read once and kept in memory: each stroke drawn saves it, and reading it back
every time would cost more the more is drawn. A damaged entry is skipped and logged, never drawn.
"""

import json
import logging
import os
import re
import secrets
import shutil
from pathlib import Path

from PyQt6.QtCore import QRect

from vitralis.models import Stroke

logger = logging.getLogger("vitralis.persistence")

DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "Vitralis"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STROKES_FILE = DATA_DIR / "strokes.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

PRIMARY_KEY = "0,0"
"""The screen whose strokes the first versions saved as a bare list."""
DAMAGED_SUFFIX = ".damaged"
"""A ``strokes.json`` that can't be read is kept under this name before a new one replaces it."""

_SAFE_NAME = re.compile(r"[^\w\- ]+")

_strokes: dict[str, list] | None = None
"""``strokes.json`` as last read or written; ``None`` until first needed."""


class SnapshotError(Exception):
    """A snapshot couldn't be saved, read or deleted; the message is a one-line reason for the log."""


def write_json_atomic(path: Path, data: object, indent: int | None = 2) -> None:
    """Write ``data`` to ``path`` whole or not at all; ``OSError`` when it can't be written."""
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(json.dumps(data, indent=indent), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as ex:
            logger.warning("couldn't delete %s: %s", temporary, ex)
        raise


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
    if not STROKES_FILE.exists():
        return {}
    try:
        data = json.loads(STROKES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        logger.error("couldn't read %s, starting without drawings: %s", STROKES_FILE, ex)
        _keep_damaged()
        return {}
    if isinstance(data, list):  # the first versions' format: the primary screen's strokes
        return {PRIMARY_KEY: data}
    if isinstance(data, dict):
        return data
    logger.error("%s holds neither screens nor strokes, starting without drawings", STROKES_FILE)
    _keep_damaged()
    return {}


def _keep_damaged() -> None:
    """Copy the unreadable file aside, so the next save doesn't destroy what might still be recovered."""
    kept = STROKES_FILE.with_name(STROKES_FILE.name + DAMAGED_SUFFIX)
    try:
        shutil.copyfile(STROKES_FILE, kept)
        logger.info("kept the unreadable file as %s", kept)
    except OSError as ex:
        logger.warning("couldn't keep the unreadable file as %s: %s", kept, ex)


def _all_strokes() -> dict[str, list]:
    global _strokes
    if _strokes is None:
        _strokes = _read_strokes_file()
    return _strokes


def forget_strokes() -> None:
    """Read ``strokes.json`` again at the next use (for tests, which change the file behind the app's back)."""
    global _strokes
    _strokes = None


def load_strokes_for(geo: QRect) -> list[Stroke]:
    key = screen_key(geo)
    return _parse_strokes(_all_strokes().get(key, []), f"{STROKES_FILE.name} [{key}]")


def save_strokes_for(geo: QRect, strokes: list[Stroke]) -> bool:
    """Save one screen's strokes; whether it worked (a failure is logged and the drawing stays on screen)."""
    data = _all_strokes()
    data[screen_key(geo)] = [s.to_dict() for s in strokes]
    try:
        write_json_atomic(STROKES_FILE, data, indent=None)
    except OSError as ex:
        logger.error("couldn't save the drawings to %s: %s", STROKES_FILE, ex)
        return False
    return True


# --- snapshots ----------------------------------------------------------------------------------------------


def _snapshot_path(name: str) -> Path:
    safe = _SAFE_NAME.sub("_", name).strip()
    return SNAPSHOTS_DIR / f"{safe}.json"


def list_snapshots() -> list[str]:
    """Snapshot names sorted alphabetically; none (and an error in the log) when the folder can't be read."""
    try:
        return sorted(f.stem for f in SNAPSHOTS_DIR.iterdir() if f.suffix == ".json")
    except OSError as ex:
        logger.error("couldn't list the snapshots in %s: %s", SNAPSHOTS_DIR, ex)
        return []


def save_snapshot(name: str, screens: dict[str, list[Stroke]]) -> None:
    """Save a named snapshot of all screens' strokes; ``SnapshotError`` when it can't be written."""
    path = _snapshot_path(name)
    data = {key: [s.to_dict() for s in strokes] for key, strokes in screens.items()}
    try:
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
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
