#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:09.620591
Revised: 2026/11/15 22:45:18.882657

Settings → Updates on the offscreen ``QApplication``, driven by a real ``UpdateChecker`` with a fake check:
each state shows the right texts and enabled buttons (up to date, available, skipped, no build, failed,
checking, downloading, installing), the clicks reach the checker and the settings, a build from source shows
no controls, and it relabels in another language.
"""

import datetime as dt

import pytest
from PyQt6.QtCore import QUrl

from tests.qt_support import wait_until
from tests.updates.fakes import FAILED, TARGET, FakeFeed, MemorySettings, release
from tests.updates.test_checker import FakeInstall
from vitralis.settings import SettingsManager, SettingsWindow
from vitralis.translations import set_language
from vitralis.updates.checker import InstallKind, UpdateChecker
from vitralis.updates.rules import ChecksumMismatch, NotSigned
from vitralis.updates.section import UpdatesSection

pytestmark = pytest.mark.ui


@pytest.fixture
def build(qapp):
    made = []

    def make(feed=None, settings=None, installer=None, quit_app=None, target=TARGET):
        checker = UpdateChecker(
            feed or FakeFeed(),
            settings or MemorySettings(),
            "1.3.0",
            target,
            clock=lambda: dt.datetime(2026, 11, 13, 12, 34),
            installer=installer,
        )
        opened = []
        section = UpdatesSection(checker, quit_app=quit_app, open_url=opened.append)
        made.append((checker, section))
        return checker, section, opened

    yield make
    for checker, section in made:
        checker.stop()
        section.deleteLater()


def check(qapp, checker):
    checker.check_now()
    wait_until(qapp, lambda: not checker.busy)


def visible(widget) -> bool:
    return not widget.isHidden()


def test_before_any_check_only_the_version_and_the_controls_show(build):
    _, section, _ = build()
    assert section.version_label.text() == "Version 1.3.0 · windows-x86_64"
    assert not visible(section.result_label) and not visible(section.error_label)
    assert section.check_button.text() == "Check now" and section.check_button.isEnabled()
    assert not section.notes_button.isEnabled() and not section.skip_button.isEnabled()
    assert not visible(section.install_button)


def test_a_build_from_source_says_how_to_update_and_shows_no_controls(build):
    _, section, _ = build(target=None)
    assert section.version_label.text() == "Version 1.3.0 · built from source"
    assert section.result_label.text() == ("This copy was built from source. Update it with git pull and a new build.")
    for control in (section.switch, section.notes_button, section.skip_button, section.check_button):
        assert not visible(control)
    assert not visible(section.install_button)


def test_up_to_date(qapp, build):
    checker, section, _ = build(feed=FakeFeed(release("v1.3.0")))
    check(qapp, checker)
    assert section.result_label.text() == "Vitralis is up to date (checked 12:34)."
    assert section.notes_button.isEnabled() and not section.skip_button.isEnabled()


def test_a_new_version_is_available(qapp, build):
    checker, section, opened = build()
    check(qapp, checker)
    assert section.result_label.text() == "Vitralis 1.4.0 is available (checked 12:34)."
    assert section.skip_button.text() == "Skip this version" and section.skip_button.isEnabled()
    section.notes_button.click()
    assert opened == [QUrl("https://github.com/Ran-n/vitralis/releases/tag/v1.4.0")]
    assert not visible(section.install_button)  # not the packaged exe: nothing to install


def test_a_release_without_a_build_for_this_system(qapp, build):
    checker, section, _ = build(feed=FakeFeed(release("1.4.0", missing="exe")))
    check(qapp, checker)
    assert section.result_label.text() == "Vitralis 1.4.0 is out, but has no build for this system yet."
    assert not section.skip_button.isEnabled()


def test_skip_and_stop_skipping_save_and_relabel(qapp, build):
    settings = MemorySettings()
    checker, section, _ = build(settings=settings)
    check(qapp, checker)
    section.skip_button.click()
    assert settings.skipped == "1.4.0"
    assert section.result_label.text() == "Vitralis 1.4.0 is available; you chose to skip it (checked 12:34)."
    assert section.skip_button.text() == "Stop skipping 1.4.0" and section.skip_button.isEnabled()
    section.skip_button.click()
    wait_until(qapp, lambda: not checker.busy)
    assert settings.skipped == "" and section.result_label.text() == "Vitralis 1.4.0 is available (checked 12:34)."


def test_a_failed_check_shows_each_sources_reason_in_the_error_colour(qapp, build):
    checker, section, _ = build(feed=FakeFeed(FAILED))
    check(qapp, checker)
    assert visible(section.error_label)
    assert section.error_label.text() == (
        "Couldn't check for updates: GitHub: the server answered 429; GitLab: the request timed out."
    )
    assert "#ff8a65" in section.error_label.styleSheet()


def test_checking_dims_check_now(qapp, build):
    feed = FakeFeed()
    feed.gate.clear()
    checker, section, _ = build(feed=feed)
    section.check_button.click()
    assert section.check_button.text() == "Checking…" and not section.check_button.isEnabled()
    feed.gate.set()
    wait_until(qapp, lambda: not checker.busy)
    assert section.check_button.text() == "Check now" and section.check_button.isEnabled()


def test_the_switch_saves(build):
    settings = MemorySettings(check=True)
    _, section, _ = build(settings=settings)
    assert section.switch.isChecked() and section.switch.text() == "Check for updates automatically"
    section.switch.click()
    assert settings.check is False


def test_update_and_restart_then_cancel_then_update_again(qapp, build, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.gate.clear()
    quits = []
    checker, section, _ = build(installer=fake.installer(), quit_app=lambda: quits.append(1))
    check(qapp, checker)
    assert visible(section.install_button) and section.install_button.text() == "Update and restart"
    section.install_button.click()
    wait_until(qapp, lambda: checker.status.install.percent == 100)
    assert section.install_label.text() == "Downloading Vitralis 1.4.0… 100 %"
    assert section.install_button.text() == "Cancel" and section.install_button.isEnabled()
    assert not section.skip_button.isEnabled()
    section.install_button.click()  # Cancel
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.IDLE)
    assert section.install_button.text() == "Update and restart" and not visible(section.install_label)
    fake.gate.set()
    section.install_button.click()
    wait_until(qapp, lambda: quits == [1])
    assert section.install_label.text() == "Installing Vitralis 1.4.0…" and not section.install_button.isEnabled()


def test_without_a_way_to_quit_the_update_button_is_dimmed(qapp, build, tmp_path):
    checker, section, _ = build(installer=FakeInstall(tmp_path).installer())
    check(qapp, checker)
    assert visible(section.install_button) and not section.install_button.isEnabled()
    section.install_button.click()
    assert checker.status.install.kind is InstallKind.IDLE


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (ChecksumMismatch("x"), "The download of Vitralis 1.4.0 didn't match its checksum, so it wasn't installed."),
        (
            NotSigned("x"),
            "The download of Vitralis 1.4.0 isn't signed with Vitralis's release key, so it wasn't installed.",
        ),
    ],
)
def test_install_failures_show_why_in_the_error_colour(qapp, build, tmp_path, error, text):
    fake = FakeInstall(tmp_path, error=error)
    checker, section, _ = build(installer=fake.installer(), quit_app=lambda: None)
    check(qapp, checker)
    section.install_button.click()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    assert section.install_label.text() == text
    assert "#ff8a65" in section.install_label.styleSheet()
    assert section.install_button.isEnabled()  # try again


def test_a_folder_that_cant_be_written_says_where_and_where_to_download(qapp, build, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.writable = False
    checker, section, _ = build(installer=fake.installer(), quit_app=lambda: None)
    check(qapp, checker)
    section.install_button.click()
    assert section.install_label.text() == (
        f"Vitralis couldn't replace itself at {fake.exe}: the folder can't be written to. "
        "Download it from the release page instead: https://github.com/Ran-n/vitralis/releases/tag/v1.4.0"
    )


def test_the_section_relabels_in_deutsch(qapp, build):
    checker, section, _ = build()
    check(qapp, checker)
    set_language("Deutsch")
    section.retranslate()
    assert section.result_label.text() == "Vitralis 1.4.0 ist verfügbar (geprüft um 12:34)."
    assert section.switch.text() == "Automatisch nach Updates suchen"
    assert section.check_button.text() == "Jetzt prüfen"


def test_the_settings_window_shows_updates_before_license(qapp, icons, make_gate, monkeypatch, tmp_path):
    import vitralis.settings as settings_module

    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.json")
    checker = UpdateChecker(FakeFeed(), MemorySettings(), "1.3.0", TARGET)
    window = SettingsWindow(SettingsManager(), licence=make_gate(), updates=checker)
    titles = [label.text() for label, _ in window._section_labels]
    assert titles.index("UPDATES") < titles.index("LICENSE")
    assert window.updates_section is not None
    window.close()
    window.deleteLater()
    no_updates = SettingsWindow(SettingsManager())
    assert no_updates.updates_section is None
    no_updates.deleteLater()
