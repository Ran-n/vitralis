#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.794151
Revised: 2026/11/11 11:06:52.931779

Starts Vitralis behind its licence: the licence window first when no key is active on this computer, the
overlay (``Session``) once the licence holds, and back to the licence window if it stops holding.
"""

import contextlib
import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from vitralis.canvas import Canvas, DrawCapture
from vitralis.icons import init_icons_dir
from vitralis.licence import build_licence
from vitralis.licence.gate import LicenceGate
from vitralis.licence.window import LicenceWindow
from vitralis.persistence import DATA_DIR, load_strokes_for
from vitralis.settings import SettingsManager
from vitralis.toolbar import Toolbar
from vitralis.translations import set_language
from vitralis.tray import make_app_icon, make_tray_icon

logger = logging.getLogger("vitralis.app")


class Session:
    """The overlay on every screen, the toolbar and the tray icon: everything that only runs while licensed."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._gate: LicenceGate | None = None
        self.canvases: list[Canvas] = []
        self.captures: list[DrawCapture] = []
        self.toolbar: Toolbar | None = None
        self._tray: QSystemTrayIcon | None = None

    def attach(self, gate: LicenceGate) -> None:
        self._gate = gate

    @property
    def running(self) -> bool:
        return self.toolbar is not None

    def start(self) -> None:
        if self.running:
            return
        toolbar_ref: list[Toolbar] = []

        def _stop_active():
            toolbar_ref[0].stop_drawing()
            toolbar_ref[0].stop_pan()
            toolbar_ref[0].stop_delete()

        for screen in self._app.screens():
            geo = screen.geometry()
            canvas = Canvas(geo)
            canvas.load(load_strokes_for(geo))
            canvas.show()
            capture = DrawCapture(canvas, geo, stop_active=_stop_active, toolbar=toolbar_ref)
            capture.setWindowFlags(capture.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.canvases.append(canvas)
            self.captures.append(capture)

        app_icon = make_app_icon()
        toolbar = Toolbar(self.canvases, self.captures, licence=self._gate)
        toolbar.setWindowIcon(app_icon)
        toolbar_ref.append(toolbar)
        primary = self._app.primaryScreen().geometry()
        toolbar.move(primary.x() + 20, primary.y() + 20)
        toolbar.show()
        self.toolbar = toolbar
        self._tray = make_tray_icon(self._app, toolbar)
        logger.info("overlay started on %d screen(s)", len(self.canvases))

    def stop(self) -> None:
        """Tear everything down: the hotkey and wheel hooks stop with the toolbar; strokes are already saved."""
        if not self.running:
            return
        if self._tray is not None:
            self._tray.hide()
            self._tray.deleteLater()
            self._tray = None
        self.toolbar.close()  # stops the global hotkey and wheel threads, closes its panels
        self.toolbar.deleteLater()
        self.toolbar = None
        for widget in (*self.captures, *self.canvases):
            widget.close()
            widget.deleteLater()
        self.captures.clear()
        self.canvases.clear()
        logger.info("overlay stopped")


LOG_FILE = DATA_DIR / "vitralis.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging() -> None:
    """Log to ``vitralis.log`` in the data folder (the packaged exe has no console), and to the console too
    when there is one."""
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers)


def main() -> None:
    setup_logging()
    with contextlib.suppress(Exception):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ran.vitralis")

    init_icons_dir()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        "QToolTip { background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,40);"
        "border-radius: 4px; padding: 4px 6px; font-size: 12px; }"
    )
    app.setWindowIcon(make_app_icon())
    set_language(SettingsManager().language())  # the licence window may come before the toolbar

    parts = build_licence(DATA_DIR)
    session = Session(app)
    gate = LicenceGate(parts.licence, parts.checks, session.start, session.stop, LicenceWindow)
    session.attach(gate)

    def _shutdown() -> None:
        session.stop()
        gate.shutdown()
        parts.close()

    app.aboutToQuit.connect(_shutdown)
    gate.begin()
    sys.exit(app.exec())
