#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.471868
Revised: 2026/11/14 12:31:26.457159

The real toolbar driving real canvases and captures on the offscreen ``QApplication`` (its system-wide hooks
replaced by inert stand-ins, as in ``test_toolbar``): modes, Esc, quitting once, undo across screens, the tool,
colour, size and position it remembers, every label following the language, and the Snapshots window with its
failures said in words.
"""

import json
import logging
import threading

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QCloseEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel

import vitralis.persistence as persistence
import vitralis.settings as settings_module
from tests.conftest import wait_until
from tests.test_toolbar import InertThread
from vitralis import snapshots as snapshots_module
from vitralis import toolbar as toolbar_module
from vitralis.canvas import Canvas, DrawCapture
from vitralis.models import Stroke, Tool
from vitralis.persistence import SnapshotError, flush_writes, forget_strokes, list_snapshots, load_strokes_for
from vitralis.snapshots import (
    SNAPSHOT_DELETE_FAILED,
    SNAPSHOT_LOAD_FAILED,
    SNAPSHOT_SAVE_FAILED,
    SnapshotWindow,
)
from vitralis.styles import PALETTE, SIZES
from vitralis.toolbar import DEFAULT_SIZE, Toolbar
from vitralis.translations import _TRANSLATIONS, set_language

pytestmark = pytest.mark.ui
LEFT = QRect(0, 0, 300, 200)
RIGHT = QRect(300, 0, 300, 200)


def stroke(created: float, y: float = 10.0) -> Stroke:
    return Stroke("LINE", "#ff0000", 3, [[10.0, y], [100.0, y]], created=created)


@pytest.fixture
def overlay(qapp, icons, monkeypatch):
    """A toolbar over two screens' canvases and captures; ``build()`` makes another on the same canvases."""
    monkeypatch.setattr(toolbar_module, "GlobalHotkeyThread", InertThread)
    monkeypatch.setattr(toolbar_module, "GlobalMouseWheelThread", InertThread)
    quits = []
    monkeypatch.setattr(qapp, "quit", lambda: quits.append(1), raising=False)
    canvases = [Canvas(LEFT), Canvas(RIGHT)]
    bars: list[Toolbar] = []
    captures = [
        DrawCapture(canvas, geo, stop_active=lambda: bars[-1].stop_modes())
        for canvas, geo in zip(canvases, (LEFT, RIGHT), strict=True)
    ]

    def build() -> Toolbar:
        bars.append(Toolbar(canvases, captures))
        return bars[-1]

    class Overlay:
        pass

    made = Overlay()
    made.build, made.canvases, made.captures, made.quits = build, canvases, captures, quits
    made.bar = build()
    yield made
    for bar in bars:
        bar.close()
        bar.deleteLater()
    for widget in (*captures, *canvases):
        widget.close()
        widget.deleteLater()


def foreground(monkeypatch, window) -> None:
    """Make ``window`` (``None`` for another app's) what Windows says is in the foreground."""
    handle = 0 if window is None else int(window.winId())
    user32 = type("User32", (), {"GetForegroundWindow": staticmethod(lambda: handle)})
    monkeypatch.setattr(toolbar_module.ctypes, "windll", type("Windll", (), {"user32": user32}), raising=False)


def saved_toolbar() -> dict:
    assert flush_writes(5)
    return json.loads(settings_module.SETTINGS_FILE.read_text(encoding="utf-8"))["toolbar"]


# --- start --------------------------------------------------------------------------------------------------


def test_a_first_start_draws_with_the_pen_the_first_colour_and_the_shown_size(overlay):
    """Regression guard: the canvases used to draw 3 px wide while the toolbar showed 5."""
    bar = overlay.bar
    assert bar._size_lbl.text() == str(DEFAULT_SIZE)
    for canvas in overlay.canvases:
        assert (canvas.active_tool, canvas.active_color, canvas.active_width) == (Tool.PEN, PALETTE[0], DEFAULT_SIZE)
    assert bar._tool_btns[Tool.PEN].isChecked() and bar._swatch_btns[0].isChecked()
    assert flush_writes(5) and not settings_module.SETTINGS_FILE.exists()  # opening the toolbar saves nothing


# --- modes and Esc ------------------------------------------------------------------------------------------


def test_each_mode_shows_the_captures_and_turns_the_others_off(overlay):
    bar = overlay.bar
    bar._toggle_drawing(True)
    assert bar._drawing_active and bar.mode_active and all(c.isVisible() for c in overlay.captures)
    assert bar._draw_btn.text() == "Drawing…"
    bar._toggle_pan(True)
    assert bar._pan_active and not bar._drawing_active and all(c.pan_mode for c in overlay.captures)
    assert bar._pan_btn.text() == "Panning…" and bar._draw_btn.text() == "Draw"
    bar._toggle_delete(True)
    assert bar._delete_active and not bar._pan_active
    assert all(c.delete_mode and not c.pan_mode for c in overlay.captures)
    bar._toggle_drawing(True)
    assert not bar._delete_active and not any(c.delete_mode for c in overlay.captures)
    bar.stop_modes()
    assert not bar.mode_active and not any(c.isVisible() for c in overlay.captures)


def test_the_mode_buttons_toggle_their_mode(overlay):
    bar = overlay.bar
    for button, active in (
        (bar._draw_btn, lambda: bar._drawing_active),
        (bar._pan_btn, lambda: bar._pan_active),
        (bar._del_btn, lambda: bar._delete_active),
    ):
        button.click()
        assert active()
        button.click()
        assert not active()


def test_escape_leaves_the_mode_and_only_quits_when_idle(overlay):
    """Regression guard: with the toolbar focused, Esc while drawing used to quit Vitralis."""
    bar = overlay.bar
    bar._toggle_drawing(True)
    bar._esc()
    assert not bar.mode_active and overlay.quits == []
    bar._esc()
    assert overlay.quits == [1]


def test_escape_closes_the_topmost_panel_before_anything_else(overlay):
    bar = overlay.bar
    bar.open_settings()
    bar._open_snapshots()
    bar._open_info()
    bar._toggle_drawing(True)
    for remaining in (2, 1, 0):
        bar._esc()
        panels = [w for w in (bar._settings_win, bar._snapshot_win, bar._info_win) if w is not None]
        assert len(panels) == remaining and bar._drawing_active and overlay.quits == []
    bar._esc()
    assert not bar._drawing_active and overlay.quits == []


def test_escape_closes_the_window_last_used_not_a_fixed_one(overlay):
    """Regression guard: the order was fixed (About, Snapshots, Settings) whichever was on top."""
    bar = overlay.bar
    bar._open_info()
    bar.open_settings()  # opened last: on top
    bar._esc()
    assert bar._settings_win is None and bar._info_win is not None
    bar.open_settings()
    bar._open_info()  # already open: brought to the front again
    bar._esc()
    assert bar._info_win is None and bar._settings_win is not None
    bar._open_snapshots()
    bar._on_window_focused(bar._settings_win.windowHandle())  # the user clicked the Settings window
    bar._on_window_focused(None)  # the focus left Vitralis: the order stays
    bar._esc()
    assert bar._settings_win is None and bar._snapshot_win is not None


def test_quitting_asks_the_app_once(overlay):
    overlay.bar.quit()
    overlay.bar.quit()
    assert overlay.quits == [1]


def test_hiding_with_the_focus_key_leaves_the_mode(overlay, monkeypatch):
    """Regression guard: the toolbar used to come back saying "Drawing…" with its captures hidden."""
    bar = overlay.bar
    bar.show()
    bar._toggle_drawing(True)
    foreground(monkeypatch, bar)
    bar._toggle_focus()
    assert not bar.isVisible() and not bar.mode_active and bar._draw_btn.text() == "Draw"
    assert not any(c.isVisible() for c in overlay.captures)


def test_a_right_click_on_a_capture_leaves_the_mode(overlay):
    overlay.bar._toggle_delete(True)
    spot = QPointF(20, 20)
    click = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        spot,
        spot,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(overlay.captures[0], click)
    assert not overlay.bar.mode_active and not any(c.isVisible() for c in overlay.captures)


def test_starting_a_mode_shows_a_hidden_overlay_and_hiding_it_leaves_the_mode(overlay):
    """Regression guard: with the drawings hidden, a mode still started, and what was drawn was saved unseen."""
    bar = overlay.bar
    for canvas in overlay.canvases:
        canvas.show()
    bar._toggle_visibility(True)
    for start in (bar._toggle_drawing, bar._toggle_pan, bar._toggle_delete):
        start(True)
        assert all(c.isVisible() for c in overlay.canvases) and not bar._vis_btn.isChecked() and bar.mode_active
        bar._toggle_visibility(True)
        assert not bar.mode_active and not any(c.isVisible() for c in (*overlay.canvases, *overlay.captures))
    assert saved_toolbar()["hidden"] is True


def test_each_mode_has_its_cursor_over_the_screen(overlay):
    bar = overlay.bar
    for start, cursor in (
        (bar._toggle_pan, Qt.CursorShape.OpenHandCursor),
        (bar._toggle_delete, Qt.CursorShape.ForbiddenCursor),
        (bar._toggle_drawing, Qt.CursorShape.CrossCursor),
    ):
        start(True)
        assert all(capture.cursor().shape() == cursor for capture in overlay.captures)


def test_turning_off_a_mode_that_isnt_on_leaves_the_one_that_is(overlay):
    bar = overlay.bar
    bar._toggle_pan(True)
    bar.stop_drawing()
    bar.stop_delete()
    assert bar._pan_active and all(c.pan_mode for c in overlay.captures)
    bar.stop_pan()
    assert not bar.mode_active


def test_hiding_the_toolbar_from_the_tray_leaves_the_mode(overlay):
    """Regression guard: the captures went on taking every click, with no toolbar and no shortcut to get out."""
    bar = overlay.bar
    bar.show()
    bar._toggle_drawing(True)
    bar.hide_toolbar()
    assert not bar.isVisible() and not bar.mode_active and not any(c.isVisible() for c in overlay.captures)
    bar.show_toolbar()
    assert bar.isVisible() and bar._draw_btn.text() == "Draw"


# --- the keys the tooltips name -----------------------------------------------------------------------------------


def tips(bar) -> dict[str, str]:
    return {
        "quit": bar._quit_btn.toolTip(),
        "draw": bar._draw_btn.toolTip(),
        "pan": bar._pan_btn.toolTip(),
        "delete": bar._del_btn.toolTip(),
        "minus": bar._minus_btn.toolTip(),
        "plus": bar._plus_btn.toolTip(),
        "undo": bar._undo_btn.toolTip(),
        "clear": bar._clear_btn.toolTip(),
        "hide": bar._vis_btn.toolTip(),
        "pen": bar._tool_btns[Tool.PEN].toolTip(),
        "ellipse": bar._tool_btns[Tool.ELLIPSE].toolTip(),
        "dot": bar._focus_dot.toolTip(),
    }


def test_the_tooltips_name_the_default_keys(overlay, monkeypatch):
    foreground(monkeypatch, None)
    overlay.bar._refresh_hints()
    assert tips(overlay.bar) == {
        "quit": "Quit  [ESC / CTRL+Q]",
        "draw": "Activate drawing mode  [D]  ·  Focus: F8",
        "pan": "Drag to shift all drawings on the overlay  [G]",
        "delete": "Click near any stroke to remove it  [X]",
        "minus": "Decrease stroke size  [[]",
        "plus": "Increase stroke size  []]",
        "undo": "Undo  [Z]",
        "clear": "Clear all  [DELETE]",
        "hide": "Hide overlay  [H]",
        "pen": "Pen  [P]",
        "ellipse": "Ellipse  [O]",
        "dot": "Unfocused  ·  F8 to focus",
    }


def test_the_tooltips_follow_the_shortcuts_set_in_settings(overlay, monkeypatch):
    """Regression guard: with focus on F9 and draw on K, the tooltips still said F8 and D."""
    foreground(monkeypatch, None)
    bar = overlay.bar
    changed = {
        **settings_module.DEFAULT_SHORTCUTS,
        "focus_toggle": "f9",
        "draw": "k",
        "undo": "ctrl+z",
        "tool_pen": "1",
    }
    bar._restart_global_hotkey(changed)
    now = tips(bar)
    assert now["draw"] == "Activate drawing mode  [K]  ·  Focus: F9" and now["dot"] == "Unfocused  ·  F9 to focus"
    assert now["undo"] == "Undo  [CTRL+Z]" and now["pen"] == "Pen  [1]" and now["pan"].endswith("[G]")
    bar._toggle_visibility(True)
    assert bar._vis_btn.toolTip() == "Show overlay  [H]"


def test_an_action_without_a_shortcut_has_a_tooltip_without_a_key(overlay, monkeypatch):
    foreground(monkeypatch, None)
    bar = overlay.bar
    none = {**settings_module.DEFAULT_SHORTCUTS, "focus_toggle": "", "draw": "", "quit": "", "hide": "", "clear": ""}
    bar._restart_global_hotkey(none)
    now = tips(bar)
    assert now["draw"] == "Activate drawing mode" and now["quit"] == "Quit  [ESC]" and now["dot"] == "Unfocused"
    assert now["hide"] == "Hide overlay" and now["clear"] == "Clear all"
    foreground(monkeypatch, bar)
    bar._poll_focus()
    assert bar._focus_dot.toolTip() == "Focused"


def test_the_tooltips_are_in_the_ui_language_with_the_users_keys(overlay, monkeypatch):
    foreground(monkeypatch, None)
    bar = overlay.bar
    bar._restart_global_hotkey({**settings_module.DEFAULT_SHORTCUTS, "focus_toggle": "f9"})
    set_language("Galego")
    bar.retranslate()
    galego = _TRANSLATIONS["Galego"]
    assert bar._draw_btn.toolTip() == f"{galego['Activate drawing mode']}  [D]  ·  Foco: F9"
    assert bar._focus_dot.toolTip() == "Sen foco  ·  F9 para enfocar"
    assert bar._tool_btns[Tool.RECT].toolTip() == f"{galego['Rectangle']}  [R]"
    assert bar._quit_btn.toolTip() == f"{galego['Quit']}  [ESC / CTRL+Q]"


# --- what is greyed out ----------------------------------------------------------------------------------------


def test_undo_and_clear_are_greyed_out_until_something_is_drawn(overlay):
    bar, (left, right) = overlay.bar, overlay.canvases
    assert not bar._undo_btn.isEnabled() and not bar._clear_btn.isEnabled()
    right.load([stroke(1.0)])
    assert bar._undo_btn.isEnabled() and bar._clear_btn.isEnabled()
    bar._undo()
    assert not bar._undo_btn.isEnabled() and not bar._clear_btn.isEnabled()
    left.load([stroke(1.0), stroke(2.0)])
    bar._clear_btn.click()
    assert not bar._undo_btn.isEnabled() and left.strokes == []


def test_undo_and_clear_follow_the_canvases_of_new_screens(overlay, qapp):
    """A monitor plugged in: the canvases are rebuilt, and the buttons must follow the new ones."""
    bar = overlay.bar
    replaced = Canvas(RIGHT)
    overlay.canvases[1].deleteLater()
    overlay.canvases[1] = replaced
    bar.sync_canvases()
    bar.sync_canvases()  # twice: still told once per change
    assert not bar._undo_btn.isEnabled()
    told = []
    replaced.changed.connect(lambda: told.append(bar._undo_btn.isEnabled()))
    replaced.load([stroke(1.0)])
    assert told == [True] and replaced.active_color == bar._color
    replaced.deleteLater()


def test_the_size_buttons_are_greyed_out_at_the_ends(overlay):
    bar = overlay.bar
    assert bar._minus_btn.isEnabled() and bar._plus_btn.isEnabled()
    for _ in range(len(SIZES)):
        bar._size_down()
    assert not bar._minus_btn.isEnabled() and bar._plus_btn.isEnabled()
    for _ in range(len(SIZES)):
        bar._plus_btn.click()
    assert bar._minus_btn.isEnabled() and not bar._plus_btn.isEnabled()
    settings_module.SettingsManager().set_toolbar_state(size=SIZES[0])
    assert not overlay.build()._minus_btn.isEnabled()  # as left: greyed out from the start


# --- where the toolbar's windows are left ------------------------------------------------------------------------


def test_a_window_opens_beside_the_toolbar_and_saves_nothing_until_it_is_dragged(overlay, qapp):
    bar = overlay.bar
    area = qapp.primaryScreen().availableGeometry()
    bar.move(area.x() + 40, area.y() + 40)
    bar._open_info()
    beside = QPoint(bar.frameGeometry().right() + toolbar_module.PANEL_GAP, bar.frameGeometry().top())
    assert bar._info_win.pos() == beside
    bar._info_win.close()
    assert flush_writes(5) and not settings_module.SETTINGS_FILE.exists()


def test_where_a_window_was_dragged_to_is_remembered_from_the_toolbars_corner(overlay, qapp):
    """The windows keep their place beside the toolbar: moved with it, and still there at the next start."""
    bar = overlay.bar
    area = qapp.primaryScreen().availableGeometry()
    bar.move(area.x() + 40, area.y() + 40)
    bar._open_snapshots()
    bar._snapshot_win.move(bar.pos() + QPoint(30, 200))
    bar._snapshot_win.close()
    assert saved_toolbar()["panels"] == {"snapshots": [30, 200]}
    bar.move(area.x() + 100, area.y() + 60)
    bar._open_snapshots()
    assert bar._snapshot_win.pos() == bar.pos() + QPoint(30, 200)
    bar._snapshot_win.close()  # not moved since: nothing new to save
    again = overlay.build()
    again.move(area.x() + 10, area.y() + 10)
    again.open_settings()
    again._open_snapshots()
    assert again._snapshot_win.pos() == again.pos() + QPoint(30, 200)
    assert again._settings_win.pos().x() == again.frameGeometry().right() + toolbar_module.PANEL_GAP


def test_a_window_left_where_no_screen_shows_it_any_more_opens_beside_the_toolbar(overlay, qapp):
    settings_module.SettingsManager().set_toolbar_state(panels={"info": [-90_000, -90_000]})
    bar = overlay.build()
    area = qapp.primaryScreen().availableGeometry()
    bar.move(area.x() + 40, area.y() + 40)
    bar._open_info()
    assert bar._info_win.pos().x() == bar.frameGeometry().right() + toolbar_module.PANEL_GAP


def test_the_windows_titles_are_in_the_ui_language(overlay):
    """Regression guard: "Vitralis — Settings" (shown in the taskbar and Alt+Tab) was English only."""
    settings_module.SettingsManager().set_language("Español")
    bar = overlay.build()
    bar.open_settings()
    bar._open_snapshots()
    bar._open_info()
    bar._pick_custom_color()
    español = _TRANSLATIONS["Español"]
    titles = {name: window.windowTitle() for name, window in bar._panels.items()}
    assert titles == {
        "settings": f"Vitralis — {español['Settings']}",
        "snapshots": f"Vitralis — {español['Snapshots']}",
        "info": f"Vitralis — {español['About']}",
        "color": f"Vitralis — {español['Pick color']}",
    }
    bar._settings_win.findChild(QComboBox).setCurrentText("Deutsch")  # picked in Settings
    deutsch = _TRANSLATIONS["Deutsch"]
    assert bar._settings_win.windowTitle() == f"Vitralis — {deutsch['Settings']}"
    assert bar._color_win.windowTitle() == f"Vitralis — {deutsch['Pick color']}"
    assert bar._info_win.windowTitle() == f"Vitralis — {deutsch['About']}"


# --- tools, colours, size -----------------------------------------------------------------------------------


def test_the_tool_colour_and_size_reach_every_canvas_and_are_remembered(overlay):
    bar = overlay.bar
    bar._tool_btns[Tool.ARROW].click()
    bar._swatch_btns[7].click()
    bar._plus_btn.click()
    for canvas in overlay.canvases:
        assert (canvas.active_tool, canvas.active_color, canvas.active_width) == (Tool.ARROW, PALETTE[7], 6)
    assert saved_toolbar() == {"tool": "ARROW", "color": PALETTE[7], "size": 6}
    again = overlay.build()
    assert again._tool_btns[Tool.ARROW].isChecked() and again._swatch_btns[7].isChecked()
    assert again._size_lbl.text() == "6" and not again._swatch_btns[0].isChecked()
    assert overlay.canvases[0].active_tool is Tool.ARROW


def test_the_size_stops_at_both_ends(overlay):
    bar = overlay.bar
    for _ in range(len(SIZES) + 3):
        bar._size_down()
    assert bar._size_lbl.text() == str(SIZES[0]) and overlay.canvases[0].active_width == SIZES[0]
    for _ in range(len(SIZES) + 3):
        bar._size_up()
    assert bar._size_lbl.text() == str(SIZES[-1]) and overlay.canvases[1].active_width == SIZES[-1]


def test_a_saved_size_the_toolbar_doesnt_offer_falls_back(overlay):
    settings_module.SettingsManager().set_toolbar_state(size=150)
    assert overlay.build()._size_lbl.text() == str(DEFAULT_SIZE)


def test_a_custom_colour_is_picked_in_vitraliss_own_window_and_remembered(overlay):
    """The picker is one of Vitralis's windows (in its language, dark, frameless), not the system's dialog."""
    set_language("Galego")
    overlay.bar._custom_btn.click()
    picker = overlay.bar._color_win
    assert picker.isVisible() and picker._title_lbl.text() == _TRANSLATIONS["Galego"]["Pick color"]
    assert picker.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert picker.color() == PALETTE[0] == picker.field.text()
    picker.field.setText("#123456")
    picker.field.returnPressed.emit()
    assert all(c.active_color == "#123456" for c in overlay.canvases)
    assert not any(button.isChecked() for button in overlay.bar._swatch_btns)
    assert saved_toolbar()["color"] == "#123456"
    again = overlay.build()
    assert again._color == "#123456" and not any(button.isChecked() for button in again._swatch_btns)


def test_a_colour_picker_closed_without_picking_changes_nothing(overlay):
    overlay.bar._custom_btn.click()
    overlay.bar._custom_btn.click()  # already open: brought to the front, not built again
    picker = overlay.bar._color_win
    picker.close()
    assert overlay.bar._color_win is None
    assert overlay.canvases[0].active_color == PALETTE[0] and overlay.bar._swatch_btns[0].isChecked()
    assert flush_writes(5) and not settings_module.SETTINGS_FILE.exists()


def test_the_wheel_cycles_the_palette_only_while_vitralis_has_the_focus(overlay, monkeypatch):
    bar = overlay.bar
    foreground(monkeypatch, None)
    bar._on_global_wheel(1)
    assert bar._color == PALETTE[0]
    foreground(monkeypatch, bar)
    bar._on_global_wheel(1)
    assert bar._color == PALETTE[1] and bar._swatch_btns[1].isChecked()
    bar._on_global_wheel(-1)
    bar._on_global_wheel(-1)
    assert bar._color == PALETTE[-1]
    bar._select_color("#123456", None)
    bar._on_global_wheel(1)  # from a custom colour the wheel starts at the palette's beginning
    assert bar._color == PALETTE[1]


def test_the_wheel_over_one_of_the_toolbars_windows_leaves_the_colour_alone(overlay, monkeypatch):
    """Regression guard: scrolling the snapshot list or the language box also changed the pen's colour."""
    bar = overlay.bar
    bar._open_snapshots()
    bar.open_settings()
    for window in (bar._snapshot_win, bar._settings_win):
        foreground(monkeypatch, window)
        assert bar._is_vitralis_focused()  # the focus dot still counts it as Vitralis
        bar._on_global_wheel(1)
    assert bar._color == PALETTE[0]
    foreground(monkeypatch, overlay.captures[1])  # while drawing, the wheel is the palette's
    bar._on_global_wheel(1)
    assert bar._color == PALETTE[1]
    assert flush_writes(5) and saved_toolbar() == {"color": PALETTE[1]}


# --- undo, clear, hide --------------------------------------------------------------------------------------


def test_undo_takes_back_only_the_latest_stroke_whichever_screen_it_is_on(overlay):
    """Regression guard: Undo used to take one stroke off every screen at once."""
    left, right = overlay.canvases
    left.load([stroke(1.0), stroke(4.0)])
    right.load([stroke(2.0), stroke(3.0)])
    overlay.bar._undo_btn.click()
    assert [s.created for s in left.strokes] == [1.0] and [s.created for s in right.strokes] == [2.0, 3.0]
    overlay.bar._undo()
    overlay.bar._undo()
    assert [s.created for s in left.strokes] == [1.0] and right.strokes == []
    overlay.bar._undo()
    overlay.bar._undo()  # nothing left: nothing happens
    assert left.strokes == [] and right.strokes == []


def test_undo_on_strokes_without_a_time_takes_one_at_a_time(overlay):
    left, right = overlay.canvases
    left.load([stroke(0.0)])
    right.load([stroke(0.0)])
    overlay.bar._undo()
    assert len(left.strokes) + len(right.strokes) == 1


def test_clear_empties_every_screen(overlay):
    for canvas in overlay.canvases:
        canvas.load([stroke(1.0)])
    overlay.bar._clear_btn.click()
    assert all(canvas.strokes == [] for canvas in overlay.canvases)
    forget_strokes()
    assert load_strokes_for(LEFT) == [] and load_strokes_for(RIGHT) == []


def test_hiding_the_overlay_hides_every_canvas_and_showing_brings_them_back(overlay):
    bar = overlay.bar
    for canvas in overlay.canvases:
        canvas.show()
    bar._toggle_visibility(True)
    assert not any(c.isVisible() for c in overlay.canvases) and bar._vis_btn.toolTip() == "Show overlay  [H]"
    bar.sync_canvases()  # canvases rebuilt while hidden stay hidden
    assert not any(c.isVisible() for c in overlay.canvases)
    bar._vis_btn.click()
    assert all(c.isVisible() for c in overlay.canvases) and bar._vis_btn.toolTip() == "Hide overlay  [H]"


def test_a_hidden_overlay_is_still_hidden_at_the_next_start_and_the_button_says_so(overlay):
    for canvas in overlay.canvases:
        canvas.show()
    overlay.bar._vis_btn.click()
    assert saved_toolbar()["hidden"] is True
    for canvas in overlay.canvases:
        canvas.show()  # as a new start builds them
    again = overlay.build()
    assert not any(c.isVisible() for c in overlay.canvases)
    assert again._vis_btn.isChecked() and again._vis_btn.toolTip() == "Show overlay  [H]"
    again._vis_btn.click()
    assert all(c.isVisible() for c in overlay.canvases) and saved_toolbar()["hidden"] is False
    assert not overlay.build()._vis_btn.isChecked()


def test_restoring_the_hidden_overlay_writes_nothing(overlay, monkeypatch):
    settings_module.SettingsManager().set_toolbar_state(hidden=True)
    writes = []
    monkeypatch.setattr(settings_module, "write_in_background", lambda *a, **k: writes.append(a))
    assert overlay.build()._vis_btn.isChecked() and writes == []


# --- position -----------------------------------------------------------------------------------------------


def test_a_first_start_goes_to_the_default_spot(overlay):
    overlay.bar.place(QPoint(20, 20))
    assert overlay.bar.pos() == QPoint(20, 20)


def test_where_the_toolbar_was_dragged_to_is_remembered(overlay, qapp):
    area = qapp.primaryScreen().availableGeometry()
    spot = QPoint(area.x() + 120, area.y() + 90)
    bar = overlay.bar
    bar._dragging = True
    bar.move(spot)
    bar.mouseReleaseEvent(None)
    assert saved_toolbar()["position"] == [spot.x(), spot.y()]
    again = overlay.build()
    again.place(QPoint(20, 20))
    assert again.pos() == spot


def test_a_release_without_a_drag_saves_nothing(overlay):
    overlay.bar.mouseReleaseEvent(None)
    assert flush_writes(5) and not settings_module.SETTINGS_FILE.exists()


def test_a_saved_spot_no_screen_shows_any_more_falls_back_to_the_default(overlay):
    settings_module.SettingsManager().set_toolbar_state(position=[-50_000, -50_000])
    again = overlay.build()
    again.place(QPoint(20, 20))
    assert again.pos() == QPoint(20, 20)


# --- language -----------------------------------------------------------------------------------------------


def test_a_language_change_relabels_the_active_mode_and_the_hidden_overlay(overlay):
    """Regression guard: "Drawing…" and the Show/Hide overlay tooltip used to stay in the old language."""
    bar = overlay.bar
    bar._toggle_drawing(True)
    seen = []
    bar.language_changed.connect(lambda: seen.append(1))
    set_language("Galego")
    bar._on_language_changed("Galego")
    galego = _TRANSLATIONS["Galego"]
    assert bar._draw_btn.text() == galego["Drawing…"] and bar._pan_btn.text() == galego["Pan"]
    assert bar._vis_btn.toolTip() == f"{galego['Hide overlay']}  [H]"
    bar._toggle_visibility(True)
    assert bar._vis_btn.toolTip() == f"{galego['Show overlay']}  [H]"
    set_language("Deutsch")
    bar._on_language_changed("Deutsch")
    deutsch = _TRANSLATIONS["Deutsch"]
    assert bar._vis_btn.toolTip() == f"{deutsch['Show overlay']}  [H]"
    assert bar._undo_btn.toolTip() == f"{deutsch['Undo']}  [Z]" and seen == [1, 1]


def test_a_language_change_reaches_the_open_windows(overlay):
    bar = overlay.bar
    bar._open_snapshots()
    bar._open_info()
    set_language("Deutsch")
    bar._on_language_changed("Deutsch")
    deutsch = _TRANSLATIONS["Deutsch"]
    assert bar._snapshot_win._title_lbl.text() == deutsch["Snapshots"]
    assert deutsch["Version"].upper() in [label.text() for label in bar._info_win.findChildren(QLabel)]


def test_the_open_windows_close_with_the_toolbar(overlay):
    bar = overlay.bar
    bar.open_settings()
    bar._open_snapshots()
    bar._open_info()
    bar._open_info()  # already open: brought to the front, not built again
    windows = [bar._settings_win, bar._snapshot_win, bar._info_win]
    bar.close()
    assert not any(w.isVisible() for w in windows)
    assert bar._settings_win is None and bar._snapshot_win is None and bar._info_win is None


def test_changing_the_shortcuts_restarts_the_focus_hotkey(overlay):
    bar = overlay.bar
    first = bar._hotkey_thread
    bar._restart_global_hotkey({"focus_toggle": "f9", "draw": "k"})
    assert not first.running and bar._hotkey_thread is not first and bar._hotkey_thread.running
    local = len(settings_module.DEFAULT_SHORTCUTS) - 1  # all but the focus key, which isn't Qt's
    assert len(bar._shortcuts) == local
    bar._restart_global_hotkey({**settings_module.DEFAULT_SHORTCUTS, "draw": ""})  # no key: no shortcut
    assert len(bar._shortcuts) == local - 1


# --- snapshots ----------------------------------------------------------------------------------------------


def settle(window: SnapshotWindow) -> None:
    """Let the window's disk work end and its answer reach the UI thread."""
    wait_until(QApplication.instance(), lambda: not window.busy)


@pytest.fixture
def snapshots(overlay):
    window = SnapshotWindow(overlay.canvases)
    settle(window)
    yield window
    settle(window)
    window.close()
    window.deleteLater()


def select(window: SnapshotWindow, *names: str) -> None:
    window._list.clearSelection()
    for row in range(window._list.count()):
        if window._list.item(row).text() in names:
            window._list.item(row).setSelected(True)


def test_a_snapshot_is_saved_listed_loaded_back_and_deleted(overlay, snapshots):
    left, right = overlay.canvases
    left.load([stroke(1.0)])
    right.load([stroke(2.0), stroke(3.0)])
    assert not snapshots._save_btn.isEnabled() and not snapshots._load_btn.isEnabled()
    snapshots._name_edit.setText("review")
    snapshots._save_btn.click()
    settle(snapshots)
    assert list_snapshots() == ["review"] and snapshots._name_edit.text() == ""
    assert [snapshots._list.item(i).text() for i in range(snapshots._list.count())] == ["review"]
    overlay.bar._clear()
    select(snapshots, "review")
    snapshots._load_btn.click()
    settle(snapshots)
    assert [s.created for s in left.strokes] == [1.0] and [s.created for s in right.strokes] == [2.0, 3.0]
    forget_strokes()
    assert load_strokes_for(RIGHT) == right.strokes  # a loaded snapshot is what the next start shows
    snapshots._del_btn.click()
    settle(snapshots)
    assert list_snapshots() == [] and snapshots._list.count() == 0 and not snapshots._error_lbl.isVisibleTo(snapshots)


def test_saving_with_one_snapshot_selected_overwrites_it(overlay, snapshots):
    snapshots._name_edit.setText("review")
    snapshots._save()
    settle(snapshots)
    overlay.canvases[0].load([stroke(5.0)])
    select(snapshots, "review")
    snapshots._save()
    settle(snapshots)
    assert list_snapshots() == ["review"]
    assert [s.created for s in persistence.load_snapshot("review")["0,0"]] == [5.0]


def test_typing_filters_the_list_and_keeps_the_selection(snapshots):
    for name in ("alpha", "beta", "alphabet"):
        snapshots._name_edit.setText(name)
        snapshots._save()
        settle(snapshots)
    select(snapshots, "alphabet")
    snapshots._name_edit.setText("ALPHA")
    shown = [snapshots._list.item(i).text() for i in range(snapshots._list.count())]
    assert shown == ["alpha", "alphabet"]
    assert [item.text() for item in snapshots._list.selectedItems()] == ["alphabet"]


def test_several_snapshots_are_deleted_together_but_not_loaded_or_saved(snapshots):
    for name in ("one", "two", "three"):
        snapshots._name_edit.setText(name)
        snapshots._save()
        settle(snapshots)
    select(snapshots, "one", "two")
    assert (
        snapshots._del_btn.isEnabled() and not snapshots._load_btn.isEnabled() and not snapshots._save_btn.isEnabled()
    )
    snapshots._load()  # more than one selected: nothing to load
    settle(snapshots)
    snapshots._delete()
    settle(snapshots)
    assert list_snapshots() == ["three"]
    snapshots._delete()  # nothing selected: nothing happens
    settle(snapshots)
    snapshots._save()  # no name and nothing selected: nothing happens
    settle(snapshots)
    assert list_snapshots() == ["three"]


def refuse(*args, **kwargs):
    raise SnapshotError("read-only")


def test_a_snapshot_that_cant_be_saved_says_so_and_keeps_the_name(snapshots, monkeypatch):
    snapshots._name_edit.setText("review")
    with monkeypatch.context() as patch:  # only this one patch ends here: the test's data folder stays its own
        patch.setattr(snapshots_module, "save_snapshot", refuse)
        snapshots._save()
        settle(snapshots)
    assert snapshots._error_lbl.text() == SNAPSHOT_SAVE_FAILED and snapshots._error_lbl.isVisibleTo(snapshots)
    assert snapshots._name_edit.text() == "review" and list_snapshots() == []
    snapshots._save()
    settle(snapshots)
    assert list_snapshots() == ["review"]
    assert not snapshots._error_lbl.isVisibleTo(snapshots) and snapshots._error_lbl.text() == ""


def test_a_snapshot_that_cant_be_loaded_says_so_and_leaves_the_drawing(overlay, snapshots, caplog):
    overlay.canvases[0].load([stroke(1.0)])
    (persistence.SNAPSHOTS_DIR / "broken.json").write_text("{not json", encoding="utf-8")
    snapshots._refresh_list()
    settle(snapshots)
    select(snapshots, "broken")
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        snapshots._load()
        settle(snapshots)
    assert snapshots._error_lbl.text() == SNAPSHOT_LOAD_FAILED and caplog.records
    assert [s.created for s in overlay.canvases[0].strokes] == [1.0]


def test_a_snapshot_that_cant_be_deleted_says_so_in_the_ui_language(snapshots, monkeypatch):
    snapshots._name_edit.setText("kept")
    snapshots._save()
    settle(snapshots)
    select(snapshots, "kept")
    monkeypatch.setattr(snapshots_module, "delete_snapshot", refuse)
    snapshots._delete()
    settle(snapshots)
    assert snapshots._error_lbl.text() == SNAPSHOT_DELETE_FAILED and list_snapshots() == ["kept"]
    set_language("Español")
    snapshots.retranslate()
    español = _TRANSLATIONS["Español"]
    assert snapshots._error_lbl.text() == español[SNAPSHOT_DELETE_FAILED]
    assert snapshots._title_lbl.text() == español["Snapshots"] and snapshots._save_btn.text().strip() == español["Save"]


def test_a_snapshot_of_other_screens_changes_only_the_screens_it_has(overlay, snapshots):
    persistence.save_snapshot("left only", {"0,0": [stroke(9.0)]})
    overlay.canvases[1].load([stroke(2.0)])
    snapshots._refresh_list()
    settle(snapshots)
    select(snapshots, "left only")
    snapshots._load()
    settle(snapshots)
    assert [s.created for s in overlay.canvases[0].strokes] == [9.0]
    assert [s.created for s in overlay.canvases[1].strokes] == [2.0]


def keys_to(window: SnapshotWindow, widget) -> None:
    """Make ``window`` the active one with the keyboard on ``widget``, as when the user clicked it."""
    window.show()
    QApplication.setActiveWindow(window)
    widget.setFocus()


def test_enter_in_the_name_field_saves_and_never_loads(overlay, snapshots):
    """Regression guard: a window-wide Return shortcut took the key, so Enter while naming a snapshot loaded
    the selected one over the drawing instead of saving."""
    overlay.canvases[0].load([stroke(1.0)])
    snapshots._name_edit.setText("review")
    snapshots._save()
    settle(snapshots)
    overlay.canvases[0].load([stroke(1.0), stroke(2.0)])
    select(snapshots, "review")
    snapshots._name_edit.setText("review")
    keys_to(snapshots, snapshots._name_edit)
    QTest.keyClick(snapshots._name_edit, Qt.Key.Key_Return)
    settle(snapshots)
    assert [s.created for s in overlay.canvases[0].strokes] == [1.0, 2.0]  # not replaced by the old snapshot
    assert [s.created for s in persistence.load_snapshot("review")["0,0"]] == [1.0, 2.0]  # saved over it


def test_enter_and_delete_in_the_list_load_and_delete_beside_the_toolbars_own_delete(overlay, snapshots):
    """Regression guard: the list's Delete and the toolbar's Clear all (Delete too) cancelled each other."""
    left = overlay.canvases[0]
    overlay.bar.show()  # its shortcuts only work while it shows
    left.load([stroke(1.0)])
    for name in ("one", "two"):
        snapshots._name_edit.setText(name)
        snapshots._save()
        settle(snapshots)
    left.load([stroke(5.0), stroke(6.0)])
    select(snapshots, "one")
    keys_to(snapshots, snapshots._list)
    QTest.keyClick(snapshots._list, Qt.Key.Key_Return)
    settle(snapshots)
    assert [s.created for s in left.strokes] == [1.0]
    QTest.keyClick(snapshots._list, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(snapshots._list.selectedItems()) == 2
    QTest.keyClick(snapshots._list, Qt.Key.Key_Delete)
    settle(snapshots)
    assert list_snapshots() == [] and [s.created for s in left.strokes] == [1.0]  # the drawing wasn't cleared


def test_delete_outside_the_list_is_still_the_toolbars_clear_all(overlay, snapshots):
    left = overlay.canvases[0]
    left.load([stroke(1.0)])
    overlay.bar.show()
    QApplication.setActiveWindow(overlay.bar)
    QTest.keyClick(overlay.bar, Qt.Key.Key_Delete)
    assert left.strokes == []


def test_while_the_disk_is_busy_the_buttons_wait_and_the_ui_thread_doesnt(overlay, snapshots, monkeypatch):
    """A slow disk greys the buttons out until it answers; the click itself returns at once."""
    held, release = threading.Event(), threading.Event()
    real = snapshots_module.save_snapshot

    def slow(name, screens) -> None:
        held.set()
        assert release.wait(5)
        real(name, screens)

    monkeypatch.setattr(snapshots_module, "save_snapshot", slow)
    overlay.canvases[0].load([stroke(1.0)])
    snapshots._name_edit.setText("review")
    snapshots._save_btn.click()  # returns while the disk hasn't answered
    assert held.wait(5) and snapshots.busy
    assert not (snapshots._save_btn.isEnabled() or snapshots._load_btn.isEnabled() or snapshots._del_btn.isEnabled())
    overlay.canvases[0].load([stroke(1.0), stroke(2.0)])  # drawn on meanwhile: not part of this snapshot
    snapshots._save()  # a second save while busy does nothing
    snapshots._load()
    snapshots._delete()
    release.set()
    settle(snapshots)
    assert snapshots._save_btn.isEnabled() is False and snapshots._name_edit.text() == ""  # no name, none selected
    assert [s.created for s in persistence.load_snapshot("review")["0,0"]] == [1.0]
    select(snapshots, "review")
    assert snapshots._save_btn.isEnabled() and snapshots._load_btn.isEnabled() and snapshots._del_btn.isEnabled()


def test_an_error_the_snapshots_didnt_expect_is_logged_and_said(snapshots, monkeypatch, caplog):
    def bug(name, screens) -> None:
        raise TypeError("a bug")

    monkeypatch.setattr(snapshots_module, "save_snapshot", bug)
    snapshots._name_edit.setText("review")
    with caplog.at_level(logging.ERROR, "vitralis.toolbar"):
        snapshots._save()
        settle(snapshots)
    assert snapshots._error_lbl.text() == SNAPSHOT_SAVE_FAILED
    assert any(r.exc_info and "unexpectedly" in r.getMessage() for r in caplog.records)


def test_one_snapshot_that_cant_be_deleted_doesnt_keep_the_others(snapshots, monkeypatch):
    for name in ("one", "two", "three"):
        snapshots._name_edit.setText(name)
        snapshots._save()
        settle(snapshots)
    real = snapshots_module.delete_snapshot

    def refuse_two(name) -> None:
        if name == "two":
            raise SnapshotError("in use")
        real(name)

    monkeypatch.setattr(snapshots_module, "delete_snapshot", refuse_two)
    select(snapshots, "one", "two", "three")
    snapshots._delete()
    settle(snapshots)
    assert list_snapshots() == ["two"] and snapshots._error_lbl.text() == SNAPSHOT_DELETE_FAILED
    assert [snapshots._list.item(i).text() for i in range(snapshots._list.count())] == ["two"]


# --- closed from outside ------------------------------------------------------------------------------------


class Spontaneous(QCloseEvent):
    """A close that comes from Windows (Alt+F4, the taskbar, ``taskkill``), not from the app."""

    def spontaneous(self) -> bool:
        return True


def test_closing_the_toolbar_from_outside_quits_instead_of_leaving_vitralis_headless(overlay):
    """Regression guard: Alt+F4 on the toolbar used to stop its hooks and leave the app running without it."""
    bar = overlay.bar
    event = Spontaneous()
    bar.closeEvent(event)
    assert not event.isAccepted() and overlay.quits == [1] and bar._hotkey_thread.running
    bar.close()  # the session's close, as the shutdown does
    assert not bar._hotkey_thread.running and not bar._wheel_thread.running


def test_closing_a_capture_from_outside_only_leaves_the_mode(overlay):
    overlay.bar._toggle_drawing(True)
    capture = overlay.captures[0]
    event = Spontaneous()
    capture.closeEvent(event)
    assert not event.isAccepted() and not overlay.bar.mode_active and overlay.quits == []
    assert capture.close()  # the session can still close it
