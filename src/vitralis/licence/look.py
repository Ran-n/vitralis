#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 21:39:56.968445
Revised: 2026/11/15 21:40:18.471995

How the licence window looks: its width, its text styles, the Vitralis logo and name at its top, the labels and
the key field it is made of, and the dark rounded panel it is painted on. What it does is in ``window.py``.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from vitralis.icons import logo_path
from vitralis.styles import danger_btn
from vitralis.widgets import LineEdit

logger = logging.getLogger("vitralis.licence.look")

KEY_PLACEHOLDER = "BRN-XXXX-XXXX-XXXX-XXXX"
WIDTH = 380
LOGO_SIZE = 72
MESSAGE = "color: rgba(255,255,255,210); font-size: 12px; background: transparent;"
ERROR = "color: #ff8a65; font-size: 11px; background: transparent;"
NOTE = "color: rgba(255,255,255,90); font-size: 10px; background: transparent;"
TITLE = "color: white; font-size: 16px; font-weight: 700; background: transparent;"
FIELD = (
    "QLineEdit { background: rgba(255,255,255,10); color: #f0f0f0; border: 1px solid rgba(255,255,255,30);"
    "border-radius: 6px; padding: 6px 8px; font-size: 14px; font-family: Consolas, monospace; }"
    "QLineEdit:focus { border: 1px solid #2272c3; }"
    "QLineEdit:disabled { color: rgba(255,255,255,80); }"
)
PANEL_EDGE = QColor(255, 255, 255, 18)
PANEL_FILL = QColor(18, 18, 22, 230)
PANEL_RADIUS = 9


def close_row(button: QPushButton) -> QHBoxLayout:
    """``button`` as the window's ✕, at the top right."""
    button.setText("✕")
    button.setFixedSize(22, 22)
    button.setStyleSheet(danger_btn())
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(button)
    return row


def logo() -> QLabel | None:
    """The Vitralis logo, or ``None`` (and an error in the log) when it can't be loaded."""
    path = logo_path()
    picture = QPixmap(str(path))
    if picture.isNull():  # the window is whole without it, and the log says what is missing
        logger.error("the Vitralis logo %s can't be loaded: the licence window shows none", path)
        return None
    label = QLabel()
    mode = Qt.TransformationMode.SmoothTransformation
    label.setPixmap(picture.scaled(LOGO_SIZE, LOGO_SIZE, Qt.AspectRatioMode.KeepAspectRatio, mode))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("background: transparent;")
    return label


def text_label(style: str, text: str = "") -> QLabel:
    """Centred, wrapped text in ``style``."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(style)
    return label


def key_field() -> LineEdit:
    field = LineEdit()
    field.setPlaceholderText(KEY_PLACEHOLDER)
    field.setAlignment(Qt.AlignmentFlag.AlignCenter)
    field.setStyleSheet(FIELD)
    return field


def paint_panel(widget: QWidget) -> None:
    """The dark rounded panel the window's contents sit on."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(PANEL_EDGE, 1))
    painter.setBrush(PANEL_FILL)
    painter.drawRoundedRect(widget.rect().adjusted(1, 1, -1, -1), PANEL_RADIUS, PANEL_RADIUS)
    painter.end()
