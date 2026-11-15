#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 21:52:55.091626
Revised: 2026/11/15 21:53:11.662303

The README's hero picture: Vitralis doing its job, notes drawn by its real overlay over a made-up slide, with its
real toolbar beside them. The slide's content is invented (no file, name or path of anyone's), the strokes are
the overlay's own ``Stroke`` and drawing code, and the toolbar is the one the tests drive, so the picture changes
when the app's look does and is reviewed like every other baseline.
"""

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from vitralis.canvas import Canvas
from vitralis.models import Stroke

SIZE = (960, 580)
SLIDE = QRect(190, 24, 750, 532)
TOOLBAR_AT = QPoint(24, 24)
BARS = (("Q1", 0.42), ("Q2", 0.58), ("Q3", 0.51), ("Q4", 0.86))
CHART = QRect(70, 230, 420, 230)
"""The bar chart, in the slide's own pixels."""
ORANGE, RED, GREEN, BLUE = "#fe8019", "#fb4934", "#b8bb26", "#83a598"


def _bar(index: int) -> QRect:
    """Bar ``index`` of the chart, in the slide's own pixels."""
    gap, width = 34, 66
    height = int(CHART.height() * BARS[index][1])
    left = CHART.left() + gap + index * (width + gap)
    return QRect(left, CHART.bottom() - height, width, height)


def paint_slide(painter: QPainter, area: QRect) -> None:
    """A slide of an invented quarterly review: a title, three points and a bar chart."""
    painter.save()
    painter.translate(area.topLeft())
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#fbf1c7"))
    painter.drawRoundedRect(QRectF(0, 0, area.width(), area.height()), 10, 10)
    painter.setPen(QColor("#3c3836"))
    painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
    painter.drawText(QRect(48, 34, area.width() - 96, 44), Qt.AlignmentFlag.AlignLeft, "Quarterly review")
    painter.setFont(QFont("Segoe UI", 12))
    for row, line in enumerate(
        ("Sign-ups up 40 % since spring", "Support replies within a day", "New office opens in March")
    ):
        painter.drawText(QRect(64, 100 + row * 32, 600, 28), Qt.AlignmentFlag.AlignLeft, "•  " + line)
    painter.setPen(QPen(QColor("#a89984"), 2))
    painter.drawLine(CHART.bottomLeft(), CHART.bottomRight())
    painter.setFont(QFont("Segoe UI", 11))
    for index, (label, _) in enumerate(BARS):
        bar = _bar(index)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#458588"))
        painter.drawRect(bar)
        painter.setPen(QColor("#504945"))
        painter.drawText(QRect(bar.left(), CHART.bottom() + 6, bar.width(), 22), Qt.AlignmentFlag.AlignHCenter, label)
    painter.restore()


def strokes() -> list[Stroke]:
    """Notes as a person would draw them on that slide, in the overlay's own pixels."""
    tall = _bar(3).adjusted(-12, -14, 12, 8)
    note = QPoint(CHART.right() + 40, 140)
    return [
        Stroke("RECT", RED, 5, [[tall.left(), tall.top()], [tall.right(), tall.bottom()]]),
        Stroke("ARROW", ORANGE, 5, [[note.x() + 60, note.y() + 30], [tall.right() + 6, tall.top() + 40]]),
        Stroke("ELLIPSE", GREEN, 4, [[52, 96], [356, 130]]),
        Stroke("PEN", BLUE, 4, _tick(QPoint(620, 108))),
        Stroke("LINE", ORANGE, 4, [[64, 194], [300, 194]]),
    ]


def _tick(at: QPoint) -> list[list[float]]:
    """A hand-drawn tick, a little uneven."""
    points = [(0, 18), (5, 23), (10, 29), (15, 33), (22, 24), (30, 13), (38, 4), (46, -6)]
    return [[at.x() + x, at.y() + y] for x, y in points]


def render(toolbar: QWidget) -> QImage:
    """The whole picture: a desktop, the slide, the overlay's notes over it and the toolbar beside it."""
    image = QImage(*SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    backdrop = QLinearGradient(0, 0, SIZE[0], SIZE[1])
    backdrop.setColorAt(0, QColor("#1d2021"))
    backdrop.setColorAt(1, QColor("#32302f"))
    painter.fillRect(image.rect(), backdrop)
    paint_slide(painter, SLIDE)
    overlay = Canvas(SLIDE)
    overlay.load(strokes())
    painter.drawPixmap(SLIDE.topLeft(), overlay.grab())
    overlay.deleteLater()
    painter.drawPixmap(TOOLBAR_AT, toolbar.grab())
    painter.end()
    return image
