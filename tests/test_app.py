#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.433417
Revised: 2026/11/14 17:53:27.545670

The overlay session behind the licence: nothing of the overlay exists while locked, it starts once the licence
holds, and locking tears it all down (toolbar with its global hooks, canvases, captures, tray). The real toolbar
installs system-wide keyboard and mouse hooks, so it is replaced by a recording stand-in here.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import contextlib
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
        self.retranslated = 0

    def showMessage(self, title, text, icon=None) -> None:
        self.messages.append(text)

    def retranslate(self) -> None:
        self.retranslated += 1

    def close(self) -> None:
        self.shown = False
        self.closed = self.deleted = True


class FakeToolbar(FakeWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_opened = 0
        self.language_changed = FakeSignal()
        self.placed = None
        self.modes_stopped = 0
        self.synced = 0
        self.fronted = 0

    def show_toolbar(self) -> None:
        self.fronted += 1

    def open_settings(self) -> None:
        self.settings_opened += 1

    def place(self, default) -> None:
        self.placed = default

    def stop_modes(self) -> None:
        self.modes_stopped += 1

    def sync_canvases(self) -> None:
        self.synced += 1

    def raise_(self) -> None:
        self.raised = True

    def activateWindow(self) -> None:
        self.activated = True


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

    sessions = []

    def make(**kwargs) -> Session:
        made = Session(qapp, **kwargs)
        made.trays = trays
        sessions.append(made)
        return made

    yield make
    for made in sessions:  # a session left running would go on answering the app's screen signals
        made.stop()


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


def test_setup_logging_makes_the_data_folder_on_a_first_start(monkeypatch, tmp_path):
    fresh = tmp_path / "Vitralis"
    monkeypatch.setattr(app_module, "LOG_FILE", fresh / "vitralis.log")
    root = logging.getLogger()
    before = list(root.handlers)
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: [h.close() for h in kwargs["handlers"]])
    app_module.setup_logging()
    assert fresh.is_dir() and root.handlers == before


def test_setup_logging_writes_to_the_data_folder(monkeypatch, tmp_path):
    import logging

    monkeypatch.setattr(app_module, "LOG_FILE", tmp_path / "vitralis.log")
    root = logging.getLogger()
    before = list(root.handlers)
    monkeypatch.setattr(root, "handlers", [])
    try:
        app_module.setup_logging()
        logging.getLogger("vitralis.test").info("hello")
        logging.getLogger("httpx").info("HTTP Request: POST https://clavren.breren.com/api/v1/activations/id/checks")
        logging.getLogger("httpx").warning("slow answer")
        for handler in root.handlers:
            handler.flush()
        written = (tmp_path / "vitralis.log").read_text(encoding="utf-8")
        assert "vitralis.test: hello" in written and "httpx: slow answer" in written
        assert "activations" not in written  # the activation id stays out of the log
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = before
        for name in app_module.QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.NOTSET)


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
    assert quiet_main == ["logging", ("wait", 42), ("app", ["vitralis.exe"])]


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


# --- the overlay follows the screens and the toolbar ----------------------------------------------------------


def test_the_toolbar_is_placed_near_the_primary_screens_corner(qapp, session):
    session = session()
    session.start()
    corner = qapp.primaryScreen().geometry().topLeft()
    placed = of(FakeToolbar)[0].placed
    assert (placed.x() - corner.x(), placed.y() - corner.y()) == (app_module.TOOLBAR_MARGIN, app_module.TOOLBAR_MARGIN)


def test_a_capture_leaves_its_mode_through_the_toolbar(session):
    session = session()
    session.start()
    capture = of(FakeCapture)[0]
    capture.kwargs["stop_active"]()
    assert of(FakeToolbar)[0].modes_stopped == 1
    session.stop()
    capture.kwargs["stop_active"]()  # a late click on a closing capture: nothing to stop, nothing raised


def test_a_change_of_screens_rebuilds_the_overlay_under_the_same_toolbar(qapp, session, caplog):
    session = session()
    session.start()
    old = [*of(FakeCanvas), *of(FakeCapture)]
    canvases, captures = session.canvases, session.captures
    with caplog.at_level(logging.INFO, "vitralis.app"):
        qapp.screenAdded.emit(qapp.primaryScreen())
    toolbar = of(FakeToolbar)[0]
    assert all(w.closed and w.deleted for w in old)
    assert session.canvases is canvases and session.captures is captures  # the lists the toolbar holds
    assert len(canvases) == len(captures) == len(qapp.screens()) and not any(w.closed for w in canvases)
    assert len(of(FakeToolbar)) == 1 and not toolbar.closed
    assert (toolbar.modes_stopped, toolbar.synced) == (1, 1)
    assert any("screens changed" in r.getMessage() for r in caplog.records)
    qapp.primaryScreen().geometryChanged.emit(qapp.primaryScreen().geometry())  # a resolution change does too
    assert toolbar.synced == 2 and len(session.canvases) == len(qapp.screens())


def test_screens_changing_after_the_session_stopped_build_nothing(qapp, session):
    session = session()
    session.start()
    session.stop()
    made = len(FakeWidget.made)
    qapp.screenAdded.emit(qapp.primaryScreen())
    qapp.screenRemoved.emit(qapp.primaryScreen())
    qapp.primaryScreen().geometryChanged.emit(qapp.primaryScreen().geometry())
    session._on_screens_changed()
    assert len(FakeWidget.made) == made


def test_another_start_of_vitralis_brings_the_toolbar_to_the_front(session):
    session = session()
    session.show_toolbar()  # locked: no toolbar, nothing happens
    session.start()
    toolbar = of(FakeToolbar)[0]
    toolbar.hide()
    session.show_toolbar()
    assert toolbar.fronted == 1


def test_a_language_change_reaches_the_tray(session):
    session = session()
    session.start()
    of(FakeToolbar)[0].language_changed.emit()
    assert session.trays[0].retranslated == 1


# --- errors nothing caught, signals, the taskbar identity -----------------------------------------------------


def test_an_error_nothing_caught_goes_to_the_log_with_its_traceback(caplog):
    try:
        raise RuntimeError("boom")
    except RuntimeError as ex:
        with caplog.at_level(logging.CRITICAL, "vitralis.app"):
            app_module.log_unhandled(type(ex), ex, ex.__traceback__)
    record = caplog.records[0]
    assert record.levelno == logging.CRITICAL and record.exc_info[1].args == ("boom",)


def test_ctrl_c_is_left_to_python(monkeypatch, caplog):
    seen = []
    monkeypatch.setattr(app_module.sys, "__excepthook__", lambda *args: seen.append(args[0]))
    with caplog.at_level(logging.CRITICAL, "vitralis.app"):
        app_module.log_unhandled(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert seen == [KeyboardInterrupt] and caplog.records == []


def test_an_error_in_a_thread_is_logged_with_the_threads_name(caplog):
    import threading

    args = threading.ExceptHookArgs((ValueError, ValueError("bad"), None, threading.Thread(name="vitralis-worker")))
    with caplog.at_level(logging.CRITICAL, "vitralis.app"):
        app_module.log_unhandled_in_thread(args)
        app_module.log_unhandled_in_thread(threading.ExceptHookArgs((ValueError, ValueError("bad"), None, None)))
    assert "vitralis-worker" in caplog.records[0].getMessage() and "thread ?" in caplog.records[1].getMessage()


def test_the_error_hooks_are_installed(monkeypatch):
    import threading

    monkeypatch.setattr(app_module.sys, "excepthook", None)
    monkeypatch.setattr(threading, "excepthook", None)
    app_module.install_error_logging()
    assert app_module.sys.excepthook is app_module.log_unhandled
    assert threading.excepthook is app_module.log_unhandled_in_thread


def test_a_signal_quits_through_the_clean_shutdown(qapp, monkeypatch, caplog):
    import signal

    quits = []
    monkeypatch.setattr(qapp, "quit", lambda: quits.append(1), raising=False)
    names = [name for name in ("SIGINT", "SIGTERM", "SIGBREAK") if hasattr(signal, name)]
    before = {name: signal.getsignal(getattr(signal, name)) for name in names}
    try:
        timer = app_module.quit_on_signals(qapp)
        assert timer.isActive() and timer.interval() == app_module.SIGNAL_POLL_MS
        with caplog.at_level(logging.INFO, "vitralis.app"):
            for name in names:
                signal.getsignal(getattr(signal, name))(int(getattr(signal, name)), None)
        timer.stop()
        timer.deleteLater()
    finally:
        for name, handler in before.items():
            signal.signal(getattr(signal, name), handler)
    assert quits == [1] * len(names) and len(names) >= 2
    assert sum("quitting" in r.getMessage() for r in caplog.records) == len(names)


def test_the_taskbar_identity_is_set_and_a_refusal_only_logged(monkeypatch, caplog):
    from types import SimpleNamespace

    given = []
    shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=given.append)
    monkeypatch.setattr(app_module.ctypes, "windll", SimpleNamespace(shell32=shell), raising=False)
    app_module.set_app_user_model_id()
    assert given == [app_module.APP_USER_MODEL_ID]

    def refuse(_id):
        raise OSError("refused")

    shell.SetCurrentProcessExplicitAppUserModelID = refuse
    with caplog.at_level(logging.WARNING, "vitralis.app"):
        app_module.set_app_user_model_id()
    assert any("taskbar identity" in r.getMessage() for r in caplog.records)


# --- main ---------------------------------------------------------------------------------------------------


class FakeInstance:
    def __init__(self, order, running: bool) -> None:
        self.order, self.running = order, running
        self.activated = FakeSignal()

    def notify_running(self) -> bool:
        self.order.append("notify")
        return self.running

    def listen(self) -> bool:
        self.order.append("listen")
        return True

    def close(self) -> None:
        self.order.append("instance closed")


@pytest.fixture
def wired_main(qapp, monkeypatch, tmp_path):
    """``main()`` on the test's QApplication with every part it wires replaced by a recorder."""
    from types import SimpleNamespace

    order = []
    record = order.append
    monkeypatch.setattr(app_module.sys, "argv", ["vitralis.exe"])
    monkeypatch.setattr(app_module, "setup_logging", lambda: record("logging"))
    monkeypatch.setattr(app_module, "install_error_logging", lambda: record("error logging"))
    monkeypatch.setattr(app_module, "clean_after_updates", lambda current: record("clean"))
    monkeypatch.setattr(app_module, "set_app_user_model_id", lambda: record("identity"))
    monkeypatch.setattr(app_module, "mark_running", lambda: record("running mark"))
    monkeypatch.setattr(app_module, "init_icons_dir", lambda: record("icons"))
    monkeypatch.setattr(app_module, "QApplication", lambda argv: record("app") or qapp)
    monkeypatch.setattr(app_module, "make_app_icon", lambda: qapp.windowIcon())
    monkeypatch.setattr(qapp, "exec", lambda: record("exec") or 0, raising=False)
    style = qapp.styleSheet()
    timer = SimpleNamespace(stop=lambda: record("timer stopped"))
    monkeypatch.setattr(app_module, "quit_on_signals", lambda app: record("signals") or timer)
    parts = SimpleNamespace(
        licence="licence", checks="checks", close=lambda working: record(("licence closed", working))
    )
    monkeypatch.setattr(app_module, "build_licence", lambda data_dir: record("licence") or parts)
    updates = SimpleNamespace(checker=None, close=lambda: record("updates closed"))
    made = SimpleNamespace(order=order, instance=None, flushed=True)
    monkeypatch.setattr(app_module, "flush_writes", lambda timeout: record(("flush", timeout)) or made.flushed)
    monkeypatch.setattr(app_module, "build_updates", lambda data_dir, settings: record("updates") or updates)

    class Gate:
        def __init__(self, licence, checks, on_unlock, on_lock, make_prompt) -> None:
            order.append(("gate", licence, checks, make_prompt))

        def begin(self) -> None:
            record("begin")

        def show_window(self) -> None:
            record("licence window to the front")

        working = False

        def shutdown(self) -> None:
            record("gate shut down")

    monkeypatch.setattr(app_module, "LicenceGate", Gate)

    class RecordedSession(Session):
        def stop(self) -> None:
            record("session stopped")
            super().stop()

    monkeypatch.setattr(app_module, "Session", RecordedSession)

    def instance(running: bool) -> None:
        made.instance = FakeInstance(order, running)
        monkeypatch.setattr(app_module, "SingleInstance", lambda: made.instance)

    made.use_instance = instance
    yield made
    with contextlib.suppress(TypeError):  # main() quit before connecting its shutdown
        qapp.aboutToQuit.disconnect()
    qapp.setStyleSheet(style)


def test_main_wires_everything_in_order_and_shuts_it_all_down_on_quit(qapp, wired_main):
    wired_main.use_instance(running=False)
    with pytest.raises(SystemExit) as raised:
        app_module.main()
    assert raised.value.code == 0
    gate = ("gate", "licence", "checks", app_module.LicenceWindow)
    assert wired_main.order == [
        "logging",
        "error logging",
        "identity",
        "icons",
        "app",
        "notify",
        "running mark",  # before listening: of two starts at the same moment only one goes on
        "listen",
        "clean",  # after the others: only the one running Vitralis tidies the downloaded updates
        "signals",
        "licence",
        "updates",
        gate,
        "begin",
        "exec",
    ]
    assert len(wired_main.instance.activated.slots) == 1  # a second start shows this one's toolbar
    del wired_main.order[:]
    qapp.aboutToQuit.emit()
    assert wired_main.order == [
        "timer stopped",
        "instance closed",
        "session stopped",
        "gate shut down",
        ("licence closed", False),
        "updates closed",
        ("flush", app_module.FLUSH_SECONDS),  # last: everything that saves has stopped
    ]


def test_another_start_while_locked_brings_the_licence_window_to_the_front(wired_main):
    """Regression guard: with no toolbar yet, starting Vitralis again did nothing anyone could see."""
    wired_main.use_instance(running=False)
    with pytest.raises(SystemExit):
        app_module.main()
    del wired_main.order[:]
    wired_main.instance.activated.emit()
    assert wired_main.order == ["licence window to the front"]


def test_writes_still_running_at_quit_are_said_in_the_log(qapp, wired_main, caplog):
    wired_main.use_instance(running=False)
    wired_main.flushed = False
    with pytest.raises(SystemExit):
        app_module.main()
    with caplog.at_level(logging.WARNING, "vitralis.app"):
        qapp.aboutToQuit.emit()
    assert any("still being written" in r.getMessage() for r in caplog.records)


def test_a_start_at_the_same_moment_as_another_leaves_it_to_that_one(wired_main, monkeypatch, caplog):
    """Regression guard: neither found the other listening yet, so both ran, each writing the same files."""
    from vitralis.single_instance import RunningMark

    wired_main.use_instance(running=False)
    monkeypatch.setattr(app_module, "mark_running", lambda: RunningMark(handle=1, first=False))
    with caplog.at_level(logging.INFO, "vitralis.app"), pytest.raises(SystemExit) as raised:
        app_module.main()
    assert raised.value.code == 0
    assert wired_main.order[-2:] == ["app", "notify"]  # no listening, no tidying, no licence, no overlay
    assert any("another Vitralis" in r.getMessage() for r in caplog.records)


def test_a_first_start_that_made_the_mark_goes_on(wired_main, monkeypatch):
    from vitralis.single_instance import RunningMark

    wired_main.use_instance(running=False)
    monkeypatch.setattr(app_module, "mark_running", lambda: RunningMark(handle=1, first=True))
    with pytest.raises(SystemExit) as raised:
        app_module.main()
    assert raised.value.code == 0 and "listen" in wired_main.order and "exec" in wired_main.order


def test_a_second_start_asks_the_first_to_show_itself_and_builds_nothing(wired_main, caplog):
    wired_main.use_instance(running=True)
    with caplog.at_level(logging.INFO, "vitralis.app"), pytest.raises(SystemExit) as raised:
        app_module.main()
    assert raised.value.code == 0
    assert wired_main.order[-2:] == ["app", "notify"]
    # regression guard: a second start used to delete the update the running Vitralis had downloaded
    assert "clean" not in wired_main.order and "running mark" not in wired_main.order
    assert any("already running" in r.getMessage() for r in caplog.records)
