#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.861492
Revised: 2026/04/28 15:57:03.861492
"""

import math

from PyQt6.QtCore import QPointF, QRect, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from vitralis.models import Stroke, Tool
from vitralis.persistence import save_strokes_for
from vitralis.renderer import render_stroke


class Canvas(QWidget):
    def __init__(self, geometry: QRect) -> None:
        super().__init__()
        self._geo = geometry
        self.strokes: list[Stroke] = []
        self.current: Stroke | None = None
        self.drawing: bool = False
        self.active_tool = Tool.PEN
        self.active_color = "#ff0000"
        self.active_width = 3
        self._offset = QPointF(0, 0)

        self.setGeometry(geometry)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowTitle("Vitralis Overlay")

        self._pixmap = QPixmap(geometry.size())
        self._pixmap.fill(Qt.GlobalColor.transparent)

    def load(self, strokes: list[Stroke]) -> None:
        self.strokes = strokes
        self._redraw_pixmap()
        self.update()

    def begin_stroke(self, pos: QPointF) -> None:
        self.current = Stroke(
            tool=self.active_tool.name,
            color=self.active_color,
            width=self.active_width,
            points=[[pos.x(), pos.y()]],
        )
        self.drawing = True

    def extend_stroke(self, pos: QPointF) -> None:
        if self.current and self.drawing:
            if self.active_tool in (Tool.PEN, Tool.ERASER):
                self.current.points.append([pos.x(), pos.y()])
            else:
                if len(self.current.points) == 1:
                    self.current.points.append([pos.x(), pos.y()])
                else:
                    self.current.points[-1] = [pos.x(), pos.y()]
            self.update()

    def end_stroke(self) -> None:
        if self.current and self.drawing and len(self.current.points) >= 1:
            self.strokes.append(self.current)
            self._commit_stroke(self.current)
            save_strokes_for(self._geo, self.strokes)
        self.current = None
        self.drawing = False
        self.update()

    def undo(self) -> None:
        if self.strokes:
            self.strokes.pop()
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()

    def clear(self) -> None:
        self.strokes.clear()
        self._offset = QPointF(0, 0)
        self._pixmap.fill(Qt.GlobalColor.transparent)
        save_strokes_for(self._geo, self.strokes)
        self.update()

    def delete_stroke_at(self, pos: QPointF, tolerance: float = 20.0) -> None:
        adjusted = pos - self._offset
        px, py = adjusted.x(), adjusted.y()
        best_idx, best_dist = -1, float("inf")
        for i, stroke in enumerate(self.strokes):
            pts = stroke.points
            for j in range(len(pts)):
                x0, y0 = pts[j]
                d = math.hypot(x0 - px, y0 - py)
                if d < best_dist:
                    best_dist, best_idx = d, i
                if j + 1 < len(pts):
                    x1, y1 = pts[j + 1]
                    dx, dy = x1 - x0, y1 - y0
                    seg_len_sq = dx * dx + dy * dy
                    if seg_len_sq > 0:
                        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg_len_sq))
                        cx, cy = x0 + t * dx, y0 + t * dy
                        d = math.hypot(cx - px, cy - py)
                        if d < best_dist:
                            best_dist, best_idx = d, i
        if best_idx >= 0 and best_dist <= tolerance:
            self.strokes.pop(best_idx)
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()

    def shift_by(self, delta: QPointF) -> None:
        self._offset += delta
        self.update()

    def apply_offset(self) -> None:
        if self._offset.isNull():
            return
        dx, dy = self._offset.x(), self._offset.y()
        for stroke in self.strokes:
            stroke.points = [[x + dx, y + dy] for x, y in stroke.points]
        self._offset = QPointF(0, 0)
        self._redraw_pixmap()
        save_strokes_for(self._geo, self.strokes)
        self.update()

    def _redraw_pixmap(self) -> None:
        self._pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for stroke in self.strokes:
            render_stroke(painter, stroke)
        painter.end()

    def _commit_stroke(self, stroke: Stroke) -> None:
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        render_stroke(painter, stroke)
        painter.end()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(self._offset.toPoint(), self._pixmap)
        if self.current:
            painter.translate(self._offset)
            render_stroke(painter, self.current)
        painter.end()


class DrawCapture(QWidget):
    """Invisible full-screen widget that captures mouse events while a tool is active."""

    def __init__(self, canvas: Canvas, geometry: QRect, stop_active, toolbar: list) -> None:
        super().__init__()
        self.canvas = canvas
        self._stop_active = stop_active
        self._toolbar_ref = toolbar
        self.pan_mode = False
        self.delete_mode = False
        self._pan_last: QPointF | None = None

        self.setGeometry(geometry)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setWindowOpacity(0.01)
        self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.pan_mode:
                self._pan_last = event.globalPosition()
            elif self.delete_mode:
                pos = event.position() + QPointF(self.geometry().topLeft())
                cp = pos - QPointF(self.canvas.geometry().topLeft())
                self.canvas.delete_stroke_at(cp)
            else:
                pos = event.position() + QPointF(self.geometry().topLeft())
                cp = pos - QPointF(self.canvas.geometry().topLeft())
                self.canvas.begin_stroke(cp)
        elif event.button() == Qt.MouseButton.RightButton:
            self._stop_active()

    def mouseMoveEvent(self, event) -> None:
        if self.pan_mode:
            if self._pan_last is not None:
                delta = event.globalPosition() - self._pan_last
                self._pan_last = event.globalPosition()
                self.canvas.shift_by(delta)
        elif not self.delete_mode:
            pos = event.position() + QPointF(self.geometry().topLeft())
            cp = pos - QPointF(self.canvas.geometry().topLeft())
            self.canvas.extend_stroke(cp)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.pan_mode:
                self._pan_last = None
                self.canvas.apply_offset()
            elif not self.delete_mode:
                self.canvas.end_stroke()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._stop_active()
        else:
            QApplication.sendEvent(self._toolbar_ref[0], event)
