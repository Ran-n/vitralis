#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.718195
Revised: 2026/11/14 12:31:22.718195

What Vitralis's small windows share: ``Panel``, the dark frameless window that drags from anywhere, closes with
Esc and says when it closed; and ``LineEdit``, a text field whose right-click menu speaks the UI language (Qt's
own stays English in most of Vitralis's languages).
"""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import QLineEdit, QMenu, QWidget

from vitralis.translations import t

PANEL_FILL = QColor(18, 18, 22, 218)
PANEL_EDGE = QColor(255, 255, 255, 18)
PANEL_RADIUS = 9
MENU_STYLE = (
    "QMenu { background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,40); padding: 4px; }"
    "QMenu::item { padding: 5px 18px; border-radius: 4px; }"
    "QMenu::item:selected { background: #e07020; color: white; }"
    "QMenu::item:disabled { color: rgba(255,255,255,80); }"
)
CUT = "Cut"
COPY = "Copy"
PASTE = "Paste"
SELECT_ALL = "Select all"
EDIT_MENU = (CUT, COPY, PASTE, SELECT_ALL)
"""Every entry of a text field's menu, so a test can check each is translated into every language."""


class Divider(QWidget):
    """A hairline between two groups of a panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet("background: rgba(255,255,255,20);")


class Panel(QWidget):
    """A frameless, always-on-top window on the dark rounded panel: dragged from anywhere on it, closed with
    Esc, and telling through ``closed`` when it closed."""

    closed = pyqtSignal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(
            parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)
        self._dragging = False
        self._drag_pos = QPoint()
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(PANEL_EDGE, 1))
        painter.setBrush(PANEL_FILL)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), PANEL_RADIUS, PANEL_RADIUS)
        painter.end()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        event.accept()


class LineEdit(QLineEdit):
    """A text field with its right-click menu in the UI language."""

    def edit_menu(self) -> QMenu:
        """Cut, Copy, Paste and Select all, each greyed out when it would do nothing."""
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        selected = self.hasSelectedText() and self.echoMode() == QLineEdit.EchoMode.Normal
        writable = self.isEnabled() and not self.isReadOnly()
        menu.addAction(t(CUT), self.cut).setEnabled(selected and writable)
        menu.addAction(t(COPY), self.copy).setEnabled(selected)
        menu.addAction(t(PASTE), self.paste).setEnabled(writable and bool(QGuiApplication.clipboard().text()))
        menu.addSeparator()
        menu.addAction(t(SELECT_ALL), self.selectAll).setEnabled(bool(self.text()))
        return menu

    def contextMenuEvent(self, event) -> None:
        menu = self.edit_menu()
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(event.globalPos())
