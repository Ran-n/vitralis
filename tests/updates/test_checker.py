#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:08.909997
Revised: 2026/11/14 12:01:49.118368

The update checker on the offscreen ``QApplication``: checks run off the UI thread and come back as one
``UpdateStatus``; skip and Don't skip need no new check; errors are shown and never leave it busy; the timer
respects the switch; and, with an ``Installer``, the download → ready → restart steps in order.
"""

import logging
import threading
from pathlib import Path

import pytest

from tests.conftest import wait_until
from tests.updates.fakes import NOON, OFFLINE, FakeFeed, MemorySettings, release
from vitralis.updates.checker import (
    FIRST_CHECK_DELAY_MS,
    FailureKind,
    Installer,
    InstallKind,
    UpdateChecker,
)
from vitralis.updates.github import ReleaseFeedError
from vitralis.updates.rules import (
    ChecksumMismatch,
    DownloadRefused,
    DownloadUnreachable,
    FeedFailure,
    SwapFailed,
    UpdateCancelled,
    UpdateError,
)


class Recorder:
    def __init__(self, checker: UpdateChecker) -> None:
        self.statuses = []
        self.busy = []
        checker.changed.connect(self.statuses.append)
        checker.busy_changed.connect(self.busy.append)


@pytest.fixture
def make(qapp):
    made = []

    def build(feed=None, settings=None, current="1.3.0", installer=None):
        checker = UpdateChecker(
            feed or FakeFeed(), settings or MemorySettings(), current, clock=lambda: NOON, installer=installer
        )
        made.append(checker)
        return checker, Recorder(checker)

    yield build
    for checker in made:
        checker.stop()


def check(qapp, checker):
    checker.check_now()
    wait_until(qapp, lambda: not checker.busy)


def test_check_now_says_busy_then_offers_the_newer_release(qapp, make):
    checker, seen = make()
    check(qapp, checker)
    assert seen.busy == [True, False]
    status = seen.statuses[-1]
    assert status.offered == release("v1.4.0") and status.newer and status.checked_at == NOON and status.error == ""


def test_the_check_runs_off_the_ui_thread(qapp, make):
    names = []
    feed = FakeFeed()
    real = feed.latest
    feed.latest = lambda: names.append(threading.current_thread().name) or real()
    checker, _ = make(feed=feed)
    check(qapp, checker)
    assert names == ["vitralis-update-check"]


def test_up_to_date_offers_nothing(qapp, make):
    checker, seen = make(feed=FakeFeed(release("v1.3.0")))
    check(qapp, checker)
    assert seen.statuses[-1].offered is None and not seen.statuses[-1].newer


def test_skip_hides_the_offer_without_a_new_check_and_dont_skip_brings_it_back(qapp, make):
    settings = MemorySettings()
    feed = FakeFeed()
    checker, seen = make(feed=feed, settings=settings)
    check(qapp, checker)
    checker.skip()
    assert settings.skipped == "1.4.0" and seen.statuses[-1].offered is None and seen.statuses[-1].newer
    checker.unskip()
    assert settings.skipped == "" and seen.statuses[-1].offered == release("v1.4.0")
    assert feed.calls == 1


def test_a_feed_error_is_shown_and_keeps_the_latest(qapp, make):
    feed = FakeFeed()
    checker, seen = make(feed=feed)
    check(qapp, checker)
    feed.answer = OFFLINE
    check(qapp, checker)
    status = seen.statuses[-1]
    assert status.error == str(OFFLINE) and status.latest == release("v1.4.0")
    assert status.error_kind is FeedFailure.OTHER
    feed.answer = release("v1.4.0")
    check(qapp, checker)
    assert seen.statuses[-1].error == ""


def test_an_unexpected_exception_is_shown_and_never_leaves_it_busy(qapp, make, caplog):
    checker, seen = make(feed=FakeFeed(RuntimeError("bug")))
    with caplog.at_level(logging.ERROR, "vitralis.updates.checker"):
        check(qapp, checker)
    assert not checker.busy and "RuntimeError: bug" in seen.statuses[-1].error
    assert any(r.exc_info for r in caplog.records)


def test_a_second_check_while_one_runs_is_ignored(qapp, make):
    feed = FakeFeed()
    feed.gate.clear()
    checker, _ = make(feed=feed)
    checker.check_now()
    checker.check_now()
    feed.gate.set()
    wait_until(qapp, lambda: not checker.busy)
    assert feed.calls == 1


def test_the_timer_checks_only_while_the_switch_is_on(qapp, make):
    settings = MemorySettings(check=False)
    feed = FakeFeed()
    checker, _ = make(feed=feed, settings=settings)
    checker._on_timer()
    qapp.processEvents()
    assert feed.calls == 0
    check(qapp, checker)  # Check now works with the switch off
    assert feed.calls == 1
    checker.set_check_enabled(True)
    assert settings.check
    checker._on_timer()
    wait_until(qapp, lambda: not checker.busy)
    assert feed.calls == 2


def test_start_waits_before_the_first_check_and_then_checks_daily(qapp, make):
    checker, _ = make()
    checker.start()
    assert checker._timer.isActive() and checker._timer.interval() == FIRST_CHECK_DELAY_MS
    checker._on_timer()
    assert checker._timer.interval() == 24 * 3600 * 1000
    wait_until(qapp, lambda: not checker.busy)
    checker.stop()
    assert not checker._timer.isActive()


def test_the_new_version_is_logged_once(qapp, make, caplog):
    checker, _ = make()
    with caplog.at_level(logging.INFO, "vitralis.updates.checker"):
        check(qapp, checker)
        check(qapp, checker)
    assert [r.getMessage() for r in caplog.records].count("version 1.4.0 is out (running 1.3.0)") == 1


def test_an_unknown_running_version_is_offered_any_release(qapp, make):
    checker, seen = make(current="?")
    check(qapp, checker)
    assert seen.statuses[-1].offered is not None


# --- installing -------------------------------------------------------------------------------------------------


class FakeInstall:
    """The installer's I/O: a download that does what it is told, a recorded swap."""

    def __init__(self, tmp_path: Path) -> None:
        self.exe = tmp_path / "Tools" / "vitralis-1.3.0.exe"
        self.updates_dir = tmp_path / "updates"
        self.outcome: Exception | None = None
        self.gate = threading.Event()
        self.gate.set()
        self.events: list[str] = []
        self.writable = True
        self.pending: Path | None = None

    def download(self, release, progress, stop):
        progress(50, 100)
        progress(100, 100)
        self.gate.wait(5)
        if stop.is_set():
            raise UpdateCancelled("stopped")
        if self.outcome is not None:
            raise self.outcome
        return self.updates_dir / "vitralis-1.4.0.exe"

    def swap(self, running, new, old_version, pid):
        self.events.append(f"swap {running.name} {new.name} {old_version}")
        if self.outcome is not None:
            raise self.outcome

    def installer(self) -> Installer:
        return Installer(
            self.exe,
            self.updates_dir,
            self.download,
            swap=self.swap,
            find_pending=lambda folder, current: self.pending,
            writable=lambda folder: self.writable,
        )


@pytest.fixture
def fake_install(tmp_path):
    return FakeInstall(tmp_path)


def install_kinds(seen) -> list[InstallKind]:
    kinds = []
    for status in seen.statuses:
        if not kinds or kinds[-1] is not status.install.kind:
            kinds.append(status.install.kind)
    return kinds


def test_installing_goes_idle_downloading_ready(qapp, make, fake_install):
    checker, seen = make(installer=fake_install.installer())
    check(qapp, checker)
    assert seen.statuses[-1].can_install
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    assert install_kinds(seen) == [InstallKind.IDLE, InstallKind.DOWNLOADING, InstallKind.READY]
    assert any(s.install.percent == 50 for s in seen.statuses)
    assert checker.status.install.path == fake_install.updates_dir / "vitralis-1.4.0.exe"


def test_restart_swaps_before_quitting(qapp, make, fake_install):
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    checker.restart_to_update(lambda: fake_install.events.append("quit"))
    assert fake_install.events == ["swap vitralis-1.3.0.exe vitralis-1.4.0.exe 1.3.0", "quit"]


def test_a_failed_swap_shows_why_and_does_not_quit(qapp, make, fake_install):
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    fake_install.outcome = SwapFailed("couldn't start the new version: denied")
    checker.restart_to_update(lambda: fake_install.events.append("quit"))
    assert "quit" not in fake_install.events
    state = checker.status.install
    assert state.kind is InstallKind.FAILED and state.failure is FailureKind.NOT_REPLACED
    assert state.path is not None  # the download is kept, so Restart can be tried again


def test_an_unexpected_install_failure_shows_its_reason(qapp, make, fake_install):
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    fake_install.outcome = UpdateError("odd")
    checker.restart_to_update(lambda: fake_install.events.append("quit"))
    state = checker.status.install
    assert state.kind is InstallKind.FAILED and state.failure is FailureKind.OTHER and state.detail == "odd"


def test_working_holds_while_a_check_or_a_download_runs(qapp, make, fake_install):
    checker, _ = make(installer=fake_install.installer())
    assert not checker.working
    checker._feed.gate.clear()
    checker.check_now()
    assert checker.working  # its connection must not be closed under it
    checker._feed.gate.set()
    wait_until(qapp, lambda: not checker.working and not checker.busy)
    fake_install.gate.clear()
    checker.install()
    assert checker.working
    fake_install.gate.set()
    wait_until(qapp, lambda: not checker.working)


@pytest.mark.parametrize(
    ("outcome", "failure"),
    [
        (ChecksumMismatch("mismatch"), FailureKind.DAMAGED),
        (DownloadUnreachable("ConnectError: offline"), FailureKind.OFFLINE),
        (DownloadRefused("the exe", 500), FailureKind.REFUSED),
        (UpdateError("odd"), FailureKind.OTHER),
        (RuntimeError("bug"), FailureKind.OTHER),
    ],
)
def test_a_failed_download_shows_why(qapp, make, fake_install, outcome, failure):
    fake_install.outcome = outcome
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    assert checker.status.install.failure is failure
    if failure is FailureKind.REFUSED:
        assert checker.status.install.detail == "500"


def test_a_folder_that_cant_be_written_downloads_nothing(qapp, make, fake_install):
    fake_install.writable = False
    downloads = []
    fake_install.download = lambda *a: downloads.append(a)
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    state = checker.status.install
    assert state.failure is FailureKind.NOT_WRITABLE and state.detail == str(fake_install.exe.parent)
    assert downloads == []


def test_install_is_not_offered_from_source_or_without_a_checksum(qapp, make, fake_install):
    source, _ = make()
    check(qapp, source)
    assert not source.status.can_install
    source.install()  # does nothing
    assert source.status.install.kind is InstallKind.IDLE
    bare, _ = make(feed=FakeFeed(release("v1.4.0", exe=False)), installer=fake_install.installer())
    check(qapp, bare)
    assert not bare.status.can_install


def test_stop_during_a_download_cancels_it(qapp, make, fake_install):
    fake_install.gate.clear()
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    checker.install()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.DOWNLOADING)
    threading.Timer(0.1, fake_install.gate.set).start()
    checker.stop()  # sets the stop event and waits for the thread
    assert not checker._download.is_alive()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.IDLE)


def test_a_download_left_from_an_earlier_run_is_ready_at_start(qapp, make, fake_install):
    fake_install.pending = fake_install.updates_dir / "vitralis-1.4.0.exe"
    checker, _ = make(installer=fake_install.installer())
    checker.start()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    assert checker.status.install.version == "1.4.0"


def test_install_steps_are_logged(qapp, make, fake_install, caplog):
    checker, _ = make(installer=fake_install.installer())
    check(qapp, checker)
    with caplog.at_level(logging.INFO, "vitralis.updates.checker"):
        checker.install()
        wait_until(qapp, lambda: checker.status.install.kind is InstallKind.READY)
    messages = [r.getMessage() for r in caplog.records]
    assert "update install: downloading 1.4.0" in messages and "update install: ready 1.4.0" in messages


@pytest.mark.parametrize("kind", [FeedFailure.OFFLINE, FeedFailure.RATE_LIMITED])
def test_the_kind_of_a_feed_error_reaches_the_status_and_clears_with_the_next_good_check(qapp, make, kind):
    feed = FakeFeed(ReleaseFeedError("ConnectError: no route", kind))
    checker, seen = make(feed=feed)
    check(qapp, checker)
    assert seen.statuses[-1].error_kind is kind and seen.statuses[-1].error
    feed.answer = release("v1.4.0")
    check(qapp, checker)
    assert seen.statuses[-1].error == "" and seen.statuses[-1].error_kind is None


def test_an_unexpected_error_in_the_check_is_of_the_other_kind(qapp, make, caplog):
    checker, seen = make(feed=FakeFeed(RuntimeError("bug")))
    with caplog.at_level(logging.ERROR, "vitralis.updates.checker"):
        check(qapp, checker)
    assert seen.statuses[-1].error_kind is FeedFailure.OTHER and "RuntimeError" in seen.statuses[-1].error
