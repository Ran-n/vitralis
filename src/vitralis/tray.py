#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.410036
Revised: 2026/04/28 16:22:10.836404
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from vitralis.icons import media_base


def make_app_icon() -> QIcon:
    icon_path = media_base() / "media" / "logo" / "icon.png"
    source = QPixmap(str(icon_path))
    icon = QIcon()
    if not source.isNull():
        for size in (16, 32, 48, 64, 128, 256):
            icon.addPixmap(
                source.scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
    else:
        px = QPixmap(256, 256)
        px.fill(QColor("#0d1420"))
        icon.addPixmap(px)
    return icon


def make_tray_icon(app: QApplication, toolbar) -> QSystemTrayIcon:
    icon = make_app_icon()
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Vitralis")

    menu = QMenu()
    show_action = menu.addAction("Show toolbar")
    hide_action = menu.addAction("Hide toolbar")
    menu.addSeparator()
    quit_action = menu.addAction("Quit")

    show_action.triggered.connect(toolbar.show)
    hide_action.triggered.connect(toolbar.hide)
    quit_action.triggered.connect(toolbar._quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: toolbar.show() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
    )
    tray.show()
    return tray
