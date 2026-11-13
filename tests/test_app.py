#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.433417
Revised: 2026/11/13 19:56:13.013912

The overlay session behind the licence: nothing of the overlay exists while locked, it starts once the licence
holds, and locking tears it all down (toolbar with its global hooks, canvases, captures, tray). The real toolbar
installs system-wide keyboard and mouse hooks, so it is replaced by a recording stand-in here.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import logging
import time

import pytest

from tests.conftest import wait_until
from tests.licence.fakes import KEY
from tests.updates.fakes import FakeFeed, MemorySettings
from vitralis import app as app_module
from vitralis.app import Session
from vitralis.licence.gate import LicenceGate
from vitralis.licence.rules import LicenceKind, LicenceStatus
from vitralis.updates.checker import UpdateChecker

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


class FakeSignal:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def emit(self) -> None:
        for slot in self.slots:
            slot()


class FakeTray(FakeWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.messageClicked = FakeSignal()
        self.messages: list[str] = []

    def showMessage(self, title, text, icon=None) -> None:
        self.messages.append(text)


class FakeToolbar(FakeWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_opened = 0

    def open_settings(self) -> None:
        self.settings_opened += 1


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
    monkeypatch.setattr(app_module, "make_tray_icon", lambda app, toolbar: trays.append(FakeTray()) or trays[-1])

    def make(**kwargs) -> Session:
        made = Session(qapp, **kwargs)
        made.trays = trays
        return made

    return make


def of(kind) -> list:
    return [w for w in FakeWidget.made if type(w) is kind]


def test_starting_builds_a_canvas_and_capture_per_screen_a_toolbar_and_a_tray(qapp, session):
    session = session()
    session.start()
    screens = len(qapp.screens())
    assert len(of(FakeCanvas)) == len(of(FakeCapture)) == screens >= 1
    assert all(c.shown for c in of(FakeCanvas))
    assert len(of(FakeToolbar)) == 1 and of(FakeToolbar)[0].shown and session.running
    assert len(session.trays) == 1


def test_starting_twice_builds_once(session):
    session = session()
    session.start()
    session.start()
    assert len(of(FakeToolbar)) == 1


def test_stopping_tears_everything_down(session):
    session = session()
    session.start()
    session.stop()
    assert not session.running and session.canvases == [] and session.captures == []
    assert all(w.closed and w.deleted for w in (*of(FakeToolbar), *of(FakeCanvas), *of(FakeCapture)))
    assert session.trays[0].deleted and not session.trays[0].shown


def test_stopping_when_not_running_does_nothing(session):
    session = session()
    session.stop()
    assert FakeWidget.made == []


def test_the_toolbar_gets_the_gate_for_its_settings(session, make_gate):
    session = session()
    gate = make_gate()
    session.attach(gate)
    session.start()
    assert of(FakeToolbar)[0].kwargs["licence"] is gate


def _gate(licence, checks, session, events) -> LicenceGate:
    gate = LicenceGate(licence, checks, session.start, session.stop, events.prompt)
    session.attach(gate)
    return gate


def test_locked_nothing_of_the_overlay_exists_until_a_key_is_activated(qapp, session, licence, checks, events):
    session = session()
    gate = _gate(licence, checks, session, events)
    gate.begin()
    assert FakeWidget.made == [] and not session.running
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert session.running
    gate.shutdown()


def test_a_licence_ending_while_running_takes_the_overlay_down(qapp, session, activated, checks, events):
    session = session()
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


# --- updates ----------------------------------------------------------------------------------------------------


@pytest.fixture
def updates(qapp):
    checker = UpdateChecker(FakeFeed(), MemorySettings(), "1.3.0")
    yield checker
    checker.stop()


def check(qapp, checker) -> None:
    checker.check_now()
    wait_until(qapp, lambda: not checker.busy)


def test_the_toolbar_gets_the_updater_and_the_checks_start_and_stop_with_the_session(session, updates):
    session = session(updates=updates)
    session.start()
    assert of(FakeToolbar)[0].kwargs["updates"] is updates and updates._timer.isActive()
    session.stop()
    assert not updates._timer.isActive()


def test_a_new_version_is_told_once_in_the_tray(qapp, session, updates):
    session = session(updates=updates)
    session.start()
    check(qapp, updates)
    check(qapp, updates)  # the daily re-check of the same version doesn't nag
    assert session.trays[0].messages == ["Vitralis 1.4.0 is out"]


def test_clicking_the_update_message_opens_settings(qapp, session, updates):
    session = session(updates=updates)
    session.start()
    check(qapp, updates)
    session.trays[0].messageClicked.emit()
    assert of(FakeToolbar)[0].settings_opened == 1


def test_a_start_after_an_update_says_so_once(qapp, session, monkeypatch):
    monkeypatch.setattr(app_module, "app_version", lambda: "1.4.0")
    session = session(updated=True)
    session.start()
    assert session.trays[0].messages == ["Updated to 1.4.0"]
    session.trays[0].messageClicked.emit()  # not about an update on offer: opens nothing
    assert of(FakeToolbar)[0].settings_opened == 0
    session.stop()
    session.start()
    assert session.trays[1].messages == []


def test_no_tray_message_after_the_session_stopped(qapp, session, updates):
    session = session(updates=updates)
    session.start()
    session.stop()
    check(qapp, updates)
    assert session.trays[0].messages == []


def test_the_update_options_are_parsed_and_the_rest_left_to_qt():
    args, rest = app_module.parse_arguments(["vitralis.exe", "--updated", "1.3.0", "--wait-pid", "42", "-style", "x"])
    assert (args.updated, args.wait_pid, rest) == ("1.3.0", 42, ["-style", "x"])
    plain, rest = app_module.parse_arguments(["vitralis.exe"])
    assert (plain.updated, plain.wait_pid, rest) == (None, None, [])


class StopHere(Exception):
    pass


@pytest.fixture
def quiet_main(monkeypatch):
    """``main()`` up to building the QApplication, with logging and the cleanup recorded instead of run."""
    order = []
    monkeypatch.setattr(app_module, "setup_logging", lambda: order.append("logging"))
    monkeypatch.setattr(app_module, "clean_after_updates", lambda current: order.append("clean"))

    def no_app(argv):
        order.append(("app", argv))
        raise StopHere

    monkeypatch.setattr(app_module, "QApplication", no_app)
    monkeypatch.setattr(app_module, "init_icons_dir", lambda: None)
    return order


def test_wait_pid_waits_before_building_anything(monkeypatch, quiet_main):
    monkeypatch.setattr(app_module.sys, "argv", ["vitralis.exe", "--updated", "1.3.0", "--wait-pid", "42"])
    monkeypatch.setattr(app_module, "wait_for_exit", lambda pid, timeout: quiet_main.append(("wait", pid)) or True)
    with pytest.raises(StopHere):
        app_module.main()
    assert quiet_main == ["logging", ("wait", 42), "clean", ("app", ["vitralis.exe"])]


def test_wait_pid_quits_when_the_old_process_never_ends(monkeypatch, quiet_main, caplog):
    monkeypatch.setattr(app_module.sys, "argv", ["vitralis.exe", "--wait-pid", "42"])
    monkeypatch.setattr(app_module, "wait_for_exit", lambda pid, timeout: False)
    with caplog.at_level(logging.ERROR, "vitralis.app"), pytest.raises(SystemExit) as raised:
        app_module.main()
    assert raised.value.code == 1 and quiet_main == ["logging"]
    assert any("pid 42" in r.getMessage() for r in caplog.records)


def test_cleanup_runs_only_in_the_packaged_exe(monkeypatch, tmp_path):
    calls, synced = [], []
    monkeypatch.setattr(app_module, "clean_leftovers", lambda *a: calls.append(a))
    monkeypatch.setattr(app_module, "sync_installed_version", lambda *a: synced.append(a))
    monkeypatch.setattr(app_module, "is_packaged", lambda: False)
    app_module.clean_after_updates("1.4.0")
    assert calls == [] and synced == []
    monkeypatch.setattr(app_module, "is_packaged", lambda: True)
    monkeypatch.setattr(app_module.sys, "executable", str(tmp_path / "vitralis-1.3.0.exe"))
    app_module.clean_after_updates("1.4.0")
    deadline = time.monotonic() + 5
    while not synced and time.monotonic() < deadline:
        time.sleep(0.01)
    running, updates_dir, current = calls[0]
    assert running == tmp_path / "vitralis-1.3.0.exe" and updates_dir.name == "updates" and str(current) == "1.4.0"
    assert synced == [(tmp_path / "vitralis-1.3.0.exe", "1.4.0")]  # the installed-apps entry follows the update
