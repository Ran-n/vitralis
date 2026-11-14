#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.047917
Revised: 2026/11/14 12:01:49.049572

One Vitralis per account, over a real local socket with a name of the test's own: the first start listens, a
second finds it and asks it to show itself, and once the first is gone the next start is the first again. And
the named mutex a running Vitralis holds for the uninstaller, under a name of the test's own.
"""

import logging
import secrets
import sys

import pytest

from tests.conftest import wait_until
from vitralis import single_instance
from vitralis.single_instance import SingleInstance, default_name, mark_running


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
    handle = mark_running(name)
    assert handle and mutex_exists(name)
    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))  # as Windows does when the process ends
    assert not mutex_exists(name)


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
