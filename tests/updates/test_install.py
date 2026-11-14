#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:08.147005
Revised: 2026/11/14 12:01:49.251945

Putting a downloaded release in place (real files in ``tmp_path``, a fake ``Popen``): the swap keeps the path,
every failure puts the old exe back, the writable check, finding a prepared update, cleaning leftovers, and
waiting for a process to end.
"""

import logging
import os
import subprocess
import sys

import pytest
from blake3 import blake3

from vitralis.updates import install
from vitralis.updates.install import (
    RESET_ENVIRONMENT,
    can_write,
    clean_leftovers,
    old_path,
    pending,
    swap_and_start,
    wait_for_exit,
)
from vitralis.updates.rules import SwapFailed, Version

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows processes")
OLD, NEW = b"old exe", b"new exe"


@pytest.fixture
def exes(tmp_path):
    tools = tmp_path / "Tools"
    tools.mkdir()
    running = tools / "vitralis-1.3.0.exe"
    running.write_bytes(OLD)
    updates = tmp_path / "updates"
    updates.mkdir()
    new = updates / "vitralis-1.4.0.exe"
    new.write_bytes(NEW)
    return running, new


class FakePopen:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.fail = fail

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail:
            raise OSError("access denied")


def test_a_swap_keeps_the_path_and_starts_the_new_exe(exes):
    running, new = exes
    popen = FakePopen()
    swap_and_start(running, new, "1.3.0", 4242, popen=popen)
    assert running.read_bytes() == NEW and old_path(running).read_bytes() == OLD and not new.exists()
    args, kwargs = popen.calls[0]
    assert args == [str(running), "--updated", "1.3.0", "--wait-pid", "4242"]
    assert kwargs["env"][RESET_ENVIRONMENT] == "1"
    assert kwargs["creationflags"] == getattr(subprocess, "DETACHED_PROCESS", 0)


def test_popen_failing_puts_the_old_exe_back_and_keeps_the_download(exes):
    running, new = exes
    with pytest.raises(SwapFailed, match="couldn't start"):
        swap_and_start(running, new, "1.3.0", 1, popen=FakePopen(fail=True))
    assert running.read_bytes() == OLD and not old_path(running).exists() and new.read_bytes() == NEW


def test_a_refused_move_leaves_the_original_untouched(exes, monkeypatch):
    running, new = exes

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(install.shutil, "move", refuse)
    with pytest.raises(SwapFailed, match="in place"):
        swap_and_start(running, new, "1.3.0", 1, popen=FakePopen())
    assert running.read_bytes() == OLD and not old_path(running).exists()


def test_a_refused_rename_changes_nothing(exes, monkeypatch):
    running, new = exes

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(install.os, "replace", refuse)
    popen = FakePopen()
    with pytest.raises(SwapFailed, match="aside"):
        swap_and_start(running, new, "1.3.0", 1, popen=popen)
    assert running.read_bytes() == OLD and new.read_bytes() == NEW and popen.calls == []


def test_a_writable_folder_is_writable_and_leaves_no_probe(tmp_path):
    assert can_write(tmp_path) and list(tmp_path.iterdir()) == []


def test_a_folder_that_cant_be_written_is_not_writable(tmp_path, caplog):
    missing = tmp_path / "Program Files" / "Vitralis"  # can't create a file in a folder that isn't there
    with caplog.at_level(logging.WARNING, "vitralis.updates.install"):
        assert not can_write(missing)
    assert caplog.records


def prepare(folder, version: str, body: bytes, checksum: bytes | None = None):
    exe = folder / f"vitralis-{version}.exe"
    exe.write_bytes(body)
    (folder / f"{exe.name}.b3").write_text(f"{blake3(checksum or body).hexdigest()}  {exe.name}\n", encoding="utf-8")
    return exe


def test_pending_finds_the_newest_valid_prepared_exe(tmp_path):
    prepare(tmp_path, "1.4.0", b"a")
    newest = prepare(tmp_path, "1.5.0", b"b")
    assert pending(tmp_path, Version(1, 3, 0)) == newest


def test_pending_ignores_a_damaged_or_not_newer_exe(tmp_path):
    prepare(tmp_path, "1.4.0", b"a", checksum=b"other")
    prepare(tmp_path, "1.3.0", b"c")
    (tmp_path / "vitralis-1.6.0.exe").write_bytes(b"no checksum")
    assert pending(tmp_path, Version(1, 3, 0)) is None
    assert pending(tmp_path / "missing", Version(1, 3, 0)) is None


def test_clean_leftovers_deletes_the_old_exe_and_stale_downloads(exes):
    running, new = exes
    old_path(running).write_bytes(OLD)
    updates = new.parent
    (updates / "vitralis-1.4.0.exe.b3").write_text("x", encoding="utf-8")
    (updates / "vitralis-1.5.0.exe.part").write_bytes(b"half")
    clean_leftovers(running, updates, Version(1, 4, 0))  # running 1.4.0 now
    assert not old_path(running).exists() and not updates.exists()


def test_clean_leftovers_keeps_a_pending_newer_download(exes):
    running, new = exes
    clean_leftovers(running, new.parent, Version(1, 3, 0))
    assert new.exists()


def test_clean_leftovers_logs_a_failure_without_raising(exes, monkeypatch, caplog):
    running, _ = exes
    old_path(running).write_bytes(OLD)
    real_unlink = type(running).unlink

    def refuse(self, *args, **kwargs):
        if self.name.endswith(".old"):
            raise PermissionError("still running")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(running), "unlink", refuse)
    with caplog.at_level(logging.WARNING, "vitralis.updates.install"):
        clean_leftovers(running, running.parent / "missing", Version(1, 4, 0))
    assert old_path(running).exists()
    assert any("next start" in r.getMessage() for r in caplog.records)


@windows_only
def test_wait_for_exit_is_true_for_an_ended_process():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert wait_for_exit(child.pid, 5)


@windows_only
def test_wait_for_exit_is_false_on_timeout():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert not wait_for_exit(child.pid, 0.2)
    finally:
        child.kill()
        child.wait()


@windows_only
def test_wait_for_exit_waits_for_a_process_that_ends_soon():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    assert wait_for_exit(child.pid, 10)
    child.wait()


def test_old_path_sits_beside_the_exe(tmp_path):
    assert old_path(tmp_path / "vitralis-1.3.0.exe") == tmp_path / "vitralis-1.3.0.exe.old"
    assert os.path.dirname(old_path(tmp_path / "a.exe")) == str(tmp_path)
