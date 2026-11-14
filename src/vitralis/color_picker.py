#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.450769
Revised: 2026/11/14 12:31:22.450769

The custom colour window: a square of every shade of one hue, a bar of hues under it, and the colour as
``#rrggbb`` to read or type. A colour is picked when the mouse lets go of it, or with Enter in the field. It is
Vitralis's own window (dark, frameless, dragged from anywhere, ✕ and Esc to close), not the system's dialog,
which has neither that look nor Vitralis's languages.
"""

import re

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vitralis.styles import danger_btn
from vitralis.translations import t
from vitralis.widgets import LineEdit, Panel

PICK_COLOR = "Pick color"
HEX_COLOR = re.compile(r"#?([0-9a-fA-F]{6})")
SHADES_SIZE = (220, 150)
HUES_HEIGHT = 16
HUE_STOPS = 6
"""Red, yellow, green, cyan, blue, magenta, and red again: the bar's gradient goes through each."""
MAX_HUE = 0.999
"""Qt takes a hue of 1.0 for none at all; the bar's right end is the last red before it."""
_FIELD_STYLE = (
    "QLineEdit { background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,25);"
    "border-radius: 6px; color: #f0f0f0; font-size: 12px; padding: 5px 8px; }"
    "QLineEdit:focus { border-color: rgba(255,255,255,60); }"
)


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


class _Picker(QWidget):
    """A surface the mouse picks a spot on: ``moved`` while it is held, ``released`` when it lets go."""

    moved = pyqtSignal(float, float)
    """Where the mouse is, each coordinate from 0 to 1."""
    released = pyqtSignal()

    def __init__(self, width: int, height: int) -> None:
        super().__init__()
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _tell(self, event) -> None:
        position = event.position()
        self.moved.emit(_unit(position.x() / (self.width() - 1)), _unit(position.y() / (self.height() - 1)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._tell(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._tell(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.released.emit()


class _Shades(_Picker):
    """Every shade of one hue: more of the colour to the right, darker downwards."""

    def __init__(self) -> None:
        super().__init__(*SHADES_SIZE)
        self.hue, self.saturation, self.value = 0.0, 1.0, 1.0

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        area = QRectF(self.rect())
        across = QLinearGradient(area.topLeft(), area.topRight())
        across.setColorAt(0, QColor("white"))
        across.setColorAt(1, QColor.fromHsvF(self.hue, 1, 1))
        painter.fillRect(area, across)
        down = QLinearGradient(area.topLeft(), area.bottomLeft())
        down.setColorAt(0, QColor(0, 0, 0, 0))
        down.setColorAt(1, QColor("black"))
        painter.fillRect(area, down)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        spot = QPointF(self.saturation * (self.width() - 1), (1 - self.value) * (self.height() - 1))
        painter.setPen(QPen(QColor("black"), 3))
        painter.drawEllipse(spot, 5, 5)
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.drawEllipse(spot, 5, 5)
        painter.end()


class _Hues(_Picker):
    def __init__(self) -> None:
        super().__init__(SHADES_SIZE[0], HUES_HEIGHT)
        self.hue = 0.0

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        area = QRectF(self.rect())
        hues = QLinearGradient(area.topLeft(), area.topRight())
        for stop in range(HUE_STOPS + 1):
            hues.setColorAt(stop / HUE_STOPS, QColor.fromHsvF(min(stop / HUE_STOPS, MAX_HUE), 1, 1))
        painter.fillRect(area, hues)
        x = self.hue / MAX_HUE * (self.width() - 1)
        painter.setPen(QPen(QColor("black"), 3))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.setPen(QPen(QColor("white"), 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.end()


class ColorWindow(Panel):
    picked = pyqtSignal(str)
    """The colour chosen, as ``#rrggbb``: when the mouse lets go of it, or Enter is pressed in the field."""

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(f"Vitralis — {t(PICK_COLOR)}", parent)
        self._build_ui()
        self.show_color(color)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._title_lbl = QLabel(t(PICK_COLOR))
        self._title_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(danger_btn())
        close_btn.clicked.connect(self.close)
        title_row.addWidget(self._title_lbl, stretch=1)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        self.shades = _Shades()
        self.shades.moved.connect(self._on_shade)
        self.shades.released.connect(self._pick)
        root.addWidget(self.shades)

        self.hues = _Hues()
        self.hues.moved.connect(self._on_hue)
        self.hues.released.connect(self._pick)
        root.addWidget(self.hues)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        self.preview = QLabel()
        self.preview.setFixedSize(28, 28)
        self.field = LineEdit()
        self.field.setMaxLength(7)
        self.field.setStyleSheet(_FIELD_STYLE)
        self.field.returnPressed.connect(self._on_typed)
        value_row.addWidget(self.preview)
        value_row.addWidget(self.field, stretch=1)
        root.addLayout(value_row)

    def color(self) -> str:
        """The colour shown, as ``#rrggbb``."""
        return QColor.fromHsvF(self.shades.hue, self.shades.saturation, self.shades.value).name()

    def show_color(self, color: str) -> None:
        """Show ``color`` (``#rrggbb``) without picking it; a grey keeps the hue the window was on."""
        hue, saturation, value, _alpha = QColor(color).getHsvF()
        if hue >= 0:  # -1 for a grey, which has no hue
            self.shades.hue = self.hues.hue = min(hue, MAX_HUE)
        self.shades.saturation, self.shades.value = saturation, value
        self._refresh(color)

    def _refresh(self, color: str | None = None) -> None:
        """Repaint for the colour shown; the field and the preview say ``color`` when it is given exactly (a
        colour read back from its hue and shade can be one step off the one typed)."""
        shown = color or self.color()
        self.shades.update()
        self.hues.update()
        self.field.setText(shown)
        self.preview.setStyleSheet(f"background: {shown}; border: 1px solid rgba(255,255,255,40); border-radius: 4px;")

    def _on_shade(self, across: float, down: float) -> None:
        self.shades.saturation, self.shades.value = across, 1 - down
        self._refresh()

    def _on_hue(self, across: float, _down: float) -> None:
        self.shades.hue = self.hues.hue = across * MAX_HUE
        self._refresh()

    def _pick(self) -> None:
        self.picked.emit(self.color())

    def _on_typed(self) -> None:
        """Enter in the field: pick the colour typed; what isn't one is replaced by the colour shown."""
        typed = HEX_COLOR.fullmatch(self.field.text().strip())
        if typed is None:
            self._refresh()
            return
        color = f"#{typed.group(1).lower()}"
        self.show_color(color)
        self.picked.emit(color)

    def retranslate(self) -> None:
        self._title_lbl.setText(t(PICK_COLOR))
        self.setWindowTitle(f"Vitralis — {t(PICK_COLOR)}")
