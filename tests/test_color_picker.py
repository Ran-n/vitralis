#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.822154
Revised: 2026/11/14 12:31:22.822154

The colour window on the offscreen ``QApplication``, driven with Qt mouse and key events: it opens on the colour
in use, a spot of the shades or of the hues is picked when the mouse lets go, a typed ``#rrggbb`` is picked with
Enter, and what it paints is the colour it says.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QApplication

from vitralis.color_picker import HUES_HEIGHT, MAX_HUE, SHADES_SIZE, ColorWindow
from vitralis.translations import _TRANSLATIONS, set_language

pytestmark = pytest.mark.ui


@pytest.fixture
def picker(qapp, icons):
    made = ColorWindow("#2196f3")
    made.picks = []
    made.picked.connect(made.picks.append)
    yield made
    made.close()
    made.deleteLater()


def mouse(widget, kind, x: float, y: float, button=Qt.MouseButton.LeftButton) -> None:
    spot = QPointF(x, y)
    held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
    QApplication.sendEvent(widget, QMouseEvent(kind, spot, spot, button, held, Qt.KeyboardModifier.NoModifier))


def click(widget, x: float, y: float) -> None:
    mouse(widget, QEvent.Type.MouseButtonPress, x, y)
    mouse(widget, QEvent.Type.MouseButtonRelease, x, y)


def grabbed(widget, x: int, y: int) -> QColor:
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio))


def test_it_opens_on_the_colour_in_use_and_picks_nothing_by_itself(picker):
    assert picker.color() == "#2196f3" == picker.field.text()
    assert "#2196f3" in picker.preview.styleSheet() and picker.picks == []


def test_it_is_one_of_vitraliss_windows(picker):
    """Frameless, on top, with the ✕ at the top right: not the system's colour dialog."""
    from PyQt6.QtWidgets import QPushButton

    assert picker.windowFlags() & Qt.WindowType.FramelessWindowHint
    close = [button for button in picker.findChildren(QPushButton) if button.text() == "✕"]
    assert len(close) == 1 and (close[0].width(), close[0].height()) == (22, 22)
    picker.show()
    closed = []
    picker.closed.connect(lambda: closed.append(1))
    close[0].click()
    assert closed == [1] and not picker.isVisible() and picker.picks == []


def test_a_corner_of_the_shades_is_the_pure_hue_white_or_black(picker):
    width, height = SHADES_SIZE
    picker.show_color("#ff0000")
    click(picker.shades, width - 1, 0)
    click(picker.shades, 0, 0)
    click(picker.shades, 0, height - 1)
    assert picker.picks == ["#ff0000", "#ffffff", "#000000"]
    assert picker.field.text() == "#000000" and "#000000" in picker.preview.styleSheet()


def test_dragging_over_the_shades_shows_the_colour_and_picks_it_on_release(picker):
    picker.show_color("#ff0000")
    mouse(picker.shades, QEvent.Type.MouseButtonPress, 10, 10)
    mouse(picker.shades, QEvent.Type.MouseMove, 150, 60)
    shown = picker.field.text()
    assert shown == picker.color() != "#ff0000" and picker.picks == []  # shown while held, not yet picked
    mouse(picker.shades, QEvent.Type.MouseButtonRelease, 150, 60)
    assert picker.picks == [shown]


def test_moving_without_the_button_held_and_other_buttons_pick_nothing(picker):
    mouse(picker.shades, QEvent.Type.MouseMove, 50, 50, Qt.MouseButton.NoButton)
    mouse(picker.shades, QEvent.Type.MouseButtonPress, 50, 50, Qt.MouseButton.RightButton)
    mouse(picker.shades, QEvent.Type.MouseButtonRelease, 50, 50, Qt.MouseButton.RightButton)
    assert picker.picks == [] and picker.color() == "#2196f3"


def test_a_drag_past_the_edge_stops_at_the_edge(picker):
    picker.show_color("#ff0000")
    mouse(picker.shades, QEvent.Type.MouseButtonPress, 100, 50)
    mouse(picker.shades, QEvent.Type.MouseMove, 5000, -5000)
    mouse(picker.shades, QEvent.Type.MouseButtonRelease, 5000, -5000)
    assert picker.picks == ["#ff0000"]


def test_the_hue_bar_changes_the_hue_and_keeps_the_shade(picker):
    width = SHADES_SIZE[0]
    picker.show_color("#ff0000")
    click(picker.hues, (width - 1) / 3, HUES_HEIGHT / 2)  # a third along: green
    click(picker.hues, (width - 1) * 2 / 3, HUES_HEIGHT / 2)  # two thirds: blue
    click(picker.hues, width - 1, HUES_HEIGHT / 2)  # the end: red again
    green, blue, red = (QColor(pick) for pick in picker.picks)
    assert green.green() == 255 and green.red() <= 2 and green.blue() <= 2
    assert blue.blue() == 255 and blue.red() <= 2 and blue.green() <= 2
    assert red.red() == 255 and red.green() == 0 and red.blue() <= 6  # the last red before the bar starts over
    assert picker.hues.hue == pytest.approx(MAX_HUE)


@pytest.mark.parametrize(("typed", "picked"), [("#12AB34", "#12ab34"), ("7c4dff", "#7c4dff"), ("#000000", "#000000")])
def test_a_typed_colour_is_picked_with_enter(picker, typed, picked):
    picker.field.setText(typed)
    picker.field.returnPressed.emit()
    assert picker.picks == [picked] and picker.field.text() == picked == picker.color()


@pytest.mark.parametrize("typed", ["", "red", "#12345", "#12345g", "12 34 5"])
def test_what_isnt_a_colour_is_replaced_by_the_one_shown(picker, typed):
    picker.field.setText(typed)
    picker.field.returnPressed.emit()
    assert picker.picks == [] and picker.field.text() == "#2196f3"


def test_the_field_takes_no_more_than_a_colour(picker):
    picker.field.clear()
    picker.field.insert("#1234567890")
    assert picker.field.text() == "#123456"


def test_a_grey_keeps_the_hue_the_window_was_on(picker):
    picker.show_color("#808080")
    assert picker.color() == "#808080" and picker.hues.hue == pytest.approx(QColor("#2196f3").hueF())


def test_what_it_paints_is_the_colour_it_says(picker):
    width, height = SHADES_SIZE
    picker.show_color("#00ff00")
    picker.show()
    assert grabbed(picker.shades, width - 2, 1).green() > 240 and grabbed(picker.shades, width - 2, 1).red() < 20
    assert grabbed(picker.shades, 1, height - 1).lightness() < 10  # the bottom is black
    left, middle = grabbed(picker.hues, 1, 2), grabbed(picker.hues, int((width - 1) / 3) + 8, 2)
    assert left.red() > 240 and left.green() < 20 and middle.green() > 240 and middle.red() < 60


def test_the_title_follows_the_language(picker):
    set_language("Deutsch")
    picker.retranslate()
    deutsch = _TRANSLATIONS["Deutsch"]["Pick color"]
    assert picker._title_lbl.text() == deutsch and picker.windowTitle() == f"Vitralis — {deutsch}"


@pytest.mark.property
@given(st.integers(min_value=0, max_value=0xFFFFFF))
def test_any_colour_typed_is_the_colour_picked(qapp, colour):
    """The hue and the shade a colour is shown at are rounded; the colour picked is still the one typed."""
    typed = f"#{colour:06x}"
    picker = ColorWindow("#000000")
    picks = []
    picker.picked.connect(picks.append)
    picker.field.setText(typed)
    picker.field.returnPressed.emit()
    assert picks == [typed] and picker.field.text() == typed
    shown = QColor(picker.color())
    assert max(abs(shown.red() - QColor(typed).red()), abs(shown.green() - QColor(typed).green())) <= 2
    picker.deleteLater()
