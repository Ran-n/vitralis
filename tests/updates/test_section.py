#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:09.620591
Revised: 2026/11/14 00:23:20.966640

Settings → Updates on the offscreen ``QApplication``, driven by a real ``UpdateChecker`` with a fake feed: each
state shows the right texts and enabled buttons (up to date, out, out (skipped), error, checking, and the
install steps), the clicks reach the checker and the settings, and it relabels in another language.
"""

import pytest
from PyQt6.QtCore import QUrl

from tests.conftest import wait_until
from tests.updates.fakes import OFFLINE, FakeFeed, MemorySettings, release
from tests.updates.test_checker import FakeInstall
from vitralis.settings import SettingsManager, SettingsWindow
from vitralis.translations import set_language
from vitralis.updates.checker import InstallKind, UpdateChecker
from vitralis.updates.section import UpdatesSection

pytestmark = pytest.mark.ui
NOON_TEXT = "12:34"


@pytest.fixture
def build(qapp):
    made = []

    def make(feed=None, settings=None, installer=None, quit_app=None):
        import datetime as dt

        checker = UpdateChecker(
            feed or FakeFeed(),
            settings or MemorySettings(),
            "1.3.0",
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


def visible(label) -> bool:
    return not label.isHidden()


def test_before_any_check_only_the_version_and_check_now_show(build):
    _, section, _ = build()
    assert section.version_label.text() == "Version 1.3.0"
    assert not visible(section.result_label) and not visible(section.error_label)
    assert section.check_button.text() == "Check now" and section.check_button.isEnabled()
    assert not section.notes_button.isEnabled() and not section.skip_button.isEnabled()
    assert not visible(section.install_button)


def test_up_to_date(qapp, build):
    checker, section, _ = build(feed=FakeFeed(release("v1.3.0")))
    check(qapp, checker)
    assert section.result_label.text() == f"Vitralis 1.3.0 is up to date · checked {NOON_TEXT}"
    assert section.notes_button.isEnabled() and not section.skip_button.isEnabled()


def test_a_new_version_is_out(qapp, build):
    checker, section, opened = build()
    check(qapp, checker)
    assert section.result_label.text() == "Vitralis 1.4.0 is out"
    assert section.skip_button.text() == "Skip this version" and section.skip_button.isEnabled()
    section.notes_button.click()
    assert opened == [QUrl("https://github.com/Ran-n/vitralis/releases/tag/v1.4.0")]
    assert not visible(section.install_button)  # running from source: no Install


def test_skip_and_dont_skip_save_and_relabel(qapp, build):
    settings = MemorySettings()
    checker, section, _ = build(settings=settings)
    check(qapp, checker)
    section.skip_button.click()
    assert settings.skipped == "1.4.0"
    assert section.result_label.text() == "Vitralis 1.4.0 is out (skipped)"
    assert section.skip_button.text() == "Don't skip"
    section.skip_button.click()
    assert settings.skipped == "" and section.result_label.text() == "Vitralis 1.4.0 is out"


def test_an_error_shows_in_the_error_colour(qapp, build):
    checker, section, _ = build(feed=FakeFeed(OFFLINE))
    check(qapp, checker)
    assert visible(section.error_label)
    assert section.error_label.text() == "Couldn't check for updates: ConnectError: no route"
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
    assert section.switch.isChecked() and section.switch.text() == "Check for new versions"
    section.switch.click()
    assert settings.check is False


def test_install_download_and_restart_states(qapp, build, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.gate.clear()
    quits = []
    checker, section, _ = build(installer=fake.installer(), quit_app=lambda: quits.append(1))
    check(qapp, checker)
    assert visible(section.install_button) and section.install_button.text() == "Install 1.4.0"
    section.install_button.click()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.DOWNLOADING)
    wait_until(qapp, lambda: checker.status.install.percent == 100)
    assert section.install_label.text() == "Downloading 1.4.0… 100%"
    assert not section.install_button.isEnabled() and not section.skip_button.isEnabled()
    fake.gate.set()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    assert section.install_button.text() == "Restart to update" and section.install_button.isEnabled()
    section.install_button.click()
    assert quits == [1] and fake.events[0].startswith("swap")


@pytest.mark.parametrize(
    ("setup", "text"),
    [
        ("damaged", "The download is damaged (checksum mismatch): try again"),
        ("not_writable", "Can't update {dir}: move Vitralis to a folder you can write to, or update by hand"),
        ("offline", "The download failed. Check your internet connection and try again."),
    ],
)
def test_install_failures_show_why(qapp, build, tmp_path, setup, text):
    from vitralis.updates.rules import ChecksumMismatch, DownloadUnreachable

    fake = FakeInstall(tmp_path)
    if setup == "damaged":
        fake.outcome = ChecksumMismatch("x")
    elif setup == "offline":
        fake.outcome = DownloadUnreachable("ConnectError: offline")
    else:
        fake.writable = False
    checker, section, _ = build(installer=fake.installer())
    check(qapp, checker)
    section.install_button.click()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    assert section.install_label.text() == text.format(dir=fake.exe.parent)
    assert "#ff8a65" in section.install_label.styleSheet()
    assert section.install_button.isEnabled()  # try again


def test_the_downloading_line_counts_mb_without_a_total(build):
    from vitralis.updates.checker import InstallState
    from vitralis.updates.messages import install_line

    state = InstallState(InstallKind.DOWNLOADING, "1.4.0", received=3 << 20)
    assert install_line(state) == "Downloading 1.4.0… 3 MB"


def test_the_section_relabels_in_deutsch(qapp, build):
    checker, section, _ = build()
    check(qapp, checker)
    set_language("Deutsch")
    section.retranslate()
    assert section.result_label.text() == "Vitralis 1.4.0 ist erschienen"
    assert section.switch.text() == "Nach neuen Versionen suchen"
    assert section.check_button.text() == "Jetzt prüfen"


def test_the_settings_window_shows_updates_before_license(qapp, icons, make_gate, monkeypatch, tmp_path):
    import vitralis.settings as settings_module

    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.json")
    checker = UpdateChecker(FakeFeed(), MemorySettings(), "1.3.0")
    window = SettingsWindow(SettingsManager(), licence=make_gate(), updates=checker)
    titles = [label.text() for label, _ in window._section_labels]
    assert titles.index("UPDATES") < titles.index("LICENSE")
    assert window.updates_section is not None
    window.close()
    window.deleteLater()
    no_updates = SettingsWindow(SettingsManager())
    assert no_updates.updates_section is None
    no_updates.deleteLater()


def test_no_connection_shows_a_sentence_not_the_exception(qapp, build):
    from vitralis.updates.github import ReleaseFeedError
    from vitralis.updates.rules import FeedFailure

    feed = FakeFeed(ReleaseFeedError("ConnectError: [Errno 11001] getaddrinfo failed", FeedFailure.OFFLINE))
    checker, section, _ = build(feed=feed)
    check(qapp, checker)
    assert section.error_label.text() == (
        "Couldn't check for updates: GitHub can't be reached. Check your internet connection and try again."
    )
