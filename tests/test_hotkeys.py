#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:10.680882
Revised: 2026/11/14 00:23:22.175971

The two system-wide hook threads. The focus hotkey runs against a stand-in for the ``keyboard`` library (no
real key is hooked): it registers, fires, and is removed on stop, a key the library doesn't know is logged
without ending the app, and stopping works at any moment, even before the thread got going. The wheel hook is
started and stopped for real: it only listens, and must end cleanly however early it is stopped.
"""

import logging
import sys

import pytest

from tests.conftest import wait_until
from vitralis import hotkeys
from vitralis.hotkeys import GlobalHotkeyThread, GlobalMouseWheelThread, is_valid_hotkey


class FakeKeyboard:
    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.added: list[str] = []
        self.removed: list[object] = []
        self.callback = None

    def add_hotkey(self, hotkey, callback):
        if self.refuse:
            raise ValueError(f"unknown key {hotkey!r}")
        self.added.append(hotkey)
        self.callback = callback
        return ("handle", hotkey)

    def remove_hotkey(self, handle) -> None:
        self.removed.append(handle)


@pytest.fixture
def keyboard(monkeypatch):
    fake = FakeKeyboard()
    monkeypatch.setattr(hotkeys, "keyboard", fake)
    return fake


@pytest.mark.parametrize("hotkey", ["f8", "ctrl+q", "ctrl+shift+a", "pgup", "space"])
def test_keys_the_keyboard_library_knows_are_valid(hotkey):
    assert is_valid_hotkey(hotkey)


@pytest.mark.parametrize("hotkey", ["", "ctrl+nosuchkey", "launch (b)"])
def test_unknown_keys_and_no_key_are_not_valid(hotkey):
    assert not is_valid_hotkey(hotkey)


def test_the_hotkey_is_registered_fires_and_is_removed_on_stop(qapp, keyboard):
    thread = GlobalHotkeyThread(hotkey="f9")
    fired = []
    thread.signals.toggle_focus.connect(lambda: fired.append(1))
    thread.start()
    wait_until(qapp, lambda: keyboard.added == ["f9"])
    keyboard.callback()  # the library calls it from its own thread
    wait_until(qapp, lambda: fired == [1])
    thread.stop()
    assert not thread.isRunning() and keyboard.removed == [("handle", "f9")]


def test_stopping_before_the_thread_got_going_still_ends_it(qapp, keyboard):
    """Regression guard: ``stop`` right after ``start`` used to be overtaken by ``run`` and wait for ever."""
    thread = GlobalHotkeyThread(hotkey="f9")
    thread.start()
    thread.stop()
    assert not thread.isRunning() and len(keyboard.removed) == len(keyboard.added)


def test_stopping_a_thread_that_never_started_returns(qapp, keyboard):
    GlobalHotkeyThread(hotkey="f9").stop()
    assert keyboard.added == []


def test_a_key_the_library_refuses_is_logged_and_the_thread_still_stops(qapp, monkeypatch, caplog):
    """Regression guard: an unknown key name used to raise inside the thread, which ends a PyQt app."""
    monkeypatch.setattr(hotkeys, "keyboard", FakeKeyboard(refuse=True))
    thread = GlobalHotkeyThread(hotkey="nosuchkey")
    with caplog.at_level(logging.ERROR, "vitralis.hotkeys"):
        thread.start()
        wait_until(qapp, lambda: bool(caplog.records))
    assert "nosuchkey" in caplog.records[0].getMessage() and thread.isRunning()
    thread.stop()
    assert not thread.isRunning()


def test_no_key_registers_nothing(qapp, keyboard):
    thread = GlobalHotkeyThread(hotkey="")
    thread.start()
    thread.stop()
    assert keyboard.added == [] and keyboard.removed == []


def test_a_hotkey_that_is_already_gone_is_logged_on_stop(qapp, monkeypatch, caplog):
    class Forgetful(FakeKeyboard):
        def remove_hotkey(self, handle) -> None:
            raise KeyError(handle)

    fake = Forgetful()
    monkeypatch.setattr(hotkeys, "keyboard", fake)
    thread = GlobalHotkeyThread(hotkey="f9")
    thread.start()
    wait_until(qapp, lambda: fake.added == ["f9"])
    with caplog.at_level(logging.WARNING, "vitralis.hotkeys"):
        thread.stop()
    assert any("couldn't remove" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(sys.platform != "win32", reason="the wheel hook is Windows's")
def test_the_wheel_hook_installs_and_stops_cleanly(qapp):
    thread = GlobalMouseWheelThread()
    thread.start()
    wait_until(qapp, lambda: thread._hook is not None)
    thread.stop()
    assert not thread.isRunning() and thread._hook is None


@pytest.mark.skipif(sys.platform != "win32", reason="the wheel hook is Windows's")
def test_stopping_the_wheel_hook_at_once_or_before_it_starts_returns(qapp):
    """Regression guard: a WM_QUIT posted before the thread had a message queue was lost, and ``stop`` hung."""
    early = GlobalMouseWheelThread()
    early.start()
    early.stop()
    assert not early.isRunning() and early._hook is None
    GlobalMouseWheelThread().stop()
