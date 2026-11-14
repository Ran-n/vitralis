#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.047917
Revised: 2026/11/14 18:18:40.009840

One Vitralis per account, over a real local socket with a name of the test's own: the first start listens, a
second finds it and asks it to show itself, and once the first is gone the next start is the first again. And
the named mutex a running Vitralis holds for the uninstaller, under a name of the test's own.
"""

import logging
import secrets
import sys
import threading

import pytest

from tests.conftest import wait_until
from vitralis import single_instance
from vitralis.single_instance import (
    SingleInstance,
    default_name,
    mark_running,
    release_mark,
    wait_for_turn,
)


@pytest.fixture
def name():
    return f"vitralis-test-{secrets.token_hex(6)}"


@pytest.fixture
def first(qapp, name):
    instance = SingleInstance(name)
    yield instance
    instance.close()


def test_the_first_start_finds_nobody_and_listens(first):
    assert first.notify_running() is False
    assert first.listen() is True


def test_a_second_start_finds_the_first_which_is_asked_to_show_itself(qapp, first, name):
    asked = []
    first.activated.connect(lambda: asked.append(1))
    first.listen()
    assert SingleInstance(name).notify_running() is True
    wait_until(qapp, lambda: asked == [1])


def test_once_the_first_is_gone_the_next_start_is_the_first(qapp, first, name):
    first.listen()
    first.close()
    first.close()  # twice is fine
    later = SingleInstance(name)
    assert later.notify_running() is False and later.listen() is True
    later.close()


def test_a_name_that_cant_be_listened_on_is_logged_and_not_fatal(qapp, first, name, monkeypatch, caplog):
    monkeypatch.setattr(single_instance.QLocalServer, "listen", lambda self, name: False)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert first.listen() is False
    assert any(name in r.getMessage() for r in caplog.records)
    first.close()  # nothing to close: still fine


def test_the_default_name_is_per_account(monkeypatch):
    monkeypatch.setattr(single_instance.getpass, "getuser", lambda: "ana")
    assert default_name() == "vitralis-ana"
    assert SingleInstance()._name == "vitralis-ana"


def test_an_unknown_account_still_gets_a_name(monkeypatch, caplog):
    def unknown():
        raise OSError("no user")

    monkeypatch.setattr(single_instance.getpass, "getuser", unknown)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert default_name() == "vitralis-user"
    assert caplog.records


# --- the mark the uninstaller looks for ---------------------------------------------------------------------


def mutex_exists(name: str) -> bool:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenMutexW(0x00100000, False, name)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
    return bool(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="a named mutex is Windows's")
def test_a_running_vitralis_holds_the_mutex_the_uninstaller_looks_for(name):
    import ctypes

    assert not mutex_exists(name)
    mark = mark_running(name)
    assert mark.handle and mark.first and mutex_exists(name)
    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(mark.handle))  # as Windows does when the process ends
    assert not mutex_exists(name)


@pytest.mark.skipif(sys.platform != "win32", reason="a named mutex is Windows's")
def test_only_the_first_to_mark_itself_running_is_the_first(name):
    """Regression guard: two starts at the same moment found nobody listening, and both ran."""
    import ctypes

    close = ctypes.windll.kernel32.CloseHandle
    first, second = mark_running(name), mark_running(name)
    assert first.first and not second.first and second.handle
    close(ctypes.c_void_p(second.handle))
    assert mutex_exists(name)  # the first still holds it
    close(ctypes.c_void_p(first.handle))
    again = mark_running(name)  # once the first has quit, the next start is the first again
    assert again.first
    close(ctypes.c_void_p(again.handle))


def test_a_mark_that_cant_be_made_is_logged_and_not_fatal(monkeypatch, caplog):
    def no_library(*args, **kwargs):
        raise OSError("no kernel32 here")

    monkeypatch.setattr(single_instance.ctypes, "WinDLL", no_library, raising=False)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert mark_running("vitralis-test-none") is None
    assert any("couldn't mark" in r.getMessage() for r in caplog.records)


def test_a_mutex_windows_refuses_is_logged_and_not_fatal(monkeypatch, caplog):
    class Refusing:
        class CreateMutexW:
            argtypes = restype = None

            def __new__(cls, *args):
                return 0  # NULL: Windows made no mutex

    monkeypatch.setattr(single_instance.ctypes, "WinDLL", lambda *args, **kwargs: Refusing, raising=False)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert mark_running("vitralis-test-refused") is None
    assert any("error" in r.getMessage() for r in caplog.records)


# --- a start that finds the mark held ------------------------------------------------------------------------

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="a named mutex is Windows's")


@windows_only
def test_a_start_beside_one_that_begins_to_listen_asks_it_to_show_itself_and_quits(qapp, first, name):
    """Two starts at the same moment: the other made the mark first and listens a moment later."""
    other = mark_running(name)
    mine = mark_running(name)
    assert not mine.first
    shown = []
    first.activated.connect(lambda: shown.append(1))
    first.listen()
    assert wait_for_turn(SingleInstance(name), mine, name, timeout=5, pause=0.01) is False
    wait_until(qapp, lambda: shown == [1])
    release_mark(other)
    release_mark(mine)


@windows_only
def test_a_start_beside_one_that_is_quitting_goes_on_once_it_is_gone(qapp, name):
    """Regression guard: the one quitting no longer listens but still holds the mark; the new start quit too,
    without a word, and Vitralis didn't come up."""
    leaving = mark_running(name)
    mine = mark_running(name)
    assert not mine.first
    threading.Timer(0.3, release_mark, [leaving]).start()
    assert wait_for_turn(SingleInstance(name), mine, name, timeout=10, pause=0.01) is True
    assert mutex_exists(name)  # held by this start now, as the first
    late = mark_running(name)
    assert not late.first
    release_mark(late)


@windows_only
def test_a_start_beside_one_that_is_stuck_goes_on_after_a_while(qapp, name, caplog):
    stuck = mark_running(name)
    mine = mark_running(name)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert wait_for_turn(SingleInstance(name), mine, name, timeout=0.2, pause=0.01) is True
    assert any("neither answers nor quits" in r.getMessage() for r in caplog.records)
    release_mark(stuck)


@windows_only
def test_a_mark_that_cant_be_made_again_doesnt_stop_the_start(qapp, name, monkeypatch):
    other = mark_running(name)
    mine = mark_running(name)
    monkeypatch.setattr(single_instance, "mark_running", lambda name: None)
    assert wait_for_turn(SingleInstance(name), mine, name, timeout=5, pause=0.01) is True
    release_mark(other)
