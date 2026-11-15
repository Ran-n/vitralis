#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 16:56:37.129213
Revised: 2026/11/15 22:34:50.632943

The real toolbar, its windows and one overlay canvas, running as a process of its own for the rendered tests:
``python -m tests.rendered.driver <data folder>``. It reads one JSON command per line on stdin and answers each
with one ``@@{...}`` line on stdout; a command that fails answers ``{"ok": false, "error": ...}``.

Everything is drawn by Windows as in the app, but nothing of the user's is touched: the data folder is the
scratch one given, the licence is an in-memory Clavren's that already holds, updates come from a feed in memory
(nothing goes over the network), the system-wide key and wheel hooks are replaced by inert ones, and the
overlay covers a small rectangle instead of every screen. The clocks and the version shown are fixed, so what
is drawn is the same on every run. The tests click by posting window messages and look with PrintWindow; the
driver never takes clicks as commands. Its windows are cloaked (``hidden.py``), so they never show on the user's
screen unless ``VITRALIS_SHOW_TEST_WINDOW=1``, and every state it answers is searched for the user's name
(``personal.py``).
"""

import json
import os
import sys
from pathlib import Path

os.environ["APPDATA"] = sys.argv[1]  # before vitralis is imported: its data folder is read from this
os.environ.pop("QT_QPA_PLATFORM", None)  # the real screen, not the offscreen one the other tests use
# one pixel per pixel on every screen: with any screen scaled (a 150 % monitor plugged in), Qt draws all text
# unhinted, on the 100 % screens too, and the pictures would follow the monitors instead of the app
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["VITRALIS_RELEASE_TARGET"] = "windows-x86_64"  # drawn as the release build users have
os.environ["LOCALAPPDATA"] = sys.argv[1]  # nothing in the real download folder
for name in ("VITRALIS_UPDATE_SOURCES", "VITRALIS_UPDATE_KEY", "VITRALIS_UPDATE_DIR"):
    os.environ.pop(name, None)

from PyQt6.QtCore import QPoint, QRect, QThread, pyqtSignal
from PyQt6.QtWidgets import QAbstractButton, QApplication, QLabel, QLineEdit, QPushButton, QWidget

from tests.licence.fakes import START, FakeClock, licensed
from tests.rendered import hero
from tests.rendered.hidden import Cloaker, is_cloaked, shown
from tests.rendered.personal import refuse_personal
from tests.updates.fakes import NOON, TARGET, FakeFeed, MemorySettings
from vitralis import toolbar as toolbar_module
from vitralis.app import set_app_user_model_id
from vitralis.canvas import Canvas, DrawCapture
from vitralis.icons import init_icons_dir
from vitralis.licence.client import LicenceChecks
from vitralis.licence.gate import LicenceGate
from vitralis.models import Tool
from vitralis.persistence import flush_writes, forget_strokes, list_snapshots, load_strokes_for
from vitralis.settings import SettingsManager
from vitralis.toolbar import Toolbar
from vitralis.translations import set_language
from vitralis.tray import make_app_icon
from vitralis.updates.checker import UpdateChecker

CANVAS = QRect(420, 80, 360, 240)
TOOLBAR_AT = QPoint(60, 80)
CLOSE = "✕"
VERSION = "1.3.0"
"""The version every run says it is, so the baselines outlive a version bump; the feed offers 1.4.0."""


class _NoSignal:
    def connect(self, slot) -> None:
        """Nothing will ever be sent."""


class InertThread:
    """Stands in for the system-wide key and wheel hooks: installs nothing, so the user's keys stay theirs."""

    def __init__(self, *args, **kwargs) -> None:
        self.signals = self
        self.toggle_focus = self.scrolled = _NoSignal()
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class _Lines(QThread):
    """Stdin, read off the UI thread (a pipe can't be watched by Qt on Windows)."""

    line = pyqtSignal(str)

    def run(self) -> None:
        for text in sys.stdin:
            self.line.emit(text)
        self.line.emit('{"do": "quit"}')  # the tests went away: don't stay behind


class Driver:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.canvas: Canvas | None = None
        self.capture: DrawCapture | None = None
        self.bar: Toolbar | None = None
        licence = licensed(FakeClock(START))
        self.gate = LicenceGate(licence, LicenceChecks(licence), lambda: None, lambda: None, self._no_prompt)
        self.gate.begin()
        self.updates = self._updates()
        self.build()

    @staticmethod
    def _updates() -> UpdateChecker:
        """Updates from a feed in memory that offers 1.4.0, not yet asked."""
        return UpdateChecker(FakeFeed(), MemorySettings(), VERSION, TARGET, clock=lambda: NOON)

    @staticmethod
    def _no_prompt(gate: LicenceGate):
        raise AssertionError("the stand-in licence holds: its window is never asked for")

    def build(self) -> None:
        """The toolbar over one canvas, as a start of Vitralis builds them from what is saved."""
        self.teardown()
        forget_strokes()  # a start reads the file: what was drawn must have reached it
        self.canvas = Canvas(CANVAS)
        self.canvas.load(load_strokes_for(CANVAS))
        self.canvas.show()
        self.capture = DrawCapture(self.canvas, CANVAS, stop_active=lambda: self.bar.stop_modes())
        self.bar = Toolbar([self.canvas], [self.capture], licence=self.gate, updates=self.updates)
        self.bar.move(TOOLBAR_AT)
        self.bar.show()

    def teardown(self) -> None:
        if self.bar is not None:
            self.bar.close()
            for widget in (self.bar, self.capture, self.canvas):
                widget.close()
                widget.deleteLater()
            self.app.processEvents()

    def window(self, name: str) -> QWidget:
        windows = {"toolbar": self.bar, "canvas": self.canvas, "capture": self.capture, **self.bar._panels}
        return windows[name]

    def part(self, path: str) -> QWidget:
        """``toolbar._draw_btn``, ``toolbar._tool_btns.RECT``, ``toolbar._swatch_btns.6``, ``color.shades`` or
        ``settings.close`` (a window's ✕): a widget of one of the windows."""
        name, _, attribute = path.partition(".")
        widget = self.window(name)
        for step in filter(None, attribute.split(".")):
            if step == "close":
                widget = next(button for button in widget.findChildren(QPushButton) if button.text() == CLOSE)
            elif isinstance(widget, dict):
                widget = widget[Tool[step]]
            elif isinstance(widget, list):
                widget = widget[int(step)]
            else:
                widget = getattr(widget, step)
        return widget

    # --- commands -------------------------------------------------------------------------------------------

    def do_restart(self, language: str = "English", **_) -> dict:
        """Start over in ``language`` with what is saved (``wipe`` first for a first start)."""
        SettingsManager().set_language(language)
        set_language(language)
        self.build()
        return {}

    def do_wipe(self, **_) -> dict:
        self.teardown()
        self.bar = None
        flush_writes()
        for path in sorted(Path(sys.argv[1], "Vitralis").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        forget_strokes()
        self.updates = self._updates()
        return {}

    def do_icon(self, **_) -> dict:
        """The sizes of the toolbar window's icon."""
        return {"sizes": sorted(size.width() for size in self.bar.windowIcon().availableSizes())}

    def do_check_updates(self, **_) -> dict:
        """Ask the feed in memory, which offers a newer version."""
        self.updates.check_now()
        return {}

    def do_where(self, part: str, **_) -> dict:
        """The window that holds ``part`` and the part's rectangle in it, in the window's own pixels."""
        widget = self.part(part)
        window = widget.window()
        ratio = window.devicePixelRatioF()
        corner = widget.mapTo(window, QPoint(0, 0))
        box = [corner.x(), corner.y(), widget.width(), widget.height()]
        return {"hwnd": int(window.winId()), "rect": [round(value * ratio) for value in box], "ratio": ratio}

    def do_hero(self, **_) -> dict:
        """Draw the README's hero picture (``hero.py``) into the scratch folder; where it is."""
        path = Path(sys.argv[1], "hero.png")
        if not hero.render(self.bar).save(str(path)):
            raise OSError(f"couldn't write {path}")
        return {"path": str(path)}

    def do_taskbar(self, **_) -> dict:
        """What Windows needs to give the toolbar a taskbar button with Vitralis's icon: the process's app ID,
        the icon the window hands over, and that it is neither a tool window nor owned by another window."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32")
        user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetWindow.restype = wintypes.HWND
        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
        found = ctypes.c_wchar_p()
        shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(found))
        app_id = found.value
        ole32.CoTaskMemFree(found)
        hwnd = int(self.bar.winId())
        exstyle = user32.GetWindowLongPtrW(hwnd, -20)
        return {
            "app_id": app_id,
            "big_icon": bool(user32.SendMessageW(hwnd, 0x7F, 1, 0)),
            "small_icon": bool(user32.SendMessageW(hwnd, 0x7F, 0, 0)),
            "tool_window": bool(exstyle & 0x80),
            "owned": bool(user32.GetWindow(hwnd, 4)),
            "icon_sizes": sorted(size.width() for size in self.bar.windowIcon().availableSizes()),
        }

    def do_cloaked(self, **_) -> dict:
        """Whether DWM keeps each window that is up off the screen."""
        up = [widget for widget in self.app.topLevelWidgets() if widget.isVisible()]
        return {"cloaked": {type(widget).__name__: is_cloaked(int(widget.winId())) for widget in up}}

    def do_state(self, **_) -> dict:
        """What the app holds and what it saved. It fails when that, or any text on a window that is up, names
        the user: every test asks for it, so none can capture a screen that does."""
        state = self._state()
        refuse_personal({"state": state, "on screen": self._texts_on_screen()})
        return state

    def _texts_on_screen(self) -> list[str]:
        texts = []
        for window in self.app.topLevelWidgets():
            if not window.isVisible():
                continue
            texts += [window.windowTitle(), window.toolTip()]
            for widget in window.findChildren(QWidget):
                if isinstance(widget, QLabel | QAbstractButton | QLineEdit):
                    texts.append(widget.text())
                texts.append(widget.toolTip())
        return [text for text in texts if text]

    def _state(self) -> dict:
        forget_strokes()  # what the file holds, not what the app remembers having saved
        bar = self.bar
        saved = load_strokes_for(CANVAS)
        snapshots = bar._snapshot_win
        return {
            "mode": bar._mode,
            "tool": bar._tool.name,
            "color": bar._color,
            "size": int(bar._size_lbl.text()),
            "hidden": bar._vis_btn.isChecked(),
            "panels": list(bar._panels),
            "strokes": [[stroke.tool, stroke.color, stroke.points] for stroke in self.canvas.strokes],
            "saved": len(saved),
            "visible": self.canvas.isVisible(),
            "undo_enabled": bar._undo_btn.isEnabled(),
            "busy": self.updates.busy or self.gate.busy or bool(snapshots and snapshots.busy),
            "update_offered": self.updates.status.offer is not None,
            "snapshot_names": [snapshots._list.item(row).text() for row in range(snapshots._list.count())]
            if snapshots
            else [],
            "snapshot_name": snapshots._name_edit.text() if snapshots else "",
            "saved_snapshots": list_snapshots(),
        }

    def do_quit(self, **_) -> dict:
        self.teardown()
        self.gate.shutdown()
        flush_writes()
        self.app.quit()
        return {}

    def handle(self, text: str) -> None:
        try:
            command = json.loads(text)
            answer = {"ok": True, **getattr(self, f"do_{command['do']}")(**command)}
        except Exception as ex:  # told to the test, which raises: nothing is swallowed
            answer = {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
        self.app.processEvents()
        print("@@" + json.dumps(answer), flush=True)


def main() -> None:
    toolbar_module.GlobalHotkeyThread = InertThread
    toolbar_module.GlobalMouseWheelThread = InertThread
    toolbar_module.app_version = lambda: VERSION
    init_icons_dir()
    set_app_user_model_id()  # as main() does: the taskbar shows Vitralis's icon, not Python's
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(make_app_icon())
    app.setQuitOnLastWindowClosed(False)
    if not shown():  # off the user's screen unless the run asked to watch
        cloaker = Cloaker(app)
        app.installEventFilter(cloaker)
    driver = Driver(app)
    lines = _Lines()
    lines.line.connect(driver.handle)
    lines.start()
    print('@@{"ok": true}', flush=True)
    app.exec()
    lines.terminate()  # blocked in a read that will never come


if __name__ == "__main__":
    main()
