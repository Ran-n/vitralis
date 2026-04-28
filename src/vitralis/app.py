#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.794151
Revised: 2026/04/28 15:57:03.794151
"""

import contextlib
import ctypes
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from vitralis.canvas import Canvas, DrawCapture
from vitralis.icons import init_icons_dir
from vitralis.persistence import load_strokes_for
from vitralis.toolbar import Toolbar
from vitralis.tray import make_app_icon, make_tray_icon


def main() -> None:
    with contextlib.suppress(Exception):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ran.vitralis")

    init_icons_dir()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        "QToolTip { background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,40);"
        "border-radius: 4px; padding: 4px 6px; font-size: 12px; }"
    )

    canvases: list[Canvas] = []
    captures: list[DrawCapture] = []
    toolbar_ref: list[Toolbar] = []

    for screen in app.screens():
        geo = screen.geometry()
        canvas = Canvas(geo)
        canvas.load(load_strokes_for(geo))
        canvas.show()

        def _stop_active():
            toolbar_ref[0].stop_drawing()
            toolbar_ref[0].stop_pan()
            toolbar_ref[0].stop_delete()

        capture = DrawCapture(canvas, geo, stop_active=_stop_active, toolbar=toolbar_ref)
        capture.setWindowFlags(capture.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        canvases.append(canvas)
        captures.append(capture)

    app_icon = make_app_icon()
    app.setWindowIcon(app_icon)

    toolbar = Toolbar(canvases, captures)
    toolbar.setWindowIcon(app_icon)
    toolbar_ref.append(toolbar)

    primary = app.primaryScreen().geometry()
    toolbar.move(primary.x() + 20, primary.y() + 20)
    toolbar.show()

    _tray = make_tray_icon(app, toolbar)  # noqa: F841 — must stay alive

    app.aboutToQuit.connect(toolbar._hotkey_thread.stop)
    sys.exit(app.exec())
