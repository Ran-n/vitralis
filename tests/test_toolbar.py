#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:11.688678
Revised: 2026/11/13 09:11:12.021907

The real toolbar on the offscreen ``QApplication``, with its system-wide keyboard and mouse hooks replaced by
inert stand-ins: the accent dot on the Settings button shows only while an update is offered, painted inside
the button so the toolbar's width never changes, with the matching tooltip; and the About window names the
licence with its version.
"""

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel

from tests.conftest import wait_until
from tests.updates.fakes import FakeFeed, MemorySettings, release
from vitralis import toolbar as toolbar_module
from vitralis.styles import BTN_CHECKED
from vitralis.toolbar import UPDATE_DOT_MARGIN, UPDATE_DOT_SIZE, InfoWindow, Toolbar
from vitralis.translations import set_language
from vitralis.updates.checker import UpdateChecker
from vitralis.version import LICENCE_NAME

pytestmark = pytest.mark.ui


class _Signal:
    def connect(self, slot) -> None:
        pass


class _Signals:
    toggle_focus = _Signal()
    scrolled = _Signal()


class InertThread:
    """Stands in for the global hotkey and wheel hooks: never installs anything."""

    def __init__(self, *args, **kwargs) -> None:
        self.signals = _Signals()
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def isRunning(self) -> bool:
        return self.running


@pytest.fixture
def make_toolbar(qapp, icons, monkeypatch, tmp_path):
    import vitralis.settings as settings_module

    monkeypatch.setattr(toolbar_module, "GlobalHotkeyThread", InertThread)
    monkeypatch.setattr(toolbar_module, "GlobalMouseWheelThread", InertThread)
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.json")
    made = []

    def make(updates=None) -> Toolbar:
        bar = Toolbar([], [], updates=updates)
        made.append(bar)
        return bar

    yield make
    for bar in made:
        bar.close()
        bar.deleteLater()


def checked(qapp, feed):
    checker = UpdateChecker(feed, MemorySettings(), "1.3.0")
    checker.check_now()
    wait_until(qapp, lambda: not checker.busy)
    return checker


def dot_pixel(bar: Toolbar) -> QColor:
    button = bar._settings_btn
    image = button.grab().toImage()
    ratio = image.devicePixelRatio()
    centre_x = button.width() - UPDATE_DOT_MARGIN - UPDATE_DOT_SIZE / 2
    centre_y = UPDATE_DOT_MARGIN + UPDATE_DOT_SIZE / 2
    return image.pixelColor(int(centre_x * ratio), int(centre_y * ratio))


def is_accent(colour: QColor) -> bool:
    accent = QColor(BTN_CHECKED)
    return all(abs(a - b) <= 8 for a, b in zip(colour.getRgb()[:3], accent.getRgb()[:3], strict=True))


def test_the_dot_shows_only_while_an_update_is_offered(qapp, make_toolbar):
    checker = checked(qapp, FakeFeed())
    bar = make_toolbar(checker)
    assert bar._settings_btn.dot and is_accent(dot_pixel(bar))
    assert bar._settings_btn.toolTip() == "Settings · Vitralis 1.4.0 is out"
    checker.skip()
    assert not bar._settings_btn.dot and not is_accent(dot_pixel(bar))
    assert bar._settings_btn.toolTip() == "Settings"


def test_no_dot_when_up_to_date_or_without_an_updater(qapp, make_toolbar):
    bar = make_toolbar(checked(qapp, FakeFeed(release("v1.3.0"))))
    assert not bar._settings_btn.dot and not is_accent(dot_pixel(bar))
    plain = make_toolbar()
    assert not plain._settings_btn.dot and plain._settings_btn.toolTip() == "Settings"


def test_the_dot_changes_neither_the_button_nor_the_toolbar_width(qapp, make_toolbar):
    plain = make_toolbar(checked(qapp, FakeFeed(release("v1.3.0"))))
    dotted = make_toolbar(checked(qapp, FakeFeed()))
    assert dotted._settings_btn.dot
    assert dotted.width() == plain.width()
    assert dotted._settings_btn.size() == plain._settings_btn.size() and dotted._settings_btn.width() == 26


def test_the_tooltip_keeps_the_update_after_a_language_change(qapp, make_toolbar):
    bar = make_toolbar(checked(qapp, FakeFeed()))
    set_language("Deutsch")
    bar.retranslate()
    assert bar._settings_btn.toolTip() == "Einstellungen · Vitralis 1.4.0 ist erschienen"


def test_settings_open_with_the_updates_section(qapp, make_toolbar):
    bar = make_toolbar(checked(qapp, FakeFeed()))
    bar.open_settings()
    assert bar._settings_win is not None and bar._settings_win.updates_section is not None
    bar._settings_win.close()


@pytest.mark.parametrize("language", ["English", "日本語"])
def test_the_about_window_shows_the_versioned_licence(qapp, icons, language):
    set_language(language)
    window = InfoWindow("1.3.0")
    texts = [label.text() for label in window.findChildren(QLabel)]
    assert LICENCE_NAME in texts and "PayBack License (PBL)" not in texts
    window.deleteLater()
