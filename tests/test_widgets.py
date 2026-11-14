#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.950598
Revised: 2026/11/14 12:31:22.950598

What Vitralis's small windows share, on the offscreen ``QApplication``: the panel that drags from anywhere,
closes with Esc and says when it closed, and the text field whose right-click menu speaks the UI language and
greys out what would do nothing.
"""

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QGuiApplication, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from vitralis.translations import _TRANSLATIONS, set_language
from vitralis.widgets import EDIT_MENU, Divider, LineEdit, Panel

pytestmark = pytest.mark.ui
LANGUAGES = list(_TRANSLATIONS)


@pytest.fixture
def panel(qapp):
    made = Panel("Vitralis — test")
    made.resize(200, 120)
    made.closes = []
    made.closed.connect(lambda: made.closes.append(1))
    yield made
    made.close()
    made.deleteLater()


def mouse(widget, kind, x: int, y: int) -> None:
    """A left-button event at ``(x, y)`` of ``widget``, which is at its own ``pos()`` on the screen."""
    local = QPointF(x, y)
    held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    event = QMouseEvent(
        kind, local, QPointF(widget.pos()) + local, Qt.MouseButton.LeftButton, held, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(widget, event)


def test_a_panel_is_a_frameless_window_on_top_with_its_title(panel):
    flags = panel.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint and flags & Qt.WindowType.WindowStaysOnTopHint
    assert panel.windowTitle() == "Vitralis — test"
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_a_panel_is_dragged_from_anywhere_on_it(panel):
    panel.move(100, 100)
    panel.show()
    mouse(panel, QEvent.Type.MouseButtonPress, 30, 20)
    panel_at = QPoint(100, 100)
    for step in (QPoint(40, 0), QPoint(40, 25)):
        local = QPointF(30, 20)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            local,
            QPointF(panel_at + step) + local,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(panel, event)
    assert panel.pos() == QPoint(140, 125)
    mouse(panel, QEvent.Type.MouseButtonRelease, 30, 20)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(30, 20),
        QPointF(500, 500),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(panel, event)  # let go: it stays
    assert panel.pos() == QPoint(140, 125)


def test_escape_closes_a_panel_and_it_says_so_once(panel):
    panel.show()
    QApplication.setActiveWindow(panel)
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    assert not panel.isVisible() and panel.closes == [1]


def test_a_panel_paints_its_dark_rounded_body(panel):
    panel.show()
    image = panel.grab().toImage()
    ratio = image.devicePixelRatio()
    middle = image.pixelColor(int(100 * ratio), int(60 * ratio))
    assert (middle.red(), middle.green(), middle.blue()) == (18, 18, 22) and middle.alpha() > 200
    assert image.pixelColor(0, 0).alpha() == 0  # the rounded corner stays clear


def test_a_divider_is_a_hairline(qapp):
    line = Divider()
    assert line.height() == 1
    line.deleteLater()


# --- the text field's menu ----------------------------------------------------------------------------------


@pytest.fixture
def field(qapp):
    made = LineEdit()
    yield made
    made.deleteLater()


def entries(field) -> dict[str, bool]:
    """The menu's entries by text, each with whether it can be chosen."""
    menu = field.edit_menu()
    found = {action.text(): action.isEnabled() for action in menu.actions() if not action.isSeparator()}
    menu.deleteLater()
    return found


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "English"])
def test_every_entry_is_translated(language):
    for key in EDIT_MENU:
        assert _TRANSLATIONS[language].get(key), f"{language} lacks {key!r}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_menu_speaks_the_ui_language(field, language):
    """Regression guard: Qt's own menu (Undo, Cut, Copy…) stayed English in every language."""
    set_language(language)
    assert list(entries(field)) == [_TRANSLATIONS[language].get(key, key) for key in EDIT_MENU]


def test_an_empty_field_offers_only_paste_when_there_is_something_to_paste(field):
    QGuiApplication.clipboard().setText("BRN-79YN-44XQ-W025-377Z")
    assert entries(field) == {"Cut": False, "Copy": False, "Paste": True, "Select all": False}
    QGuiApplication.clipboard().clear()
    assert entries(field)["Paste"] is False


def choose(field, entry: str) -> None:
    """Right-click the field and choose ``entry``, as the menu is built at that moment."""
    menu = field.edit_menu()
    {action.text(): action for action in menu.actions()}[entry].trigger()
    menu.deleteLater()


def test_a_selection_can_be_cut_and_copied_and_the_entries_do_it(field):
    QGuiApplication.clipboard().clear()
    field.setText("review")
    assert entries(field) == {"Cut": False, "Copy": False, "Paste": False, "Select all": True}
    choose(field, "Select all")
    assert field.selectedText() == "review"
    assert entries(field)["Cut"] and entries(field)["Copy"]
    choose(field, "Copy")
    assert QGuiApplication.clipboard().text() == "review" and field.text() == "review"
    choose(field, "Cut")
    assert field.text() == ""
    choose(field, "Paste")
    assert field.text() == "review"
    field.clear()
    choose(field, "Cut")  # greyed out: choosing it does nothing
    assert QGuiApplication.clipboard().text() == "review"


def test_a_field_that_cant_be_written_offers_no_cut_or_paste(field):
    QGuiApplication.clipboard().setText("x")
    field.setText("review")
    field.selectAll()
    field.setReadOnly(True)
    assert entries(field) == {"Cut": False, "Copy": True, "Paste": False, "Select all": True}
    field.setReadOnly(False)
    field.setEnabled(False)
    assert entries(field)["Paste"] is False


def test_a_right_click_pops_the_menu_up(field, qapp):
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import QMenu

    field.show()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), field.mapToGlobal(QPoint(5, 5)))
    QApplication.sendEvent(field, event)
    menus = field.findChildren(QMenu)
    assert len(menus) == 1 and menus[0].isVisible()
    menus[0].close()
