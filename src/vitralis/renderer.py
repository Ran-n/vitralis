#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.199011
Revised: 2026/04/28 15:57:04.199011
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from vitralis.models import Stroke, Tool


def make_pen(color: str, width: int, eraser: bool = False) -> QPen:
    pen = QPen()
    pen.setWidth(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if eraser:
        pen.setColor(Qt.GlobalColor.transparent)
    else:
        pen.setColor(QColor(color))
    return pen


def draw_arrow(painter: QPainter, p1: QPointF, p2: QPointF, width: int) -> None:
    painter.drawLine(p1, p2)
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    arrow_len = max(12, width * 4)
    arrow_w = max(6, width * 2)
    tip = p2
    base = QPointF(tip.x() - ux * arrow_len, tip.y() - uy * arrow_len)
    perp = QPointF(-uy * arrow_w, ux * arrow_w)
    poly = QPolygonF(
        [
            tip,
            QPointF(base.x() + perp.x(), base.y() + perp.y()),
            QPointF(base.x() - perp.x(), base.y() - perp.y()),
        ]
    )
    old_brush = painter.brush()
    painter.setBrush(painter.pen().color())
    painter.drawPolygon(poly)
    painter.setBrush(old_brush)


def render_stroke(painter: QPainter, stroke: Stroke) -> None:
    tool = stroke.tool
    points = stroke.points

    if not points:
        return

    is_eraser = tool == Tool.ERASER.name
    painter.setPen(make_pen(stroke.color, stroke.width, eraser=is_eraser))

    if is_eraser:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)

    if tool in (Tool.PEN.name, Tool.ERASER.name):
        path = QPainterPath()
        path.moveTo(QPointF(*points[0]))
        for pt in points[1:]:
            path.lineTo(QPointF(*pt))
        painter.drawPath(path)

    elif tool == Tool.LINE.name and len(points) >= 2:
        painter.drawLine(QPointF(*points[0]), QPointF(*points[-1]))

    elif tool == Tool.ARROW.name and len(points) >= 2:
        draw_arrow(painter, QPointF(*points[0]), QPointF(*points[-1]), stroke.width)

    elif tool == Tool.RECT.name and len(points) >= 2:
        x0, y0 = points[0]
        x1, y1 = points[-1]
        painter.drawRect(QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized())

    elif tool == Tool.ELLIPSE.name and len(points) >= 2:
        x0, y0 = points[0]
        x1, y1 = points[-1]
        painter.drawEllipse(QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized())

    if is_eraser:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
