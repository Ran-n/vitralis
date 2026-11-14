#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.410036
Revised: 2026/11/14 12:31:24.875016

The app icon and the tray icon with its menu (show or hide the toolbar, quit), in the current UI language.
"""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from vitralis.icons import media_base
from vitralis.translations import t

SHOW_TOOLBAR = "Show toolbar"
HIDE_TOOLBAR = "Hide toolbar"
QUIT = "Quit"
MENU = (SHOW_TOOLBAR, HIDE_TOOLBAR, QUIT)
"""Every tray menu entry, so a test can check each is translated into every language."""


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


class TrayIcon(QSystemTrayIcon):
    """The tray icon; it keeps its menu alive (Qt doesn't) and can be told the language changed."""

    def __init__(self, app: QApplication, toolbar: QWidget, quit_app: Callable[[], None]) -> None:
        super().__init__(make_app_icon(), app)
        self.setToolTip("Vitralis")
        self._toolbar = toolbar
        self._menu = QMenu()
        self._show_action = self._menu.addAction("")
        self._hide_action = self._menu.addAction("")
        self._menu.addSeparator()
        self._quit_action = self._menu.addAction("")
        self._show_action.triggered.connect(toolbar.show_toolbar)
        self._hide_action.triggered.connect(toolbar.hide_toolbar)  # leaves any mode first
        self._quit_action.triggered.connect(quit_app)
        self._menu.aboutToShow.connect(self._offer_what_applies)
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self.retranslate()

    def retranslate(self) -> None:
        self._show_action.setText(t(SHOW_TOOLBAR))
        self._hide_action.setText(t(HIDE_TOOLBAR))
        self._quit_action.setText(t(QUIT))

    def _offer_what_applies(self) -> None:
        """Show is greyed out while the toolbar shows, Hide while it is hidden."""
        shown = self._toolbar.isVisible()
        self._show_action.setEnabled(not shown)
        self._hide_action.setEnabled(shown)

    def menu_texts(self) -> list[str]:
        return [action.text() for action in self._menu.actions() if not action.isSeparator()]

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toolbar.show_toolbar()

    def close(self) -> None:
        """Take the icon out of the tray and free it with its menu."""
        self.hide()
        self._menu.deleteLater()
        self.deleteLater()


def make_tray_icon(app: QApplication, toolbar) -> TrayIcon:
    tray = TrayIcon(app, toolbar, toolbar.quit)
    tray.show()
    return tray
