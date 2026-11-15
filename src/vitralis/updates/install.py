#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:00.709191
Revised: 2026/11/15 14:27:02.613256

Puts a downloaded release in place of the running exe, on Windows. Windows lets a running exe be renamed but
not overwritten or deleted, so the running file moves aside to ``<name>.old``, the new one takes its path
(shortcuts and pinned icons keep working), and the new one starts with ``--wait-pid`` so it only builds
anything once this process has gone. Any failure puts the old exe back: the user is never left without one.
"""

import ctypes
import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from vitralis.updates.download import TEMP_PREFIX
from vitralis.updates.rules import SwapFailed

logger = logging.getLogger("vitralis.updates.install")

WRITE_PROBE = ".vitralis-update-test"
SYNCHRONIZE = 0x0010_0000
WAIT_OBJECT_0 = 0
RESET_ENVIRONMENT = "PYINSTALLER_RESET_ENVIRONMENT"
"""Tells PyInstaller's bootloader that the new exe is a separate program, not a child of this one: without it,
the new process would reuse this one's extraction folder, which is deleted when this one quits."""


def old_path(running: Path) -> Path:
    return running.with_name(running.name + ".old")


def can_write(folder: Path) -> bool:
    """Whether files can be created and deleted in ``folder`` (not so under ``C:\\Program Files``)."""
    probe = folder / WRITE_PROBE
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as ex:
        logger.warning("can't update in %s: %s", folder, ex)
        return False
    return True


def swap_and_start(
    running: Path, new: Path, old_version: str, pid: int, popen: Callable[..., object] = subprocess.Popen
) -> None:
    """Move ``running`` aside, put ``new`` at its path and start it; on any failure undo and raise."""
    old = old_path(running)
    try:
        os.replace(running, old)
    except OSError as ex:
        raise SwapFailed(f"couldn't move {running.name} aside: {ex}") from ex
    try:
        shutil.move(new, running)  # a copy when %APPDATA% and the exe sit on different drives
    except OSError as ex:
        _put_back(old, running)
        raise SwapFailed(f"couldn't put the new version in place: {ex}") from ex
    try:
        popen(
            [str(running), "--updated", old_version, "--wait-pid", str(pid)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
            env={**os.environ, RESET_ENVIRONMENT: "1"},
        )
    except Exception as ex:
        _put_back(old, running)
        raise SwapFailed(f"couldn't start the new version: {ex}") from ex
    logger.info("started %s; %s is kept until it runs", running, old.name)


def _put_back(old: Path, running: Path) -> None:
    try:
        if running.exists():
            running.unlink()
        os.replace(old, running)
        logger.info("put %s back after a failed update", running)
    except OSError as ex:
        logger.error("couldn't put %s back from %s: %s", running, old, ex)


def wait_for_exit(pid: int, timeout_s: float) -> bool:
    """Whether process ``pid`` has ended within ``timeout_s`` (true straight away when it is already gone)."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True  # no such process any more
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout_s * 1000)) == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


LEFTOVER_AGE_SECONDS = 40 * 60
"""Older than the longest download (30 minutes) plus ten: a younger file may be another copy's live download."""
LEGACY_NAMES = re.compile(r"vitralis-\d+\.\d+\.\d+\.exe(?:\.b3|\.part)?")
"""What Vitralis 1.3 kept in its old download folder (an exe downloaded ahead of the restart)."""


def _unlink(path: Path) -> None:
    try:
        path.unlink()
        logger.info("deleted %s", path)
    except FileNotFoundError:
        pass
    except OSError as ex:
        logger.warning("couldn't delete %s (the next start tries again): %s", path, ex)


def clean_leftovers(running: Path, updates_dir: Path, legacy_dir: Path | None = None, now: float | None = None) -> None:
    """Delete ``<running>.old``, the downloads in ``updates_dir`` older than ``LEFTOVER_AGE_SECONDS`` and what
    Vitralis 1.3 left in ``legacy_dir``. Other files and folders are left alone; one that can't be deleted is
    logged and tried again at the next start. Nothing is raised."""
    _unlink(old_path(running))
    now = time.time() if now is None else now
    for path in _files(updates_dir):
        if not path.name.startswith(TEMP_PREFIX):
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError as ex:
            logger.warning("couldn't look at %s: %s", path, ex)
            continue
        if age > LEFTOVER_AGE_SECONDS:
            _unlink(path)
    if legacy_dir is not None:
        for path in _files(legacy_dir):
            if LEGACY_NAMES.fullmatch(path.name):
                _unlink(path)
        try:
            if legacy_dir.is_dir() and not any(legacy_dir.iterdir()):
                legacy_dir.rmdir()
        except OSError as ex:
            logger.warning("couldn't delete %s: %s", legacy_dir, ex)


def _files(folder: Path) -> list[Path]:
    """The files in ``folder``; one that can't even be looked at is left out (and logged), not the rest."""
    try:
        entries = list(folder.iterdir()) if folder.is_dir() else []
    except OSError as ex:
        logger.warning("couldn't look in %s: %s", folder, ex)
        return []
    files = []
    for path in entries:
        try:
            if path.is_file():
                files.append(path)
        except OSError as ex:
            logger.warning("couldn't look at %s: %s", path, ex)
    return files
