#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.794151
Revised: 2026/11/13 19:56:12.638481

Starts Vitralis behind its licence: the licence window first when no key is active on this computer, the
overlay (``Session``) once the licence holds, and back to the licence window if it stops holding.
"""

import argparse
import contextlib
import ctypes
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
from vitralis.updates import UPDATES_DIR, build_updates, is_packaged
from vitralis.updates.checker import UpdateChecker, UpdateStatus
from vitralis.updates.install import clean_leftovers, wait_for_exit
from vitralis.updates.messages import out_message, updated_message
from vitralis.updates.registration import sync_installed_version
from vitralis.updates.rules import Version, parse_version_or_none
from vitralis.version import app_version

logger = logging.getLogger("vitralis.app")


class Session:
    """The overlay on every screen, the toolbar and the tray icon: everything that only runs while licensed."""

    def __init__(self, app: QApplication, updates: UpdateChecker | None = None, updated: bool = False) -> None:
        self._app = app
        self._gate: LicenceGate | None = None
        self._updates = updates
        self._announce_updated = updated
        """This start follows an in-app update: say "Updated to {version}" once."""
        self._announced: set[Version] = set()
        """Versions the tray already told of during this run, so a daily re-check doesn't nag."""
        self._tray_says_update = False
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
        toolbar = Toolbar(self.canvases, self.captures, licence=self._gate, updates=self._updates)
        toolbar.setWindowIcon(app_icon)
        toolbar_ref.append(toolbar)
        primary = self._app.primaryScreen().geometry()
        toolbar.move(primary.x() + 20, primary.y() + 20)
        toolbar.show()
        self.toolbar = toolbar
        self._tray = make_tray_icon(self._app, toolbar)
        self._tray.messageClicked.connect(self._on_message_clicked)
        if self._announce_updated:
            self._announce_updated = False
            self._show_message(updated_message(app_version()), about_update=False)
        if self._updates is not None:
            self._updates.changed.connect(self._on_update_status)
            self._updates.start()
        logger.info("overlay started on %d screen(s)", len(self.canvases))

    def _show_message(self, text: str, about_update: bool) -> None:
        self._tray_says_update = about_update
        self._tray.showMessage("Vitralis", text, QSystemTrayIcon.MessageIcon.Information)

    def _on_update_status(self, status: UpdateStatus) -> None:
        """One tray message per newly offered version per run."""
        offered = status.offered
        if offered is None or offered.version in self._announced or self._tray is None:
            return
        self._announced.add(offered.version)
        self._show_message(out_message(status), about_update=True)

    def _on_message_clicked(self) -> None:
        if self._tray_says_update and self.toolbar is not None:
            self.toolbar.open_settings()

    def stop(self) -> None:
        """Tear everything down: the hotkey and wheel hooks stop with the toolbar; strokes are already saved."""
        if not self.running:
            return
        if self._updates is not None:
            self._updates.changed.disconnect(self._on_update_status)
            self._updates.stop()
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


WAIT_FOR_OLD_SECONDS = 30.0
"""How long a freshly installed version waits for the one that started it to quit."""


def parse_arguments(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Vitralis's own options (``--updated``, ``--wait-pid``, given by an in-app update); the rest is Qt's."""
    parser = argparse.ArgumentParser(prog="vitralis", add_help=False)
    parser.add_argument("--updated", metavar="OLD_VERSION", help="this start follows an in-app update")
    parser.add_argument("--wait-pid", type=int, metavar="PID", help="wait for this process to quit first")
    return parser.parse_known_args(argv[1:])


def clean_after_updates(current: str) -> None:
    """In the packaged exe, off the UI thread: delete the previous version (``<exe>.old``) and stale downloads,
    and, when this is the installed exe, show ``current`` in Windows's installed apps (an in-app update doesn't
    run the installer, which wrote the version it installed)."""
    if not is_packaged():
        return
    running = Path(sys.executable)

    def tidy() -> None:
        clean_leftovers(running, DATA_DIR / UPDATES_DIR, parse_version_or_none(current))
        sync_installed_version(running, current)

    threading.Thread(target=tidy, name="vitralis-update-cleanup", daemon=True).start()


def main() -> None:
    setup_logging()
    args, qt_args = parse_arguments(sys.argv)
    # two overlays, two sets of global hooks or two writers of licence.dat must never run at once
    if args.wait_pid is not None and not wait_for_exit(args.wait_pid, WAIT_FOR_OLD_SECONDS):
        logger.error(
            "the previous Vitralis (pid %d) didn't quit within %.0f s: quitting",
            args.wait_pid,
            WAIT_FOR_OLD_SECONDS,
        )
        sys.exit(1)
    if args.updated:
        logger.info("updated from %s to %s", args.updated, app_version())
    clean_after_updates(app_version())
    with contextlib.suppress(Exception):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ran.vitralis")

    init_icons_dir()
    app = QApplication(sys.argv[:1] + qt_args)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        "QToolTip { background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,40);"
        "border-radius: 4px; padding: 4px 6px; font-size: 12px; }"
    )
    app.setWindowIcon(make_app_icon())
    settings = SettingsManager()
    set_language(settings.language())  # the licence window may come before the toolbar

    parts = build_licence(DATA_DIR)
    updates = build_updates(DATA_DIR, settings)
    session = Session(app, updates=updates.checker, updated=bool(args.updated))
    gate = LicenceGate(parts.licence, parts.checks, session.start, session.stop, LicenceWindow)
    session.attach(gate)

    def _shutdown() -> None:
        session.stop()  # stops the update checks and any download
        gate.shutdown()
        parts.close()
        updates.close()

    app.aboutToQuit.connect(_shutdown)
    gate.begin()
    sys.exit(app.exec())
