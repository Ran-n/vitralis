#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 16:56:38.576341
Revised: 2026/11/14 18:33:19.233062

Vitralis as Windows draws it: the real toolbar, its windows and an overlay canvas run in a process of their own
(``driver.py``) on a scratch data folder, clicked and dragged with posted window messages and looked at with
PrintWindow. The real mouse and keyboard are never touched and the user's own Vitralis and its data are left
alone, but the windows do show on the screen while the tests run, so they are kept out of the default run:
``uv run pytest -m desktop``.

Each test checks what a person would see (the pixels of the window) and what the click left behind (the app's
state and what it saved); the whole windows are also compared with the reviewed pictures in ``baselines/``.
"""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("the rendered tests drive real Windows windows", allow_module_level=True)

from PyQt6.QtGui import QColor

from tests.rendered import pictures
from vitralis.styles import BTN_CHECKED, PALETTE
from vitralis.toolbar import DEFAULT_SIZE, UPDATE_DOT_MARGIN, UPDATE_DOT_SIZE
from vitralis.translations import _TRANSLATIONS

pytestmark = pytest.mark.desktop

LANGUAGES = {
    "English": "en",
    "Galego": "gl",
    "Galego reintegrado": "gl-reintegrado",
    "Español": "es",
    "Português": "pt",
    "Français": "fr",
    "Deutsch": "de",
    "中文": "zh",
    "日本語": "ja",
}
"""Every UI language and the name its baselines carry."""
PANELS = {"settings": "_settings_btn", "info": "_info_btn", "snapshots": "_snapshot_btn", "color": "_custom_btn"}
"""The toolbar's windows and the button that opens each."""
LINE = ((40, 100), (170, 100), (300, 100))
"""A drag across the overlay, and so the stroke it leaves."""
NEAR = 48
"""How far a channel may be from the colour asked for: edges are smoothed, the middle of a shape is not."""


def is_color(seen: QColor, wanted: str) -> bool:
    want = QColor(wanted)
    parts = ((seen.red(), want.red()), (seen.green(), want.green()), (seen.blue(), want.blue()))
    return all(abs(one - other) <= NEAR for one, other in parts)


def is_clear(seen: QColor) -> bool:
    """Nothing is drawn there: PrintWindow gives black where a window lets the screen show through."""
    return max(seen.red(), seen.green(), seen.blue()) < 8


def baseline(app, part: str, name: str) -> None:
    if app.ratio() != 1.0:
        pytest.skip(f"the baselines were taken at 100 % scaling; this screen is at {app.ratio():.0%}")
    pictures.check(app.shot(part), name)


def draw_line(app) -> None:
    app.click("toolbar._draw_btn")
    app.drag("capture", *LINE)


def test_every_language_has_a_name_for_its_baselines():
    assert set(LANGUAGES) == set(_TRANSLATIONS)


# --- the toolbar --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_toolbar_on_a_first_start_in_every_language(running, language):
    running.start(language)
    state = running.state()
    assert (state["mode"], state["tool"], state["color"], state["size"]) == (None, "PEN", PALETTE[0], DEFAULT_SIZE)
    assert not state["hidden"] and state["visible"] and not state["undo_enabled"] and state["panels"] == []
    baseline(running, "toolbar", f"toolbar-{LANGUAGES[language]}")


def test_draw_lights_its_button_until_a_right_click_on_the_overlay(app):
    assert not is_color(app.pixel("toolbar._draw_btn", 6, 6), BTN_CHECKED)
    app.click("toolbar._draw_btn")
    assert app.state()["mode"] == "draw" and is_color(app.pixel("toolbar._draw_btn", 6, 6), BTN_CHECKED)
    baseline(app, "toolbar", "toolbar-drawing")
    app.click("capture", right=True)
    assert app.state()["mode"] is None and not is_color(app.pixel("toolbar._draw_btn", 6, 6), BTN_CHECKED)


def test_a_drag_draws_a_line_that_is_saved_and_undo_takes_it_back(app):
    draw_line(app)
    state = app.state()
    assert len(state["strokes"]) == 1 and state["saved"] == 1 and state["undo_enabled"]
    assert is_color(app.pixel("canvas", 170, 100), PALETTE[0])
    assert is_clear(app.pixel("canvas", 170, 140))  # away from the line the screen shows through
    baseline(app, "canvas", "canvas-line")
    app.click("toolbar._undo_btn")
    state = app.state()
    assert state["strokes"] == [] and state["saved"] == 0 and not state["undo_enabled"]
    assert is_clear(app.pixel("canvas", 170, 100))


def test_a_swatch_and_a_tool_change_what_the_next_drag_draws(app):
    app.click("toolbar._swatch_btns.6")
    app.click("toolbar._tool_btns.RECT")
    state = app.state()
    assert (state["color"], state["tool"]) == (PALETTE[6], "RECT")
    assert is_color(app.pixel("toolbar._tool_btns.RECT", 4, 4), BTN_CHECKED)
    app.click("toolbar._draw_btn")
    app.drag("capture", (40, 40), (120, 90), (200, 160))
    for x, y in ((40, 100), (200, 100), (120, 40), (120, 160)):  # the four sides
        assert is_color(app.pixel("canvas", x, y), PALETTE[6]), (x, y)
    assert is_clear(app.pixel("canvas", 120, 100))  # not filled
    app.start(fresh=False)  # the next start draws with the same tool and colour, over the same drawing
    state = app.state()
    assert (state["color"], state["tool"], len(state["strokes"])) == (PALETTE[6], "RECT", 1)
    assert is_color(app.pixel("canvas", 40, 100), PALETTE[6])


def test_plus_and_minus_change_how_thick_the_line_is(app):
    for _ in range(6):
        app.click("toolbar._plus_btn")
    assert app.state()["size"] == DEFAULT_SIZE + 6
    draw_line(app)
    assert is_color(app.pixel("canvas", 170, 104), PALETTE[0])  # 11 px thick: 4 px off its middle is still line
    app.click("toolbar._undo_btn")
    for _ in range(8):
        app.click("toolbar._minus_btn")
    assert app.state()["size"] == DEFAULT_SIZE - 2
    app.drag("capture", *LINE)
    assert is_color(app.pixel("canvas", 170, 100), PALETTE[0]) and is_clear(app.pixel("canvas", 170, 104))


def test_delete_mode_removes_the_stroke_clicked_and_no_other(app):
    draw_line(app)
    app.drag("capture", (40, 200), (170, 200), (300, 200))
    app.click("toolbar._del_btn")
    assert app.state()["mode"] == "delete"
    app.click("capture", at=(170 / 359, 150 / 239))  # between the two: nothing
    assert len(app.state()["strokes"]) == 2
    app.click("capture", at=(170 / 359, 100 / 239))
    state = app.state()
    assert len(state["strokes"]) == 1 and state["saved"] == 1
    assert is_clear(app.pixel("canvas", 170, 100)) and is_color(app.pixel("canvas", 170, 200), PALETTE[0])


def test_clear_empties_the_overlay(app):
    draw_line(app)
    assert app.state()["saved"] == 1 and is_color(app.pixel("canvas", 170, 100), PALETTE[0])
    app.click("toolbar._clear_btn")
    state = app.state()
    assert state["strokes"] == [] and state["saved"] == 0 and is_clear(app.pixel("canvas", 170, 100))


def test_hidden_drawings_stay_hidden_over_a_restart_and_come_back_whole(app):
    draw_line(app)
    app.click("toolbar._vis_btn")
    state = app.state()
    assert state["hidden"] and not state["visible"] and state["mode"] is None  # hiding ends drawing
    app.start(fresh=False)
    state = app.state()
    assert state["hidden"] and not state["visible"] and len(state["strokes"]) == 1
    app.click("toolbar._vis_btn")
    state = app.state()
    assert not state["hidden"] and state["visible"] and is_color(app.pixel("canvas", 170, 100), PALETTE[0])


def test_the_dot_on_settings_says_a_new_version_is_offered(running):
    running.start()
    x, y = -UPDATE_DOT_MARGIN - UPDATE_DOT_SIZE // 2, UPDATE_DOT_MARGIN + UPDATE_DOT_SIZE // 2
    shot = running.shot("toolbar._settings_btn")
    assert not is_color(shot.pixelColor(shot.width() + x, y), BTN_CHECKED)
    running.ask("check_updates")
    running.until(lambda state: state["update_offered"])
    running.settle()
    shot = running.shot("toolbar._settings_btn")
    assert is_color(shot.pixelColor(shot.width() + x, y), BTN_CHECKED)
    running.click("toolbar._settings_btn")
    baseline(running, "settings", "panel-settings-update")  # and Settings says which, with what to do about it


def test_the_logo_and_name_are_in_the_middle_of_the_toolbar(app):
    """Regression guard: the focus dot on the name's right pushed the name left of the middle."""
    shot = app.shot("toolbar._header.name_parts.1")  # "itralis", light on the dark toolbar
    _, left, _, width, _ = app.where("toolbar._header.name_parts.0")
    _, name_left, _, name_width, _ = app.where("toolbar._header.name_parts.1")
    lit = [x for x in range(shot.width()) if any(shot.pixelColor(x, y).lightness() > 90 for y in range(shot.height()))]
    assert lit, "the name isn't drawn"
    toolbar_width = app.where("toolbar")[3]
    middle = (left + name_left + lit[-1] + 1) / 2
    assert abs(middle - toolbar_width / 2) <= 2, (middle, toolbar_width / 2)


# --- its windows --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("panel", PANELS)
def test_a_button_opens_its_window_and_the_cross_closes_it(app, panel):
    app.click(f"toolbar.{PANELS[panel]}")
    assert app.state()["panels"] == [panel]
    baseline(app, panel, f"panel-{panel}")
    app.click(f"toolbar.{PANELS[panel]}")  # again: still the one window
    assert app.state()["panels"] == [panel]
    app.click(f"{panel}.close")
    assert app.state()["panels"] == []


def test_a_colour_picked_in_the_colour_window_is_the_one_drawn_with(app):
    app.click("toolbar._custom_btn")
    app.click("color.shades", at=(1.0, 0.0))  # the top right corner: the pure hue of the red in use
    assert app.state()["color"] == "#ff0000"
    preview = app.shot("color.preview")
    assert is_color(preview.pixelColor(preview.width() // 2, preview.height() // 2), "#ff0000")
    app.click("color.hues", at=(1 / 3, 0.5))  # a third along the hues: green
    picked = QColor(app.state()["color"])
    assert picked.green() == 255 and picked.red() < 8 and picked.blue() < 8
    draw_line(app)
    assert is_color(app.pixel("canvas", 170, 100), picked.name())


def test_a_snapshot_is_saved_by_name_and_loaded_back(app):
    draw_line(app)
    app.click("toolbar._snapshot_btn")
    app.type("snapshots._name_edit", "a1")
    assert app.state()["snapshot_name"] == "a1"
    app.click("snapshots._save_btn")
    state = app.until(lambda state: state["saved_snapshots"] == ["a1"])
    assert state["snapshot_names"] == ["a1"]
    app.click("toolbar._clear_btn")
    assert app.state()["strokes"] == []
    app.click("snapshots._list", at=(0.3, 0.08))  # its first row
    app.click("snapshots._load_btn")
    state = app.until(lambda state: len(state["strokes"]) == 1)
    assert state["saved"] == 1 and is_color(app.pixel("canvas", 170, 100), PALETTE[0])
    baseline(app, "snapshots", "panel-snapshots-one")
    app.click("snapshots._del_btn")
    state = app.until(lambda state: state["saved_snapshots"] == [])
    assert state["snapshot_names"] == [] and len(state["strokes"]) == 1  # the drawing stays
