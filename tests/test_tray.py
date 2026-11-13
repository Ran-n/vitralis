#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.728410
Revised: 2026/11/14 00:23:23.245085

The tray icon on the offscreen ``QApplication``: its menu in every UI language (and again after the language
changes), each entry wired to the toolbar or to quitting, a double click showing the toolbar, and closing it.
"""

import pytest
from PyQt6.QtWidgets import QSystemTrayIcon, QWidget

from vitralis.translations import _TRANSLATIONS, set_language
from vitralis.tray import MENU, TrayIcon, make_app_icon, make_tray_icon

pytestmark = pytest.mark.ui
LANGUAGES = list(_TRANSLATIONS)


class Bar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.quits = 0

    def quit(self) -> None:
        self.quits += 1


@pytest.fixture
def bar(qapp, icons):
    made = Bar()
    yield made
    made.deleteLater()


@pytest.fixture
def tray(qapp, bar):
    made = TrayIcon(qapp, bar, bar.quit)
    yield made
    made.close()


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "English"])
def test_every_menu_entry_is_translated(language):
    for key in MENU:
        assert _TRANSLATIONS[language].get(key), f"{language} lacks {key!r}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_menu_speaks_the_ui_language(qapp, bar, language):
    set_language(language)
    tray = TrayIcon(qapp, bar, bar.quit)
    expected = [_TRANSLATIONS[language].get(key, key) for key in MENU]
    assert tray.menu_texts() == expected and all(expected)
    tray.close()


def test_the_menu_follows_a_language_change(tray):
    assert tray.menu_texts() == ["Show toolbar", "Hide toolbar", "Quit"]
    set_language("Galego")
    tray.retranslate()
    assert tray.menu_texts() == ["Mostrar a barra de ferramentas", "Ocultar a barra de ferramentas", "Saír"]


def test_the_entries_show_hide_and_quit(tray, bar):
    show, hide, quit_action = [a for a in tray._menu.actions() if not a.isSeparator()]
    show.trigger()
    assert bar.isVisible()
    hide.trigger()
    assert not bar.isVisible()
    quit_action.trigger()
    assert bar.quits == 1


def test_only_a_double_click_shows_the_toolbar(tray, bar):
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert not bar.isVisible()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert bar.isVisible()


def test_the_made_tray_is_shown_and_quits_through_the_toolbar(qapp, bar):
    tray = make_tray_icon(qapp, bar)
    assert tray.isVisible() and tray.toolTip() == "Vitralis"
    tray._quit_action.trigger()
    assert bar.quits == 1
    tray.close()
    assert not tray.isVisible()


def test_the_app_icon_has_every_size(qapp, icons):
    sizes = {size.width() for size in make_app_icon().availableSizes()}
    assert {16, 32, 48, 64, 128, 256} <= sizes


def test_without_the_logo_the_icon_is_a_plain_square(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr("vitralis.tray.media_base", lambda: tmp_path)
    assert [size.width() for size in make_app_icon().availableSizes()] == [256]
