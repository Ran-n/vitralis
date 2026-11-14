#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.558622
Revised: 2026/11/14 12:01:48.843998

The licence window and the settings' License section, as real Qt widgets rendered offscreen: what they say for
each outcome, which buttons work when, and what they look like (pixels of the rendered window).
"""

import datetime as dt

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests.conftest import wait_until
from tests.licence.fakes import CANONICAL, KEY, FakeLicenceRecord
from vitralis.licence.messages import PRIVACY, status_message
from vitralis.licence.rules import LicenceKind, LicenceStatus
from vitralis.licence.section import LicenceSection
from vitralis.licence.window import LicenceWindow
from vitralis.translations import set_language, t

pytestmark = pytest.mark.ui


@pytest.fixture
def quits():
    return []


@pytest.fixture
def window_gate(make_gate, quits):
    windows: list[LicenceWindow] = []

    def prompt(gate):
        windows.append(LicenceWindow(gate, quit_app=lambda: quits.append(True)))
        return windows[-1]

    gate = make_gate(prompt)
    gate.windows = windows
    return gate


def opened(gate) -> LicenceWindow:
    gate.begin()
    return gate.windows[-1]


def test_a_new_computer_sees_the_window_asking_for_a_key(qapp, window_gate):
    window = opened(window_gate)
    assert window.isVisible()
    assert window.message.text() == (
        "Enter your license key to start Vitralis. No key yet? Ask ran.hash@proton.me for one."
    )
    assert window.privacy.text() == PRIVACY
    assert window.key_field.placeholderText() == "BRN-XXXX-XXXX-XXXX-XXXX"
    assert not window.check_button.isVisible()


def test_activate_is_greyed_out_until_the_key_is_well_formed(qapp, window_gate):
    window = opened(window_gate)
    assert not window.activate_button.isEnabled()
    window.key_field.setText("BRN-79YN")
    assert not window.activate_button.isEnabled()
    window.key_field.setText(KEY.lower().replace("-", " "))
    assert window.activate_button.isEnabled()


def test_clicking_activate_unlocks_and_closes_the_window_without_quitting(qapp, window_gate, events, quits):
    window = opened(window_gate)
    window.key_field.setText(KEY)
    QTest.mouseClick(window.activate_button, Qt.MouseButton.LeftButton)
    assert window.activate_button.text() == "Activating…" and not window.key_field.isEnabled()
    wait_until(qapp, lambda: not window_gate.busy)
    assert events.unlocks == 1 and not window.isVisible() and quits == []


def test_enter_in_the_field_activates(qapp, window_gate, events):
    window = opened(window_gate)
    window.key_field.setText(KEY)
    QTest.keyClick(window.key_field, Qt.Key.Key_Return)
    wait_until(qapp, lambda: not window_gate.busy)
    assert events.unlocks == 1


def test_enter_with_a_malformed_key_sends_nothing(qapp, window_gate, server):
    window = opened(window_gate)
    window.key_field.setText("nonsense")
    QTest.keyClick(window.key_field, Qt.Key.Key_Return)
    assert not window_gate.busy and server.calls == []


def test_a_refused_key_says_why_and_the_field_works_again(qapp, window_gate, server):
    server.licences[CANONICAL] = FakeLicenceRecord(revoked=True)
    window = opened(window_gate)
    window.key_field.setText(KEY)
    window.activate_button.click()
    wait_until(qapp, lambda: not window_gate.busy)
    assert window.message.text() == status_message(LicenceStatus(LicenceKind.REVOKED))
    assert window.key_field.isEnabled() and window.activate_button.isEnabled()


def test_a_licence_to_confirm_offers_check_again(qapp, window_gate, activated, clock, events):
    clock.advance(days=31)
    window = opened(window_gate)
    assert window.check_button.isVisible() and window.check_button.text() == "Check again"
    window.check_button.click()
    assert not window.check_button.isEnabled() and window.check_button.text() == "Checking…"
    wait_until(qapp, lambda: not window_gate.busy)
    assert events.unlocks == 1 and not window.isVisible()


def test_a_refused_key_leaves_check_again_offered(qapp, window_gate, activated, clock, server):
    """Regression guard: the button went with the refused key's message, though a check was as possible as
    before."""
    clock.advance(days=31)
    window = opened(window_gate)
    window.key_field.setText("BRN-0000-0000-0000-0000")
    QTest.mouseClick(window.activate_button, Qt.MouseButton.LeftButton)
    wait_until(qapp, lambda: not window_gate.busy)
    assert window.message.text() == status_message(LicenceStatus(LicenceKind.INVALID_KEY))
    assert window.check_button.isVisible() and window.check_button.isEnabled()
    window_gate.refresh()  # the minute's watch: nothing changed, so the message stays and the focus isn't taken
    assert window.message.text() == status_message(LicenceStatus(LicenceKind.INVALID_KEY))


def test_check_again_offline_shows_the_error_under_the_buttons(qapp, window_gate, activated, clock, server):
    clock.advance(days=31)
    server.down = True
    window = opened(window_gate)
    window.check_button.click()
    wait_until(qapp, lambda: not window_gate.busy)
    assert window.isVisible() and window.error_label.isVisible()
    assert window.error_label.text() == status_message(LicenceStatus(LicenceKind.UNREACHABLE))


def test_closing_the_window_while_locked_quits(qapp, window_gate, quits):
    window = opened(window_gate)
    window.close_button.click()
    assert quits == [True]


def test_escape_closes_the_window_and_quits(qapp, window_gate, quits):
    window = opened(window_gate)
    QApplication.setActiveWindow(window)
    window.key_field.setFocus()
    qapp.processEvents()
    QTest.keyClick(window.key_field, Qt.Key.Key_Escape)
    assert quits == [True]


def test_the_window_speaks_the_ui_language(qapp, window_gate):
    set_language("Galego")
    window = opened(window_gate)
    assert window.message.text().startswith("Introduce a túa clave de licenza para iniciar Vitralis.")
    assert window.activate_button.text() == "Activar"


def _pixel(widget, child) -> QColor:
    image = widget.grab().toImage()
    centre = child.mapTo(widget, child.rect().center())
    return image.pixelColor(centre.x(), centre.y())


def test_the_rendered_activate_button_is_dimmed_until_a_key_is_typed(qapp, window_gate):
    window = opened(window_gate)
    window.adjustSize()
    dimmed = _pixel(window, window.activate_button)
    window.key_field.setText(KEY)
    lit = _pixel(window, window.activate_button)
    assert lit.blue() > lit.red() + 60  # the accent blue (#1a5fa8)
    assert dimmed.blue() < lit.blue() - 40  # greyed out when it can't be used


def test_the_rendered_window_has_its_dark_panel(qapp, window_gate):
    window = opened(window_gate)
    image = window.grab().toImage()
    corner_inside = image.pixelColor(12, image.height() // 2)
    assert corner_inside.red() < 40 and corner_inside.alpha() > 200


# --- the settings' License section --------------------------------------------------------------------------


@pytest.fixture
def section(qapp, make_gate):
    def make() -> LicenceSection:
        gate = make_gate()
        gate.begin()
        return LicenceSection(gate)

    return make


def test_settings_show_a_permanent_licence_and_until_when_it_runs_offline(section, activated, clock):
    shown = section()
    assert shown.values["Status"].text() == "Licensed"
    assert shown.values["Valid until"].text() == "Permanent"
    expected = (clock() + dt.timedelta(days=30)).astimezone().strftime("%Y-%m-%d")
    assert shown.values["Works offline until"].text() == expected
    assert "#ffa726" not in shown.values["Works offline until"].styleSheet()


def test_settings_show_a_test_licence_until_its_date(section, server, licence, clock):
    ends = clock() + dt.timedelta(days=100)
    server.licences[CANONICAL] = FakeLicenceRecord(test=True, expires_at=ends)
    assert licence.activate(KEY).licensed
    shown = section()
    assert shown.values["Status"].text() == "Test license"
    assert shown.values["Valid until"].text() == ends.astimezone().strftime("%Y-%m-%d")


def test_settings_highlight_the_offline_date_when_it_is_under_five_days_away(section, activated, clock):
    clock.advance(days=26)
    shown = section()
    assert "#ffa726" in shown.values["Works offline until"].styleSheet()


def test_check_now_is_greyed_out_while_it_runs(qapp, section, activated):
    shown = section()
    assert shown.check_button.text() == "Check now" and shown.check_button.isEnabled()
    shown.check_button.click()
    assert not shown.check_button.isEnabled() and shown.check_button.text() == "Checking…"
    wait_until(qapp, lambda: shown.check_button.isEnabled())


def test_check_now_offline_says_so_in_the_section(qapp, section, activated, server):
    shown = section()
    server.down = True
    shown.check_button.click()
    wait_until(qapp, lambda: shown.check_button.isEnabled())
    assert shown.error_label.text() == status_message(LicenceStatus(LicenceKind.UNREACHABLE))


def test_the_section_relabels_in_another_language(section, activated):
    shown = section()
    set_language("Deutsch")
    shown.retranslate()
    assert shown.values["Status"].text() == "Lizenziert"
    assert shown.values["Valid until"].text() == "Unbefristet"
    assert shown.check_button.text() == t("Check now") == "Jetzt prüfen"
