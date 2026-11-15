#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:08.909997
Revised: 2026/11/15 22:45:18.331560

The update checker on the offscreen ``QApplication``: checks run on their own thread and come back as one
``UpdateStatus``; the six outcomes; skip and Stop skipping; a failed check never loses a known offer; the
schedule (a minute after start, a day after a success, an hour after a failure, the saved last check honoured
and a clock set back capped); a build from source asks nobody; and **Update and restart** downloads, swaps and
quits in order, with Cancel and every failure on the way.
"""

import logging
import threading
from pathlib import Path

import pytest

from tests.qt_support import wait_until
from tests.updates.fakes import FAILED, NOON, TARGET, FakeFeed, MemorySettings, release
from vitralis.updates.check import CheckResult
from vitralis.updates.checker import (
    FAILURE_INTERVAL,
    FIRST_CHECK_DELAY_MS,
    SUCCESS_INTERVAL,
    FailureKind,
    Installer,
    InstallKind,
    UpdateChecker,
)
from vitralis.updates.rules import (
    FOLDER_NOT_WRITABLE,
    CheckKind,
    ChecksumMismatch,
    DownloadFailed,
    Failure,
    NotSigned,
    Reason,
    SourceFailure,
    SwapFailed,
    UpdateCancelled,
    UpdateError,
)

DAY_MS = int(SUCCESS_INTERVAL.total_seconds() * 1000)
HOUR_MS = int(FAILURE_INTERVAL.total_seconds() * 1000)
NOW = 1_800_000_000.0


class Recorder:
    def __init__(self, checker: UpdateChecker) -> None:
        self.statuses = []
        self.busy = []
        checker.changed.connect(self.statuses.append)
        checker.busy_changed.connect(self.busy.append)


@pytest.fixture
def make(qapp):
    made = []

    def build(feed=None, settings=None, current="1.3.0", installer=None, target=TARGET):
        checker = UpdateChecker(
            feed or FakeFeed(),
            settings or MemorySettings(),
            current,
            target,
            clock=lambda: NOON,
            installer=installer,
            wall=lambda: NOW,
        )
        made.append(checker)
        return checker, Recorder(checker)

    yield build
    for checker in made:
        checker.stop()


def check(qapp, checker):
    checker.check_now()
    wait_until(qapp, lambda: not checker.busy)


def test_when_a_check_ends_its_worker_has_ended_too(qapp, make, lingering_workers):
    """Regression guard: the check's worker outlived its answer, so a test that dropped the checker then could
    leave the worker to destroy it, timer and all, on the worker's thread: an access violation in CI."""
    checker, _ = make()
    check(qapp, checker)
    assert not checker.working


def test_check_now_says_busy_then_offers_the_newer_release(qapp, make):
    settings = MemorySettings()
    checker, seen = make(settings=settings)
    check(qapp, checker)
    assert seen.busy == [True, False]
    status = seen.statuses[-1]
    assert status.kind is CheckKind.AVAILABLE and status.offer.release == release("v1.4.0")
    assert status.checked_at == NOON and status.failures == ()
    assert settings.last == NOW  # only a successful check is saved


def test_the_check_runs_on_its_own_named_thread(qapp, make):
    feed = FakeFeed()
    checker, _ = make(feed)
    check(qapp, checker)
    assert feed.threads == ["vitralis-update"]


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        (release("1.3.0"), CheckKind.UP_TO_DATE),
        (release("1.2.0"), CheckKind.UP_TO_DATE),
        (release("1.4.0", missing="sig"), CheckKind.NO_BUILD),
        (release("1.4.0-rc.1"), CheckKind.UP_TO_DATE),
    ],
)
def test_each_outcome_of_a_check(qapp, make, answer, kind):
    checker, _ = make(FakeFeed(answer))
    check(qapp, checker)
    assert checker.status.kind is kind and checker.status.offer is None


def test_both_sources_down_is_a_failed_check_with_both_reasons_and_no_saved_time(qapp, make):
    settings = MemorySettings()
    checker, _ = make(FakeFeed(FAILED), settings)
    check(qapp, checker)
    assert checker.status.kind is CheckKind.FAILED and checker.status.failures == FAILED.failures
    assert settings.last is None and not checker.busy


def test_a_failed_check_never_loses_an_offer_already_known(qapp, make):
    feed = FakeFeed()
    checker, _ = make(feed)
    check(qapp, checker)
    feed.answer = FAILED
    check(qapp, checker)
    assert checker.status.kind is CheckKind.AVAILABLE and checker.status.offer is not None
    assert checker.status.failures == FAILED.failures  # still said, beside the offer
    feed.answer = release("1.4.0")
    check(qapp, checker)
    assert checker.status.failures == ()


def test_a_bug_in_the_check_is_a_failure_not_a_stuck_button(qapp, make, caplog):
    checker, _ = make(FakeFeed(ZeroDivisionError("bug")))
    check(qapp, checker)
    assert checker.status.kind is CheckKind.FAILED and not checker.busy
    assert "failed unexpectedly" in caplog.text


def test_a_second_check_while_one_runs_is_ignored(qapp, make):
    feed = FakeFeed()
    feed.gate.clear()
    checker, _ = make(feed)
    checker.check_now()
    checker.check_now()
    feed.gate.set()
    wait_until(qapp, lambda: not checker.busy)
    assert feed.calls == 1


def test_skip_and_stop_skipping(qapp, make):
    settings = MemorySettings()
    feed = FakeFeed()
    checker, _ = make(feed, settings)
    check(qapp, checker)
    checker.skip()
    assert settings.skipped == "1.4.0" and checker.status.kind is CheckKind.SKIPPED and checker.status.offer is None
    calls = feed.calls
    checker.unskip()  # offers it again and checks at once
    assert settings.skipped == "" and checker.status.kind is CheckKind.AVAILABLE
    wait_until(qapp, lambda: not checker.busy)
    assert feed.calls == calls + 1


def test_skip_before_any_check_does_nothing(qapp, make):
    settings = MemorySettings()
    checker, _ = make(settings=settings)
    checker.skip()
    assert settings.skipped == ""


def test_a_skipped_version_stays_quiet_until_a_newer_one(qapp, make):
    feed = FakeFeed()
    checker, _ = make(feed, MemorySettings(skipped="1.4.0"))
    check(qapp, checker)
    assert checker.status.kind is CheckKind.SKIPPED
    feed.answer = release("1.4.1")
    check(qapp, checker)
    assert checker.status.kind is CheckKind.AVAILABLE


def test_a_build_from_source_asks_nobody_and_schedules_nothing(qapp, make):
    feed = FakeFeed()
    checker, _ = make(feed, target=None, installer=Installer(Path("x.exe"), lambda *a: Path("y")))
    checker.start()
    checker.check_now()
    assert feed.calls == 0 and checker.next_check_ms is None and not checker.busy
    assert checker.status.kind is CheckKind.SOURCE_BUILD and checker.is_source_build
    assert not checker.status.can_install


def test_the_first_check_comes_a_minute_after_start(qapp, make):
    checker, _ = make()
    checker.start()
    assert FIRST_CHECK_DELAY_MS == 60_000
    assert FIRST_CHECK_DELAY_MS - 1000 < checker.next_check_ms <= FIRST_CHECK_DELAY_MS


def test_a_recent_successful_check_puts_the_first_one_off(qapp, make):
    checker, _ = make(settings=MemorySettings(last=NOW - 3600))
    checker.start()
    assert DAY_MS - HOUR_MS - 1000 < checker.next_check_ms <= DAY_MS - HOUR_MS


def test_a_last_check_in_the_future_waits_at_most_one_interval(qapp, make):
    """The clock was set back: never more than a day to the next check."""
    checker, _ = make(settings=MemorySettings(last=NOW + 30 * 86400))
    checker.start()
    assert DAY_MS - 1000 < checker.next_check_ms <= DAY_MS


def test_after_a_success_the_next_check_is_a_day_away_and_after_a_failure_an_hour(qapp, make):
    feed = FakeFeed()
    checker, _ = make(feed)
    check(qapp, checker)
    # Qt rounds what is left of a long timer to whole seconds, so a day read at once can say a second less
    assert DAY_MS - 2000 < checker.next_check_ms <= DAY_MS
    feed.answer = FAILED
    check(qapp, checker)
    assert HOUR_MS - 2000 < checker.next_check_ms <= HOUR_MS


def test_the_timer_checks_only_while_the_switch_is_on(qapp, make):
    feed = FakeFeed()
    settings = MemorySettings(check=False)
    checker, _ = make(feed, settings)
    checker._on_timer()
    assert feed.calls == 0 and checker.next_check_ms is not None
    checker.set_check_enabled(True)
    assert settings.check and checker.check_enabled
    checker._on_timer()
    wait_until(qapp, lambda: not checker.busy)
    assert feed.calls == 1


def test_stop_ends_the_schedule_and_a_late_answer_schedules_nothing(qapp, make):
    feed = FakeFeed()
    feed.gate.clear()
    checker, _ = make(feed)
    checker.start()
    checker.check_now()
    checker.stop()
    feed.gate.set()
    wait_until(qapp, lambda: not checker.busy)
    assert checker.next_check_ms is None


# --- installing ------------------------------------------------------------------------------------------------


class FakeInstall:
    """The download and the swap, scripted: each can raise, the download can be held at a gate."""

    def __init__(self, tmp_path: Path, error: Exception | None = None, swap_error: Exception | None = None):
        self.exe = tmp_path / "vitralis.exe"
        self.exe.write_bytes(b"old")
        self.download_path = tmp_path / "vitralis-update-1.exe"
        self.error = error
        self.swap_error = swap_error
        self.gate = threading.Event()
        self.gate.set()
        self.swapped: list[tuple] = []
        self.threads: list[str] = []
        self.writable = True

    def download(self, offer, progress, cancel):
        self.threads.append(threading.current_thread().name)
        progress(50, 100)
        progress(50, 100)  # the same step twice is sent once
        progress(100, 100)
        while not self.gate.wait(0.01):
            if cancel.is_set():
                raise UpdateCancelled("stopped")
        if self.error is not None:
            raise self.error
        self.download_path.write_bytes(b"new")
        return self.download_path

    def swap(self, running, new, old_version, pid):
        self.threads.append(threading.current_thread().name)
        if self.swap_error is not None:
            raise self.swap_error
        self.swapped.append((running, new, old_version))

    def installer(self) -> Installer:
        return Installer(self.exe, self.download, self.swap, lambda folder: self.writable)


def offered(qapp, make, fake, **kw):
    checker, seen = make(installer=fake.installer(), **kw)
    check(qapp, checker)
    assert checker.status.can_install
    return checker, seen


def test_update_and_restart_downloads_swaps_then_quits(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    checker, seen = offered(qapp, make, fake)
    quits = []
    checker.install(lambda: quits.append(True))
    wait_until(qapp, lambda: quits)
    kinds = [s.install.kind for s in seen.statuses]
    assert InstallKind.DOWNLOADING in kinds and kinds[-1] is InstallKind.REPLACING
    percents = [s.install.percent for s in seen.statuses if s.install.kind is InstallKind.DOWNLOADING]
    assert percents == [None, 50, 100]
    assert fake.swapped == [(fake.exe, fake.download_path, "1.3.0")]
    assert fake.threads == ["vitralis-update-download", "vitralis-update-swap"]


def test_cancel_stops_the_download_and_keeps_the_offer(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.gate.clear()
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    assert checker.status.install.kind is InstallKind.DOWNLOADING
    checker.cancel()
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.IDLE)
    assert checker.status.offer is not None and fake.swapped == []
    fake.gate.set()
    quits = []
    checker.install(lambda: quits.append(True))  # a fresh cancel flag: the earlier Cancel doesn't stop it
    wait_until(qapp, lambda: quits)


def test_cancel_with_nothing_downloading_does_nothing(qapp, make, tmp_path):
    checker, _ = offered(qapp, make, FakeInstall(tmp_path))
    checker.cancel()
    assert checker.status.install.kind is InstallKind.IDLE


@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (ChecksumMismatch("x"), FailureKind.DAMAGED),
        (NotSigned("x"), FailureKind.NOT_SIGNED),
        (DownloadFailed(Failure(Reason.ANSWERED, 503)), FailureKind.NOT_DOWNLOADED),
        (UpdateError("disk full"), FailureKind.NOT_DOWNLOADED),
        (ZeroDivisionError("bug"), FailureKind.NOT_DOWNLOADED),
    ],
)
def test_a_failed_download_says_why_and_never_swaps(qapp, make, tmp_path, error, failure):
    fake = FakeInstall(tmp_path, error=error)
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    state = checker.status.install
    assert state.failure is failure and fake.swapped == []
    assert state.version == "1.4.0" and state.page_url.endswith("/v1.4.0") and state.path == str(fake.exe)
    if isinstance(error, DownloadFailed):
        assert state.reason == Failure(Reason.ANSWERED, 503)


def test_a_failed_swap_says_where_and_why_and_doesnt_quit(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path, swap_error=SwapFailed("couldn't move vitralis.exe aside: in use"))
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    state = checker.status.install
    assert state.failure is FailureKind.NOT_REPLACED and "in use" in state.detail and state.path == str(fake.exe)


def test_a_bug_in_the_swap_is_a_failure_not_a_stuck_line(qapp, make, tmp_path, caplog):
    fake = FakeInstall(tmp_path, swap_error=ZeroDivisionError("bug"))
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    assert "unexpectedly" in caplog.text


def test_a_folder_that_cant_be_written_is_said_before_downloading(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.writable = False
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    state = checker.status.install
    assert state.failure is FailureKind.NOT_REPLACED and state.detail == FOLDER_NOT_WRITABLE
    assert fake.threads == []


def test_quitting_mid_download_cancels_and_deletes_and_never_swaps(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    fake.gate.clear()
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: pytest.fail("quit"))
    checker.stop()  # waits for the download thread
    assert not checker.working or checker._download is None or not checker._download.is_alive()
    qapp.processEvents()
    assert fake.swapped == []


def test_a_download_that_finishes_as_vitralis_quits_is_deleted_not_swapped(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    checker, _ = offered(qapp, make, fake)
    fake.download_path.write_bytes(b"new")
    checker._quitting = True
    checker._on_downloaded(checker.status.offer, fake.download_path)
    assert not fake.download_path.exists() and fake.swapped == []
    assert checker.status.install.kind is InstallKind.IDLE


def test_install_needs_an_offer_an_installer_and_nothing_under_way(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path)
    checker, _ = make(installer=fake.installer())
    checker.install(lambda: None)  # nothing offered yet
    assert fake.threads == []
    plain, _ = make()
    check(qapp, plain)
    plain.install(lambda: None)  # no installer: not the packaged exe
    assert plain.status.install.kind is InstallKind.IDLE and not plain.status.can_install
    fake.gate.clear()
    check(qapp, checker)
    checker.install(lambda: None)
    checker.install(lambda: None)  # a second press while downloading
    fake.gate.set()
    wait_until(qapp, lambda: checker.status.install.kind is not InstallKind.DOWNLOADING)
    assert fake.threads.count("vitralis-update-download") == 1


def test_skipping_after_a_failed_install_clears_the_failure(qapp, make, tmp_path):
    fake = FakeInstall(tmp_path, error=ChecksumMismatch("x"))
    checker, _ = offered(qapp, make, fake)
    checker.install(lambda: None)
    wait_until(qapp, lambda: checker.status.install.kind is InstallKind.FAILED)
    checker.skip()
    assert checker.status.install.kind is InstallKind.IDLE


def test_an_offer_is_logged_once_per_version(qapp, make, caplog):
    feed = FakeFeed()
    checker, _ = make(feed)
    with caplog.at_level(logging.INFO, "vitralis.updates.checker"):
        check(qapp, checker)
        check(qapp, checker)
    assert sum("is available" in r.getMessage() for r in caplog.records) == 1


def test_a_check_result_with_both_a_release_and_failures_uses_the_release(qapp, make):
    answer = CheckResult(release("1.4.0", source="GitLab"), (SourceFailure("GitHub", Failure(Reason.TIMED_OUT)),))
    checker, _ = make(FakeFeed(answer))
    check(qapp, checker)
    assert checker.status.kind is CheckKind.AVAILABLE and checker.status.failures == ()
