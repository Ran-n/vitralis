#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:10.362555
Revised: 2026/11/14 00:23:22.098222

A real canvas and its capture on the offscreen ``QApplication``, driven with Qt mouse and key events (never the
real mouse): drawing with each tool, undo, delete, pan and clear, each saved for the next start, and what the
painter leaves on the canvas.
"""

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

import vitralis.persistence as persistence
from vitralis.canvas import Canvas, DrawCapture
from vitralis.models import Stroke, Tool
from vitralis.persistence import forget_strokes, load_strokes_for

pytestmark = pytest.mark.ui
GEO = QRect(0, 0, 400, 300)
RED = "#ff0000"


class KeySink(QWidget):
    """Stands in for the toolbar, which gets the keys a capture doesn't handle."""

    def __init__(self) -> None:
        super().__init__()
        self.keys: list[int] = []

    def keyPressEvent(self, event) -> None:
        self.keys.append(event.key())


@pytest.fixture
def canvas(qapp):
    made = Canvas(GEO)
    yield made
    made.deleteLater()


@pytest.fixture
def capture(qapp, canvas):
    stops: list[int] = []
    sink = KeySink()
    made = DrawCapture(canvas, GEO, stop_active=lambda: stops.append(1), toolbar=[sink])
    made.stops, made.sink = stops, sink
    yield made
    made.deleteLater()
    sink.deleteLater()


def mouse(widget, kind, x: float, y: float, button=Qt.MouseButton.LeftButton) -> None:
    local = QPointF(x, y)
    held = button if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    QApplication.sendEvent(widget, QMouseEvent(kind, local, local, button, held, Qt.KeyboardModifier.NoModifier))


def drag(widget, *points: tuple[float, float]) -> None:
    mouse(widget, QEvent.Type.MouseButtonPress, *points[0])
    for point in points[1:]:
        mouse(widget, QEvent.Type.MouseMove, *point)
    mouse(widget, QEvent.Type.MouseButtonRelease, *points[-1])


def saved() -> list[Stroke]:
    forget_strokes()
    return load_strokes_for(GEO)


def pixel(canvas: Canvas, x: int, y: int) -> QColor:
    return canvas._pixmap.toImage().pixelColor(x, y)


# --- drawing ------------------------------------------------------------------------------------------------


def test_a_pen_drag_becomes_one_saved_stroke_with_every_point(canvas, capture):
    canvas.active_color, canvas.active_width = RED, 4
    drag(capture, (10, 10), (50, 10), (90, 30))
    assert len(canvas.strokes) == 1
    stroke = canvas.strokes[0]
    assert (stroke.tool, stroke.color, stroke.width) == ("PEN", RED, 4)
    assert stroke.points == [[10.0, 10.0], [50.0, 10.0], [90.0, 30.0]] and stroke.created > 0
    assert saved() == canvas.strokes and not canvas.drawing and canvas.current is None
    assert pixel(canvas, 30, 10) == QColor(RED) and pixel(canvas, 200, 200).alpha() == 0


@pytest.mark.parametrize("tool", [Tool.LINE, Tool.ARROW, Tool.RECT, Tool.ELLIPSE])
def test_a_shape_keeps_only_its_two_ends(canvas, capture, tool):
    canvas.active_tool = tool
    drag(capture, (20, 20), (60, 40), (120, 90), (200, 150))
    assert canvas.strokes[0].tool == tool.name
    assert canvas.strokes[0].points == [[20.0, 20.0], [200.0, 150.0]]


def test_a_line_and_a_rectangle_paint_where_they_should(canvas, capture):
    canvas.active_color, canvas.active_width = RED, 4
    canvas.active_tool = Tool.LINE
    drag(capture, (20, 50), (120, 50))
    canvas.active_tool = Tool.RECT
    drag(capture, (200, 100), (300, 200))
    assert pixel(canvas, 70, 50) == QColor(RED)  # on the line
    assert pixel(canvas, 250, 100) == QColor(RED)  # the rectangle's top edge
    assert pixel(canvas, 250, 150).alpha() == 0  # its inside stays clear


def test_the_eraser_clears_what_it_crosses(canvas, capture):
    canvas.active_color, canvas.active_width = RED, 10
    drag(capture, (20, 50), (200, 50))
    assert pixel(canvas, 100, 50) == QColor(RED)
    canvas.active_tool = Tool.ERASER
    drag(capture, (100, 20), (100, 80))
    assert pixel(canvas, 100, 50).alpha() == 0 and pixel(canvas, 40, 50) == QColor(RED)
    assert [s.tool for s in saved()] == ["PEN", "ERASER"]


def test_a_click_without_a_drag_is_a_dot(canvas, capture):
    drag(capture, (40, 40))
    assert len(canvas.strokes) == 1 and canvas.strokes[0].points == [[40.0, 40.0]]


def test_moving_without_pressing_draws_nothing(canvas, capture):
    mouse(capture, QEvent.Type.MouseMove, 30, 30)
    mouse(capture, QEvent.Type.MouseButtonRelease, 30, 30)
    assert canvas.strokes == [] and saved() == []


# --- undo, delete, pan, clear -------------------------------------------------------------------------------


def test_undo_takes_back_the_last_stroke_and_saves(canvas, capture):
    drag(capture, (10, 10), (50, 10))
    drag(capture, (10, 100), (50, 100))
    first = canvas.strokes[0]
    assert canvas.last_drawn_at() == canvas.strokes[-1].created
    canvas.undo()
    assert canvas.strokes == [first] and saved() == [first]
    assert pixel(canvas, 30, 100).alpha() == 0 and pixel(canvas, 30, 10).alpha() > 0
    canvas.undo()
    canvas.undo()  # nothing left: nothing happens
    assert canvas.strokes == [] and canvas.last_drawn_at() is None


def test_delete_mode_removes_the_stroke_nearest_the_click_only_when_close(canvas, capture):
    canvas.active_tool = Tool.LINE
    drag(capture, (10, 50), (200, 50))
    drag(capture, (10, 200), (200, 200))
    top, bottom = canvas.strokes
    capture.delete_mode = True
    drag(capture, (300, 120))  # far from both
    assert canvas.strokes == [top, bottom]
    drag(capture, (100, 205))  # beside the lower line's middle, between its points
    assert canvas.strokes == [top] and saved() == [top]
    mouse(capture, QEvent.Type.MouseMove, 100, 55)  # moving in delete mode draws nothing
    assert canvas.current is None


def test_pan_shifts_every_stroke_and_saves_on_release(canvas, capture):
    canvas.active_tool = Tool.LINE
    drag(capture, (10, 50), (100, 50))
    capture.pan_mode = True
    mouse(capture, QEvent.Type.MouseButtonPress, 200, 200)
    mouse(capture, QEvent.Type.MouseMove, 230, 215)
    assert canvas.strokes[0].points == [[10.0, 50.0], [100.0, 50.0]]  # only shown shifted until released
    mouse(capture, QEvent.Type.MouseButtonRelease, 230, 215)
    assert canvas.strokes[0].points == [[40.0, 65.0], [130.0, 65.0]]
    assert saved()[0].points == [[40.0, 65.0], [130.0, 65.0]]
    mouse(capture, QEvent.Type.MouseMove, 300, 300)  # not held any more: nothing moves
    assert canvas.strokes[0].points == [[40.0, 65.0], [130.0, 65.0]]


def test_a_pan_that_goes_nowhere_saves_nothing(canvas, capture, monkeypatch):
    drag(capture, (10, 50), (100, 50))
    saves = []
    monkeypatch.setattr("vitralis.canvas.save_strokes_for", lambda *a: saves.append(a))
    capture.pan_mode = True
    drag(capture, (200, 200))
    assert saves == []


def test_delete_accounts_for_a_pan_in_progress(canvas):
    canvas.load([Stroke("LINE", RED, 3, [[10.0, 50.0], [100.0, 50.0]])])
    canvas.shift_by(QPointF(0, 100))
    canvas.delete_stroke_at(QPointF(50, 150))
    assert canvas.strokes == []


def test_clear_removes_everything_and_saves(canvas, capture):
    drag(capture, (10, 10), (50, 10))
    canvas.clear()
    assert canvas.strokes == [] and saved() == [] and pixel(canvas, 30, 10).alpha() == 0


def test_loading_replaces_the_strokes_and_repaints(canvas):
    canvas.load([Stroke("LINE", RED, 6, [[10.0, 50.0], [100.0, 50.0]])])
    assert pixel(canvas, 50, 50) == QColor(RED)
    canvas.load([])
    assert pixel(canvas, 50, 50).alpha() == 0


def test_the_canvas_knows_its_screen_and_lets_clicks_through(canvas):
    assert canvas.screen_geometry == GEO
    assert canvas.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_painting_the_canvas_shows_the_stroke_in_progress(canvas, capture):
    canvas.active_color, canvas.active_width = RED, 6
    mouse(capture, QEvent.Type.MouseButtonPress, 20, 50)
    mouse(capture, QEvent.Type.MouseMove, 120, 50)
    image = canvas.grab().toImage()
    ratio = image.devicePixelRatio()
    assert image.pixelColor(int(70 * ratio), int(50 * ratio)) == QColor(RED)
    assert canvas.strokes == []  # not committed until released


# --- leaving a mode -----------------------------------------------------------------------------------------


def test_a_right_click_and_escape_leave_the_mode(capture):
    mouse(capture, QEvent.Type.MouseButtonPress, 10, 10, Qt.MouseButton.RightButton)
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(capture, key)
    assert capture.stops == [1, 1] and capture.sink.keys == []


def test_other_keys_go_to_the_toolbar(capture):
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(capture, key)
    assert capture.sink.keys == [Qt.Key.Key_Z] and capture.stops == []


def test_a_capture_on_a_second_screen_draws_in_that_screens_coordinates(qapp):
    geo = QRect(400, 0, 300, 200)
    canvas = Canvas(geo)
    capture = DrawCapture(canvas, geo, stop_active=lambda: None, toolbar=[])
    drag(capture, (10, 10), (50, 10))
    assert canvas.strokes[0].points == [[10.0, 10.0], [50.0, 10.0]]
    forget_strokes()
    assert load_strokes_for(geo) == canvas.strokes and load_strokes_for(GEO) == []
    assert QPoint(geo.x(), geo.y()) == capture.geometry().topLeft()
    assert persistence.screen_key(geo) == "400,0"
    capture.deleteLater()
    canvas.deleteLater()
