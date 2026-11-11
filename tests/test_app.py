#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.433417
Revised: 2026/11/11 11:06:55.172910

The overlay session behind the licence: nothing of the overlay exists while locked, it starts once the licence
holds, and locking tears it all down (toolbar with its global hooks, canvases, captures, tray). The real toolbar
installs system-wide keyboard and mouse hooks, so it is replaced by a recording stand-in here.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from tests.conftest import wait_until
from tests.licence.fakes import KEY
from vitralis import app as app_module
from vitralis.app import Session
from vitralis.licence.gate import LicenceGate
from vitralis.licence.rules import LicenceKind, LicenceStatus

pytestmark = pytest.mark.ui


class FakeWidget:
    made: list["FakeWidget"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args, self.kwargs = args, kwargs
        self.shown = self.closed = self.deleted = False
        FakeWidget.made.append(self)

    def load(self, strokes) -> None:
        self.strokes = strokes

    def show(self) -> None:
        self.shown = True

    def hide(self) -> None:
        self.shown = False

    def close(self) -> None:
        self.closed = True

    def deleteLater(self) -> None:
        self.deleted = True

    def setWindowFlags(self, flags) -> None:
        pass

    def windowFlags(self):
        from PyQt6.QtCore import Qt

        return Qt.WindowType.Window

    def setWindowIcon(self, icon) -> None:
        pass

    def move(self, *args) -> None:
        pass


class FakeToolbar(FakeWidget):
    pass


class FakeCanvas(FakeWidget):
    pass


class FakeCapture(FakeWidget):
    pass


@pytest.fixture
def session(qapp, monkeypatch):
    FakeWidget.made = []
    monkeypatch.setattr(app_module, "Toolbar", FakeToolbar)
    monkeypatch.setattr(app_module, "Canvas", FakeCanvas)
    monkeypatch.setattr(app_module, "DrawCapture", FakeCapture)
    monkeypatch.setattr(app_module, "load_strokes_for", lambda geo: [])
    trays = []
    monkeypatch.setattr(app_module, "make_tray_icon", lambda app, toolbar: trays.append(FakeWidget()) or trays[-1])
    made = Session(qapp)
    made.trays = trays
    return made


def of(kind) -> list:
    return [w for w in FakeWidget.made if type(w) is kind]


def test_starting_builds_a_canvas_and_capture_per_screen_a_toolbar_and_a_tray(qapp, session):
    session.start()
    screens = len(qapp.screens())
    assert len(of(FakeCanvas)) == len(of(FakeCapture)) == screens >= 1
    assert all(c.shown for c in of(FakeCanvas))
    assert len(of(FakeToolbar)) == 1 and of(FakeToolbar)[0].shown and session.running
    assert len(session.trays) == 1


def test_starting_twice_builds_once(session):
    session.start()
    session.start()
    assert len(of(FakeToolbar)) == 1


def test_stopping_tears_everything_down(session):
    session.start()
    session.stop()
    assert not session.running and session.canvases == [] and session.captures == []
    assert all(w.closed and w.deleted for w in (*of(FakeToolbar), *of(FakeCanvas), *of(FakeCapture)))
    assert session.trays[0].deleted and not session.trays[0].shown


def test_stopping_when_not_running_does_nothing(session):
    session.stop()
    assert FakeWidget.made == []


def test_the_toolbar_gets_the_gate_for_its_settings(session, make_gate):
    gate = make_gate()
    session.attach(gate)
    session.start()
    assert of(FakeToolbar)[0].kwargs["licence"] is gate


def _gate(licence, checks, session, events) -> LicenceGate:
    gate = LicenceGate(licence, checks, session.start, session.stop, events.prompt)
    session.attach(gate)
    return gate


def test_locked_nothing_of_the_overlay_exists_until_a_key_is_activated(qapp, session, licence, checks, events):
    gate = _gate(licence, checks, session, events)
    gate.begin()
    assert FakeWidget.made == [] and not session.running
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert session.running
    gate.shutdown()


def test_a_licence_ending_while_running_takes_the_overlay_down(qapp, session, activated, checks, events):
    gate = _gate(activated, checks, session, events)
    gate.begin()
    assert session.running
    checks.report(LicenceStatus(LicenceKind.EXPIRED))
    qapp.processEvents()
    assert not session.running and of(FakeToolbar)[0].closed
    gate.shutdown()


def test_setup_logging_writes_to_the_data_folder(monkeypatch, tmp_path):
    import logging

    monkeypatch.setattr(app_module, "LOG_FILE", tmp_path / "vitralis.log")
    root = logging.getLogger()
    before = list(root.handlers)
    monkeypatch.setattr(root, "handlers", [])
    try:
        app_module.setup_logging()
        logging.getLogger("vitralis.test").info("hello")
        for handler in root.handlers:
            handler.flush()
        assert "vitralis.test: hello" in (tmp_path / "vitralis.log").read_text(encoding="utf-8")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = before
