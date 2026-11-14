#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.370504
Revised: 2026/11/14 12:01:48.380512

Shared fixtures for the licence's Qt tests: one offscreen ``QApplication``, a clock, an in-memory Clavren and
store, a gate wired to them with a fake daily checker, and a way to wait for a worker thread's answer.
"""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from tests.licence.fakes import KEY, START, FakeClavren, FakeClock, MemoryLicenceStore, licence_config
from vitralis.icons import init_icons_dir
from vitralis.licence.client import Licence
from vitralis.licence.gate import LicenceGate
from vitralis.licence.rules import LicenceStatus
from vitralis.translations import set_language


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture(scope="session")
def icons():
    """The icon folders, which ``main()`` sets up before building any window."""
    init_icons_dir()


@pytest.fixture(autouse=True)
def own_data_folder(monkeypatch, tmp_path_factory):
    """Every test gets a data folder of its own: none may read or write the real ``%APPDATA%\\Vitralis``."""
    import vitralis.persistence as persistence
    import vitralis.settings as settings

    data = tmp_path_factory.mktemp("vitralis-data")  # not in tmp_path, which tests expect to start empty
    (data / "snapshots").mkdir()
    monkeypatch.setattr(persistence, "STROKES_FILE", data / "strokes.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", data / "snapshots")
    monkeypatch.setattr(settings, "SETTINGS_FILE", data / "settings.json")
    persistence.forget_strokes()
    yield data
    persistence.forget_strokes()  # waits for what the test left on its way to the disk, too


@pytest.fixture(autouse=True)
def english(monkeypatch):
    """English, and no installer language: an installed Vitralis on the test machine changes nothing."""
    monkeypatch.setattr("vitralis.settings.installer_language", lambda: None)
    set_language("English")
    yield
    set_language("English")


@pytest.fixture
def clock():
    return FakeClock(START)


@pytest.fixture
def server(clock):
    return FakeClavren(clock)


@pytest.fixture
def store():
    return MemoryLicenceStore()


@pytest.fixture
def licence(clock, server, store):
    return Licence(licence_config(), store, server, server.crypto(), clock)


class FakeChecks:
    """Stands in for ``LicenceChecks``: no thread; ``report`` plays the checker telling of a change."""

    def __init__(self) -> None:
        self.listeners = []
        self.started = 0
        self.stopped = 0
        self.running = False

    def subscribe(self, listener) -> None:
        self.listeners.append(listener)

    def start(self) -> None:
        self.started += 1

    def stop(self, timeout: float = 20.0) -> None:
        self.stopped += 1

    def report(self, status: LicenceStatus) -> None:
        for listener in self.listeners:
            listener(status)


class FakePrompt:
    """Stands in for ``LicenceWindow``: records what the gate asked it to show."""

    def __init__(self, gate) -> None:
        self.gate = gate
        self.statuses: list[LicenceStatus] = []
        self.errors: list[str] = []
        self.busy: list[bool] = []
        self.dismissed = False

    def show_status(self, status: LicenceStatus) -> None:
        self.statuses.append(status)

    def show_error(self, text: str) -> None:
        self.errors.append(text)

    def set_busy(self, busy: bool) -> None:
        self.busy.append(busy)

    def dismiss(self) -> None:
        self.dismissed = True


class Events:
    """What the gate did: unlocks, locks and the prompts it made."""

    def __init__(self) -> None:
        self.unlocks = 0
        self.locks = 0
        self.prompts: list[FakePrompt] = []

    def unlock(self) -> None:
        self.unlocks += 1

    def lock(self) -> None:
        self.locks += 1

    def prompt(self, gate) -> FakePrompt:
        self.prompts.append(FakePrompt(gate))
        return self.prompts[-1]

    @property
    def last_prompt(self) -> FakePrompt:
        return self.prompts[-1]


@pytest.fixture
def checks():
    return FakeChecks()


@pytest.fixture
def events():
    return Events()


@pytest.fixture
def make_gate(qapp, licence, checks, events):
    made: list[LicenceGate] = []

    def make(prompt=None) -> LicenceGate:
        gate = LicenceGate(licence, checks, events.unlock, events.lock, prompt or events.prompt)
        made.append(gate)
        return gate

    yield make
    for gate in made:
        gate.shutdown()


def wait_until(qapp, condition, timeout: float = 5.0) -> None:
    """Process Qt events until ``condition()`` holds (a worker thread's answer arrives as a queued signal)."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the licence worker")
        qapp.processEvents()
        time.sleep(0.005)


@pytest.fixture
def activated(licence):
    """The licence already activated on this computer, as on every start after the first."""
    assert licence.activate(KEY).licensed
    return licence
