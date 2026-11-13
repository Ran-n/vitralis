#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.471868
Revised: 2026/11/14 00:23:23.066098

The real toolbar driving real canvases and captures on the offscreen ``QApplication`` (its system-wide hooks
replaced by inert stand-ins, as in ``test_toolbar``): modes, Esc, quitting once, undo across screens, the tool,
colour, size and position it remembers, every label following the language, and the Snapshots window with its
failures said in words.
"""

import json
import logging

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import QLabel

import vitralis.persistence as persistence
import vitralis.settings as settings_module
from tests.test_toolbar import InertThread
from vitralis import toolbar as toolbar_module
from vitralis.canvas import Canvas, DrawCapture
from vitralis.models import Stroke, Tool
from vitralis.persistence import SnapshotError, forget_strokes, list_snapshots, load_strokes_for
from vitralis.styles import PALETTE, SIZES
from vitralis.toolbar import (
    DEFAULT_SIZE,
    SNAPSHOT_DELETE_FAILED,
    SNAPSHOT_LOAD_FAILED,
    SNAPSHOT_SAVE_FAILED,
    SnapshotWindow,
    Toolbar,
)
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
        DrawCapture(canvas, geo, stop_active=lambda: bars[-1].stop_modes(), toolbar=bars)
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


def saved_toolbar() -> dict:
    return json.loads(settings_module.SETTINGS_FILE.read_text(encoding="utf-8"))["toolbar"]


# --- start --------------------------------------------------------------------------------------------------


def test_a_first_start_draws_with_the_pen_the_first_colour_and_the_shown_size(overlay):
    """Regression guard: the canvases used to draw 3 px wide while the toolbar showed 5."""
    bar = overlay.bar
    assert bar._size_lbl.text() == str(DEFAULT_SIZE)
    for canvas in overlay.canvases:
        assert (canvas.active_tool, canvas.active_color, canvas.active_width) == (Tool.PEN, PALETTE[0], DEFAULT_SIZE)
    assert bar._tool_btns[Tool.PEN].isChecked() and bar._swatch_btns[0].isChecked()
    assert not settings_module.SETTINGS_FILE.exists()  # opening the toolbar saves nothing


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


def test_quitting_asks_the_app_once(overlay):
    overlay.bar.quit()
    overlay.bar.quit()
    assert overlay.quits == [1]


def test_hiding_with_the_focus_key_leaves_the_mode(overlay, monkeypatch):
    """Regression guard: the toolbar used to come back saying "Drawing…" with its captures hidden."""
    bar = overlay.bar
    bar.show()
    bar._toggle_drawing(True)
    monkeypatch.setattr(bar, "_is_vitralis_focused", lambda: True)
    bar._toggle_focus()
    assert not bar.isVisible() and not bar.mode_active and bar._draw_btn.text() == "Draw"
    assert not any(c.isVisible() for c in overlay.captures)


def test_a_right_click_on_a_capture_leaves_the_mode(overlay):
    overlay.bar._toggle_delete(True)
    overlay.captures[0]._stop_active()
    assert not overlay.bar.mode_active


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


def test_a_custom_colour_is_picked_in_the_ui_language_and_remembered(overlay, monkeypatch):
    asked = []

    def pick(initial, parent, title):
        asked.append((initial.name(), title))
        return QColor("#123456")

    monkeypatch.setattr(toolbar_module.QColorDialog, "getColor", pick)
    set_language("Galego")
    overlay.bar._custom_btn.click()
    assert asked == [(PALETTE[0], _TRANSLATIONS["Galego"]["Pick color"])]
    assert all(c.active_color == "#123456" for c in overlay.canvases)
    assert not any(button.isChecked() for button in overlay.bar._swatch_btns)
    again = overlay.build()
    assert again._color == "#123456" and not any(button.isChecked() for button in again._swatch_btns)


def test_a_dismissed_colour_picker_changes_nothing(overlay, monkeypatch):
    monkeypatch.setattr(toolbar_module.QColorDialog, "getColor", lambda *a: QColor())
    overlay.bar._custom_btn.click()
    assert overlay.canvases[0].active_color == PALETTE[0] and overlay.bar._swatch_btns[0].isChecked()
    assert not settings_module.SETTINGS_FILE.exists()


def test_the_wheel_cycles_the_palette_only_while_vitralis_has_the_focus(overlay, monkeypatch):
    bar = overlay.bar
    monkeypatch.setattr(bar, "_is_vitralis_focused", lambda: False)
    bar._on_global_wheel(1)
    assert bar._color == PALETTE[0]
    monkeypatch.setattr(bar, "_is_vitralis_focused", lambda: True)
    bar._on_global_wheel(1)
    assert bar._color == PALETTE[1] and bar._swatch_btns[1].isChecked()
    bar._on_global_wheel(-1)
    bar._on_global_wheel(-1)
    assert bar._color == PALETTE[-1]
    bar._select_color("#123456", None)
    bar._on_global_wheel(1)  # from a custom colour the wheel starts at the palette's beginning
    assert bar._color == PALETTE[1]


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
    assert not settings_module.SETTINGS_FILE.exists()


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
    bar._toggle_visibility(True)
    seen = []
    bar.language_changed.connect(lambda: seen.append(1))
    set_language("Galego")
    bar._on_language_changed("Galego")
    galego = _TRANSLATIONS["Galego"]
    assert bar._draw_btn.text() == galego["Drawing…"] and bar._pan_btn.text() == galego["Pan"]
    assert bar._vis_btn.toolTip() == galego["Show overlay  [H]"]
    assert bar._undo_btn.toolTip() == galego["Undo  [Z]"] and seen == [1]


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


@pytest.fixture
def snapshots(overlay):
    window = SnapshotWindow(overlay.canvases)
    yield window
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
    assert list_snapshots() == ["review"] and snapshots._name_edit.text() == ""
    assert [snapshots._list.item(i).text() for i in range(snapshots._list.count())] == ["review"]
    overlay.bar._clear()
    select(snapshots, "review")
    snapshots._load_btn.click()
    assert [s.created for s in left.strokes] == [1.0] and [s.created for s in right.strokes] == [2.0, 3.0]
    forget_strokes()
    assert load_strokes_for(RIGHT) == right.strokes  # a loaded snapshot is what the next start shows
    snapshots._del_btn.click()
    assert list_snapshots() == [] and snapshots._list.count() == 0 and not snapshots._error_lbl.isVisibleTo(snapshots)


def test_saving_with_one_snapshot_selected_overwrites_it(overlay, snapshots):
    snapshots._name_edit.setText("review")
    snapshots._save()
    overlay.canvases[0].load([stroke(5.0)])
    select(snapshots, "review")
    snapshots._save()
    assert list_snapshots() == ["review"]
    assert [s.created for s in persistence.load_snapshot("review")["0,0"]] == [5.0]


def test_typing_filters_the_list_and_keeps_the_selection(snapshots):
    for name in ("alpha", "beta", "alphabet"):
        snapshots._name_edit.setText(name)
        snapshots._save()
    select(snapshots, "alphabet")
    snapshots._name_edit.setText("ALPHA")
    shown = [snapshots._list.item(i).text() for i in range(snapshots._list.count())]
    assert shown == ["alpha", "alphabet"]
    assert [item.text() for item in snapshots._list.selectedItems()] == ["alphabet"]


def test_several_snapshots_are_deleted_together_but_not_loaded_or_saved(snapshots):
    for name in ("one", "two", "three"):
        snapshots._name_edit.setText(name)
        snapshots._save()
    select(snapshots, "one", "two")
    assert (
        snapshots._del_btn.isEnabled() and not snapshots._load_btn.isEnabled() and not snapshots._save_btn.isEnabled()
    )
    snapshots._load()  # more than one selected: nothing to load
    snapshots._delete()
    assert list_snapshots() == ["three"]
    snapshots._delete()  # nothing selected: nothing happens
    snapshots._save()  # no name and nothing selected: nothing happens
    assert list_snapshots() == ["three"]


def refuse(*args, **kwargs):
    raise SnapshotError("read-only")


def test_a_snapshot_that_cant_be_saved_says_so_and_keeps_the_name(snapshots, monkeypatch):
    snapshots._name_edit.setText("review")
    with monkeypatch.context() as patch:  # only this one patch ends here: the test's data folder stays its own
        patch.setattr(toolbar_module, "save_snapshot", refuse)
        snapshots._save()
    assert snapshots._error_lbl.text() == SNAPSHOT_SAVE_FAILED and snapshots._error_lbl.isVisibleTo(snapshots)
    assert snapshots._name_edit.text() == "review" and list_snapshots() == []
    snapshots._save()
    assert list_snapshots() == ["review"]
    assert not snapshots._error_lbl.isVisibleTo(snapshots) and snapshots._error_lbl.text() == ""


def test_a_snapshot_that_cant_be_loaded_says_so_and_leaves_the_drawing(overlay, snapshots, caplog):
    overlay.canvases[0].load([stroke(1.0)])
    (persistence.SNAPSHOTS_DIR / "broken.json").write_text("{not json", encoding="utf-8")
    snapshots._refresh_list()
    select(snapshots, "broken")
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        snapshots._load()
    assert snapshots._error_lbl.text() == SNAPSHOT_LOAD_FAILED and caplog.records
    assert [s.created for s in overlay.canvases[0].strokes] == [1.0]


def test_a_snapshot_that_cant_be_deleted_says_so_in_the_ui_language(snapshots, monkeypatch):
    snapshots._name_edit.setText("kept")
    snapshots._save()
    select(snapshots, "kept")
    monkeypatch.setattr(toolbar_module, "delete_snapshot", refuse)
    snapshots._delete()
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
    select(snapshots, "left only")
    snapshots._load()
    assert [s.created for s in overlay.canvases[0].strokes] == [9.0]
    assert [s.created for s in overlay.canvases[1].strokes] == [2.0]


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
