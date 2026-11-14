#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.861492
Revised: 2026/11/14 17:53:23.542818

The overlay of one screen: ``Canvas`` shows that screen's strokes and lets every click through; ``DrawCapture``
sits over it while a mode (draw, pan, delete) is on and turns the mouse into strokes.
"""

import time
from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from vitralis.models import FREEHAND, Stroke, Tool
from vitralis.persistence import save_strokes_for
from vitralis.renderer import render_stroke

DELETE_TOLERANCE = 20.0
"""How near its line, in pixels, a click must be to delete a stroke."""


class Canvas(QWidget):
    changed = pyqtSignal()
    """The strokes changed (one drawn, undone, deleted, loaded, all cleared): the toolbar's Undo and Clear follow."""

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

    @property
    def screen_geometry(self) -> QRect:
        """The screen this canvas covers; its top-left corner names the screen in the saved files."""
        return self._geo

    def load(self, strokes: list[Stroke]) -> None:
        self.strokes = strokes
        self._redraw_pixmap()
        self.update()
        self.changed.emit()

    def begin_stroke(self, pos: QPointF) -> None:
        self.current = Stroke(
            tool=self.active_tool.name,
            color=self.active_color,
            width=self.active_width,
            points=[[pos.x(), pos.y()]],
            created=time.time(),
        )
        self.drawing = True

    def extend_stroke(self, pos: QPointF) -> None:
        if self.current and self.drawing:
            if self.current.tool in FREEHAND:
                self.current.points.append([pos.x(), pos.y()])
            else:
                if len(self.current.points) == 1:
                    self.current.points.append([pos.x(), pos.y()])
                else:
                    self.current.points[-1] = [pos.x(), pos.y()]
            self.update()

    def end_stroke(self) -> None:
        """Keep the stroke in progress. A click without a drag is a dot with the pen and the eraser; with a
        shape it is nothing (no line, no rectangle), so nothing is kept: it would be saved and undone unseen."""
        stroke, self.current, self.drawing = self.current, None, False
        if stroke is not None and (stroke.tool in FREEHAND or stroke.points[0] != stroke.points[-1]):
            self.strokes.append(stroke)
            self._commit_stroke(stroke)
            save_strokes_for(self._geo, self.strokes)
            self.changed.emit()
        self.update()

    def last_drawn_at(self) -> float | None:
        """When this screen's latest stroke was drawn; ``None`` without strokes."""
        return self.strokes[-1].created if self.strokes else None

    def undo(self) -> None:
        if self.strokes:
            self.strokes.pop()
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()
            self.changed.emit()

    def clear(self) -> None:
        self.strokes.clear()
        self.current, self.drawing = None, False  # a stroke still being drawn goes too
        self._offset = QPointF(0, 0)
        self._pixmap.fill(Qt.GlobalColor.transparent)
        save_strokes_for(self._geo, self.strokes)
        self.update()
        self.changed.emit()

    def delete_stroke_at(self, pos: QPointF, tolerance: float = DELETE_TOLERANCE) -> None:
        """Delete the stroke whose line is nearest ``pos``, when it is within ``tolerance`` pixels."""
        if not self.strokes:
            return
        adjusted = pos - self._offset
        distances = [stroke.distance_to(adjusted.x(), adjusted.y()) for stroke in self.strokes]
        nearest = min(range(len(distances)), key=distances.__getitem__)
        if distances[nearest] <= tolerance:
            self.strokes.pop(nearest)
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()
            self.changed.emit()

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

    def __init__(self, canvas: Canvas, geometry: QRect, stop_active: Callable[[], None]) -> None:
        super().__init__()
        self.canvas = canvas
        self._stop_active = stop_active
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

    def closeEvent(self, event) -> None:
        """Alt+F4 while a mode is on leaves the mode; only the session closes a capture for good."""
        if event.spontaneous():
            event.ignore()
            self._stop_active()
            return
        event.accept()

    def set_mode(self, pan: bool, delete: bool) -> None:
        """What the mouse does here: pan, delete, or (neither) draw. Changing it ends what the mouse was in the
        middle of: the capture stays up from one mode to the next, so no hide does it."""
        if (pan, delete) != (self.pan_mode, self.delete_mode):
            self.finish_gesture()
        self.pan_mode, self.delete_mode = pan, delete

    def finish_gesture(self) -> None:
        """End what the mouse was in the middle of: the stroke being drawn is kept, the pan under way is applied.
        Leaving a mode with the button still held (F8, a right click, Esc) never sends the release."""
        if self.canvas.drawing:
            self.canvas.end_stroke()
        if self._pan_last is not None:
            self._pan_last = None
            self.canvas.apply_offset()

    def hideEvent(self, event) -> None:
        self.finish_gesture()
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:
        """Esc leaves the mode. Every other key is the toolbar's, whose shortcuts work from any Vitralis window."""
        if event.key() == Qt.Key.Key_Escape:
            self._stop_active()
        else:
            super().keyPressEvent(event)
