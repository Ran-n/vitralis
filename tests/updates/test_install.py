#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:08.147005
Revised: 2026/11/15 14:27:07.434197

Putting a downloaded release in place (real files in ``tmp_path``, a fake ``Popen``, and once a real running
exe): the swap keeps the path, every failure puts the old exe back, the writable check, cleaning leftovers
(only the updater's own downloads, and only old ones), and waiting for a process to end.
"""

import logging
import os
import shutil
import subprocess
import sys
import time

import pytest

from vitralis.updates import install
from vitralis.updates.download import TEMP_PREFIX
from vitralis.updates.install import (
    RESET_ENVIRONMENT,
    can_write,
    clean_leftovers,
    old_path,
    swap_and_start,
    wait_for_exit,
)
from vitralis.updates.rules import SwapFailed

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows processes")
OLD, NEW = b"old exe", b"new exe"


@pytest.fixture
def exes(tmp_path):
    tools = tmp_path / "Tools"
    tools.mkdir()
    running = tools / "vitralis.exe"
    running.write_bytes(OLD)
    updates = tmp_path / "updates"
    updates.mkdir()
    new = updates / (TEMP_PREFIX + "abc.exe")
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


def test_popen_failing_puts_the_old_exe_back(exes):
    running, new = exes
    with pytest.raises(SwapFailed, match="couldn't start"):
        swap_and_start(running, new, "1.3.0", 1, popen=FakePopen(fail=True))
    assert running.read_bytes() == OLD and not old_path(running).exists() and not new.exists()


def test_a_relaunch_of_a_program_that_isnt_there_is_reported(exes):
    running, new = exes

    def missing(args, **kwargs):
        raise FileNotFoundError(2, "The system cannot find the file specified", args[0])

    with pytest.raises(SwapFailed, match="couldn't start the new version"):
        swap_and_start(running, new, "1.3.0", 1, popen=missing)
    assert running.read_bytes() == OLD


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


def aged(path, seconds: float):
    when = time.time() - seconds
    os.utime(path, (when, when))
    return path


def test_old_downloads_and_the_old_exe_go_young_ones_and_other_files_stay(exes):
    running, new = exes
    updates = new.parent
    old_path(running).write_bytes(OLD)
    stale = updates / (TEMP_PREFIX + "stale.exe")
    stale.write_bytes(b"x")
    aged(stale, 41 * 60)
    young = updates / (TEMP_PREFIX + "young.exe")
    young.write_bytes(b"live download in another copy")
    aged(young, 39 * 60)
    mine = updates / "notes.txt"
    mine.write_text("not the updater's")
    aged(mine, 99 * 60)
    folder = updates / (TEMP_PREFIX + "folder")
    folder.mkdir()
    clean_leftovers(running, updates)
    assert not old_path(running).exists() and not stale.exists()
    assert young.exists() and mine.exists() and folder.is_dir() and new.exists()


def test_what_vitralis_1_3_downloaded_is_tidied_once(tmp_path, exes):
    running, _ = exes
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    for name in ("vitralis-1.4.0.exe", "vitralis-1.4.0.exe.b3", "vitralis-1.4.0.exe.part"):
        (legacy / name).write_bytes(b"x")
    clean_leftovers(running, tmp_path / "nowhere", legacy)
    assert not legacy.exists()
    legacy.mkdir()
    (legacy / "keep.txt").write_text("someone's")
    (legacy / "vitralis-1.4.0.exe").write_bytes(b"x")
    clean_leftovers(running, tmp_path / "nowhere", legacy)
    assert [path.name for path in legacy.iterdir()] == ["keep.txt"]


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
        clean_leftovers(running, running.parent / "missing")
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


@windows_only
def test_a_running_exe_is_really_replaced_and_its_old_copy_goes_at_the_next_start(tmp_path):
    """On Windows a running exe can't be overwritten, only moved aside: the swap must work on one that runs."""
    system = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32")
    tools = tmp_path / "Tools"
    tools.mkdir()
    running = tools / "vitralis.exe"
    shutil.copy(os.path.join(system, "ping.exe"), running)
    new = tmp_path / (TEMP_PREFIX + "new.exe")
    shutil.copy(os.path.join(system, "where.exe"), new)
    expected = new.read_bytes()
    child = subprocess.Popen([str(running), "-n", "30", "127.0.0.1"], stdout=subprocess.DEVNULL)
    started = []
    try:
        time.sleep(0.3)
        assert child.poll() is None  # it runs, so its file is locked against writing
        swap_and_start(running, new, "1.3.0", child.pid, popen=lambda args, **kw: started.append(args))
        assert running.read_bytes() == expected and old_path(running).exists()
        assert started == [[str(running), "--updated", "1.3.0", "--wait-pid", str(child.pid)]]
    finally:
        child.kill()
        child.wait()
    clean_leftovers(running, tmp_path / "updates")
    assert not old_path(running).exists()


def test_old_path_sits_beside_the_exe(tmp_path):
    assert old_path(tmp_path / "vitralis.exe") == tmp_path / "vitralis.exe.old"
    assert os.path.dirname(old_path(tmp_path / "a.exe")) == str(tmp_path)


def test_a_failed_put_back_is_logged_not_raised_over_the_real_reason(exes, monkeypatch, caplog):
    running, new = exes
    real = install.os.replace
    calls = []

    def second_fails(src, dst):
        calls.append((src, dst))
        if len(calls) == 2:
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(install.os, "replace", second_fails)
    with caplog.at_level(logging.ERROR, "vitralis.updates.install"), pytest.raises(SwapFailed, match="couldn't start"):
        swap_and_start(running, new, "1.3.0", 1, popen=FakePopen(fail=True))
    assert "couldn't put" in caplog.text


def test_cleanup_logs_what_it_cant_look_at_or_delete_and_goes_on(exes, monkeypatch, caplog, tmp_path):
    running, new = exes
    updates = new.parent
    stale = updates / (TEMP_PREFIX + "stale.exe")
    stale.write_bytes(b"x")
    aged(stale, 50 * 60)
    unreadable = updates / (TEMP_PREFIX + "gone.exe")
    unreadable.write_bytes(b"x")
    real_stat, real_unlink = type(stale).stat, type(stale).unlink

    def stat(self, *args, **kwargs):
        if self.name == unreadable.name:
            raise PermissionError("no")
        return real_stat(self, *args, **kwargs)

    def unlink(self, *args, **kwargs):
        if self.name == stale.name:
            raise PermissionError("in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(stale), "stat", stat)
    monkeypatch.setattr(type(stale), "unlink", unlink)
    with caplog.at_level(logging.WARNING, "vitralis.updates.install"):
        clean_leftovers(running, updates)
    assert stale.exists() and "couldn't look at" in caplog.text and "next start" in caplog.text


def test_cleanup_says_when_a_folder_cant_be_read_or_removed(tmp_path, monkeypatch, caplog, exes):
    running, _ = exes
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setattr(type(legacy), "rmdir", lambda self: (_ for _ in ()).throw(PermissionError("busy")))
    with caplog.at_level(logging.WARNING, "vitralis.updates.install"):
        clean_leftovers(running, tmp_path / "nowhere", legacy)
    assert "couldn't delete" in caplog.text
    real_iterdir = type(legacy).iterdir

    def refuse(self):
        if self == legacy:
            raise PermissionError("no")
        return real_iterdir(self)

    monkeypatch.setattr(type(legacy), "iterdir", refuse)
    caplog.clear()
    with caplog.at_level(logging.WARNING, "vitralis.updates.install"):
        clean_leftovers(running, legacy)
    assert "couldn't look in" in caplog.text
