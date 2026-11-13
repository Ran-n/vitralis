#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:13.645333
Revised: 2026/11/14 00:23:22.509649

The settings window on the offscreen ``QApplication``, with a real ``SettingsManager`` on the test's own
``settings.json``: capturing a shortcut from a key press, one key never serving two actions, a key the global
hook can't take being refused, resets, and every label following the language.
"""

import json
import logging

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QComboBox

import vitralis.settings as settings_module
from vitralis.settings import DEFAULT_SHORTCUTS, GLOBAL_ACTION, SettingsManager, SettingsWindow
from vitralis.translations import _TRANSLATIONS, t

pytestmark = pytest.mark.ui


@pytest.fixture
def window(qapp, icons):
    made = SettingsWindow(SettingsManager())
    made.changes = []
    made.shortcuts_changed.connect(made.changes.append)
    yield made
    made.close()
    made.deleteLater()


def saved_shortcuts() -> dict:
    return json.loads(settings_module.SETTINGS_FILE.read_text(encoding="utf-8"))["shortcuts"]


def press(widget, key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


# --- capturing ----------------------------------------------------------------------------------------------


def test_a_click_then_a_key_becomes_the_shortcut_and_is_saved(window):
    capture = window._captures["draw"]
    capture.click()
    assert capture.text() == "…" and capture.isChecked()
    press(capture, Qt.Key.Key_K)
    assert capture.text() == "K" and not capture.isChecked()
    assert saved_shortcuts()["draw"] == "k" and window.changes[-1]["draw"] == "k"
    assert SettingsManager().shortcuts()["draw"] == "k"


def test_modifiers_are_part_of_the_shortcut_and_alone_capture_nothing(window):
    capture = window._captures["quit"]
    capture.click()
    press(capture, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    assert capture.text() == "…"  # still listening
    held = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
    press(capture, Qt.Key.Key_W, held)
    assert capture.text() == "CTRL+SHIFT+ALT+W" and saved_shortcuts()["quit"] == "ctrl+shift+alt+w"


def test_a_key_press_while_not_listening_captures_nothing(window):
    capture = window._captures["draw"]
    press(capture, Qt.Key.Key_K)
    assert capture.text() == "D" and window.changes == []
    assert not settings_module.SETTINGS_FILE.exists()


def test_a_key_another_action_had_moves_to_the_new_one(window):
    """Regression guard: one key on two actions made Qt call neither. The old owner is left without one."""
    window._assign("pan", DEFAULT_SHORTCUTS["draw"])
    assert window._captures["pan"].text() == "D" and window._captures["draw"].text() == "—"
    assert saved_shortcuts()["pan"] == "d" and saved_shortcuts()["draw"] == ""
    assert list(window.changes[-1].values()).count("d") == 1
    assert SettingsManager().shortcuts()["draw"] == ""  # no shortcut survives a restart as no shortcut


@pytest.mark.parametrize("key", ["launch (b)", "ctrl+nosuchkey"])
def test_a_key_the_global_hook_cant_take_is_refused_for_the_focus_shortcut(window, key, caplog):
    """Regression guard: such a key used to be saved, and registering it ended the hotkey thread."""
    with caplog.at_level(logging.WARNING, "vitralis.settings"):
        window._assign(GLOBAL_ACTION, key)
    assert window._captures[GLOBAL_ACTION].text() == "F8" and window.changes == []
    assert not settings_module.SETTINGS_FILE.exists()
    assert any(key in r.getMessage() for r in caplog.records)


def test_the_focus_shortcut_takes_a_key_the_hook_knows(window):
    window._assign(GLOBAL_ACTION, "ctrl+f9")
    assert window._captures[GLOBAL_ACTION].text() == "CTRL+F9" and saved_shortcuts()[GLOBAL_ACTION] == "ctrl+f9"


# --- resets -------------------------------------------------------------------------------------------------


def test_resetting_one_action_gives_it_its_default_back(window):
    window._assign("draw", "k")
    window._reset_action("draw")
    assert window._captures["draw"].text() == "D" and saved_shortcuts()["draw"] == "d"


def test_resetting_an_action_takes_its_default_key_back_from_another(window):
    window._assign("draw", "k")
    window._assign("pan", "d")
    window._reset_action("draw")
    assert saved_shortcuts()["draw"] == "d" and saved_shortcuts()["pan"] == ""


def test_reset_all_restores_every_default(window):
    window._assign("draw", "k")
    window._assign("pan", "d")
    window._reset_all_btn.click()
    assert saved_shortcuts() == DEFAULT_SHORTCUTS and window.changes[-1] == DEFAULT_SHORTCUTS
    assert all(window._captures[a].text() == k.upper() for a, k in DEFAULT_SHORTCUTS.items())


# --- language -----------------------------------------------------------------------------------------------


def test_picking_a_language_saves_it_and_relabels_everything(window):
    seen = []
    window.language_changed.connect(seen.append)
    window.findChild(QComboBox).setCurrentText("Galego")
    galego = _TRANSLATIONS["Galego"]
    assert seen == ["Galego"] and SettingsManager().language() == "Galego"
    assert window._title.text() == galego["Settings"]
    assert window._action_labels["draw"].text() == galego["Toggle draw mode"]
    assert window._reset_all_btn.text() == galego["Reset all"]
    assert window._lang_label.text() == galego["UI Language"]
    assert [label.text() for label, _ in window._section_labels] == [
        galego["Keyboard Shortcuts"].upper(),
        galego["Language"].upper(),
    ]


def test_the_reset_buttons_not_the_key_buttons_carry_the_reset_tooltip(window):
    """Regression guard: a language change used to put "Reset to default" on the key buttons instead."""
    window.findChild(QComboBox).setCurrentText("Deutsch")
    assert len(window._reset_buttons) == len(DEFAULT_SHORTCUTS)
    assert all(button.toolTip() == t("Reset to default") != "Reset to default" for button in window._reset_buttons)
    assert all(capture.toolTip() == "" for capture in window._captures.values())


def test_the_window_opens_in_the_saved_language(qapp, icons):
    SettingsManager().set_language("日本語")
    window = SettingsWindow(SettingsManager())
    assert window._title.text() == _TRANSLATIONS["日本語"]["Settings"]
    assert window.findChild(QComboBox).currentText() == "日本語"
    window.deleteLater()


def test_closing_says_so(window):
    closed, active = [], []
    window.closed.connect(lambda: closed.append(1))
    window.activation_changed.connect(active.append)
    window.close()
    assert closed == [1] and active[-1] is False
