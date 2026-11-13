#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:00.709191
Revised: 2026/11/13 09:11:01.167116

Puts a downloaded release in place of the running exe, on Windows. Windows lets a running exe be renamed but
not overwritten or deleted, so the running file moves aside to ``<name>.old``, the new one takes its path
(shortcuts and pinned icons keep working), and the new one starts with ``--wait-pid`` so it only builds
anything once this process has gone. Any failure puts the old exe back: the user is never left without one.
"""

import ctypes
import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from vitralis.updates.download import file_hash
from vitralis.updates.rules import UpdateError, Version, checksum_name, exe_version, parse_b3

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
        raise UpdateError(f"couldn't move {running.name} aside: {ex}") from ex
    try:
        shutil.move(new, running)  # a copy when %APPDATA% and the exe sit on different drives
    except OSError as ex:
        _put_back(old, running)
        raise UpdateError(f"couldn't put the new version in place: {ex}") from ex
    try:
        popen(
            [str(running), "--updated", old_version, "--wait-pid", str(pid)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
            env={**os.environ, RESET_ENVIRONMENT: "1"},
        )
    except Exception as ex:
        try:
            shutil.move(running, new)  # kept, so Install can try again without downloading
        except OSError as move_ex:
            logger.warning("couldn't move the new version back to %s: %s", new, move_ex)
        _put_back(old, running)
        raise UpdateError(f"couldn't start the new version: {ex}") from ex
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


def _keep(path: Path, current: Version | None) -> bool:
    """A downloaded exe (or its checksum) for a version newer than the running one is a pending update."""
    name = path.name.removesuffix(".b3")
    version = exe_version(name)
    return version is not None and (current is None or version > current)


def clean_leftovers(running: Path, updates_dir: Path, current: Version | None) -> None:
    """Delete ``<running>.old`` and everything in ``updates_dir`` that isn't a pending newer version. Failures
    are logged and tried again at the next start; nothing is raised."""
    old = old_path(running)
    try:
        if old.exists():
            old.unlink()
            logger.info("deleted the previous version %s", old)
    except OSError as ex:
        logger.warning("couldn't delete %s (next start tries again): %s", old, ex)
    if not updates_dir.is_dir():
        return
    for path in updates_dir.iterdir():
        if _keep(path, current):
            continue
        try:
            path.unlink()
            logger.info("deleted %s", path)
        except OSError as ex:
            logger.warning("couldn't delete %s (next start tries again): %s", path, ex)
    try:
        if not any(updates_dir.iterdir()):
            updates_dir.rmdir()
    except OSError as ex:
        logger.warning("couldn't delete %s: %s", updates_dir, ex)


def pending(updates_dir: Path, current: Version | None) -> Path | None:
    """The newest prepared exe newer than ``current`` whose kept checksum still matches, else ``None``."""
    if not updates_dir.is_dir():
        return None
    found: list[tuple[Version, Path]] = []
    for path in updates_dir.glob("vitralis-*.exe"):
        version = exe_version(path.name)
        if version is None or (current is not None and version <= current):
            continue
        try:
            expected = parse_b3((updates_dir / checksum_name(version)).read_text(encoding="utf-8"))
            actual = file_hash(path)
        except (OSError, ValueError) as ex:
            logger.warning("ignoring %s: %s", path, ex)
            continue
        if actual != expected:
            logger.warning("ignoring %s: its checksum no longer matches", path)
            continue
        found.append((version, path))
    return max(found)[1] if found else None
