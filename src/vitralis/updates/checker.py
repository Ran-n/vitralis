#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:01.548894
Revised: 2026/11/15 14:27:01.972462

The updater's state and timing, for the UI. The first automatic check comes ``FIRST_CHECK_DELAY_MS`` after
start (so it doesn't compete with start-up), then ``SUCCESS_INTERVAL`` after the last successful one (saved
across starts) or ``FAILURE_INTERVAL`` after a failed one. **Update and restart** proves and downloads the
offered exe, puts it in place and restarts into it; **Cancel** stops the download. The network work runs on
named worker threads whose results come back through queued signals, so the UI never waits on the network.
Everything the UI shows comes from one ``UpdateStatus``, sent on ``changed``. A build from source asks nobody.
"""

import datetime as dt
import enum
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from vitralis.updates.check import CheckResult
from vitralis.updates.install import can_write, swap_and_start
from vitralis.updates.rules import (
    FOLDER_NOT_WRITABLE,
    CheckKind,
    ChecksumMismatch,
    DownloadFailed,
    Failure,
    NotSigned,
    Offer,
    Reason,
    Release,
    SourceFailure,
    SwapFailed,
    UpdateCancelled,
    UpdateError,
    decide,
    parse_version_or_none,
)
from vitralis.updates.target import asset_name

logger = logging.getLogger("vitralis.updates.checker")

FIRST_CHECK_DELAY_MS = 60_000
SUCCESS_INTERVAL = dt.timedelta(hours=24)
FAILURE_INTERVAL = dt.timedelta(hours=1)
DOWNLOAD_JOIN_SECONDS = 5.0
"""How long quitting waits for a stopped download to delete its file."""


class UpdateSettings(Protocol):
    """The saved update settings; ``SettingsManager`` in the app."""

    def update_check(self) -> bool: ...

    def set_update_check(self, enabled: bool) -> None: ...

    def skipped_version(self) -> str: ...

    def set_skipped_version(self, version: str) -> None: ...

    def last_check(self) -> float | None: ...

    def set_last_check(self, when: float) -> None: ...


class InstallKind(enum.Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    REPLACING = "replacing"
    """Proven and downloaded: the exe is being put in place, then Vitralis restarts into it."""
    FAILED = "failed"


class FailureKind(enum.Enum):
    DAMAGED = "damaged"
    """The download didn't match its checksum, or the checksum file couldn't be read."""
    NOT_SIGNED = "not_signed"
    """The signature isn't a trusted key's, or isn't over this version and file."""
    NOT_REPLACED = "not_replaced"
    """The exe couldn't be put in place, or started; ``detail`` is the reason, ``path`` where."""
    NOT_DOWNLOADED = "not_downloaded"
    """A request failed; ``reason`` says why, ``detail`` when it isn't a network reason."""


@dataclass(frozen=True, slots=True)
class InstallState:
    kind: InstallKind = InstallKind.IDLE
    version: str = ""
    received: int = 0
    total: int | None = None
    failure: FailureKind | None = None
    reason: Failure | None = None
    detail: str = ""
    path: str = ""
    page_url: str = ""

    @property
    def percent(self) -> int | None:
        return None if not self.total else min(100, self.received * 100 // self.total)


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    current: str
    target: str | None
    """The release target, or ``None`` for a build from source."""
    kind: CheckKind | None = None
    """What the last successful check came to (``SOURCE_BUILD`` without a target); ``None`` before the first
    one, ``FAILED`` when no check has worked yet and the last one failed."""
    latest: Release | None = None
    offer: Offer | None = None
    checked_at: dt.datetime | None = None
    failures: tuple[SourceFailure, ...] = ()
    """Why the last check failed, each source's reason; empty when it worked."""
    install: InstallState = field(default_factory=InstallState)
    can_install: bool = False
    """This is the packaged exe, and a release is offered."""


@dataclass(frozen=True, slots=True)
class Installer:
    """What installing needs; only the packaged release exe has one."""

    exe: Path
    download: Callable[[Offer, Callable[[int, int | None], None], threading.Event], Path]
    swap: Callable[[Path, Path, str, int], None] = swap_and_start
    writable: Callable[[Path], bool] = can_write


def local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


class UpdateChecker(QObject):
    changed = pyqtSignal(object)
    """The ``UpdateStatus``, on the UI thread, after every check, skip and install step."""
    busy_changed = pyqtSignal(bool)
    """Whether a check is under way."""
    _checked = pyqtSignal(object)
    _install_step = pyqtSignal(object)
    _downloaded = pyqtSignal(object, object)
    """(the offer, the proven exe's path) from the download thread."""
    _replaced = pyqtSignal()

    def __init__(
        self,
        check: Callable[[], CheckResult],
        settings: UpdateSettings,
        current: str,
        target: str | None,
        clock: Callable[[], dt.datetime] = local_now,
        installer: Installer | None = None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        super().__init__()
        self._check = check
        self._settings = settings
        self._current_text = current
        self._current = parse_version_or_none(current)
        self._target = target
        self._clock = clock
        self._wall = wall
        self._installer = installer if target is not None else None
        self._busy = False
        self._kind: CheckKind | None = CheckKind.SOURCE_BUILD if target is None else None
        self._latest: Release | None = None
        self._checked_at: dt.datetime | None = None
        self._failures: tuple[SourceFailure, ...] = ()
        self._install = InstallState()
        self._announced: set[str] = set()
        self._cancel = threading.Event()
        self._quitting = False
        self._download: threading.Thread | None = None
        self._workers: list[threading.Thread] = []
        self._quit_app: Callable[[], None] | None = None
        self._status = self._compute()
        self._checked.connect(self._on_checked)
        self._install_step.connect(self._set_install)
        self._downloaded.connect(self._on_downloaded)
        self._replaced.connect(self._on_replaced)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

    # --- state ----------------------------------------------------------------------------------------------

    @property
    def status(self) -> UpdateStatus:
        return self._status

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def is_source_build(self) -> bool:
        return self._target is None

    @property
    def check_enabled(self) -> bool:
        return self._settings.update_check()

    def set_check_enabled(self, enabled: bool) -> None:
        self._settings.set_update_check(enabled)
        logger.info("automatic update checks %s", "on" if enabled else "off")

    # --- life cycle -----------------------------------------------------------------------------------------

    def start(self) -> None:
        """Schedule the first automatic check: ``FIRST_CHECK_DELAY_MS`` from now, or later when the last
        successful check is younger than ``SUCCESS_INTERVAL`` (but never more than one interval away, should
        the clock have been set back). A build from source schedules nothing."""
        if self.is_source_build:
            return
        self._quitting = False
        delay = FIRST_CHECK_DELAY_MS
        last = self._settings.last_check()
        if last is not None:
            interval = SUCCESS_INTERVAL.total_seconds()
            due = min(last + interval - self._wall(), interval)
            delay = max(delay, int(due * 1000))
        self._timer.start(delay)

    @property
    def next_check_ms(self) -> int | None:
        """How long until the next automatic check, for tests; ``None`` when none is scheduled."""
        return self._timer.remainingTime() if self._timer.isActive() else None

    def _work(self, target: Callable[[], None], name: str, daemon: bool = True) -> None:
        self._workers = [worker for worker in self._workers if worker.is_alive()]
        self._workers.append(threading.Thread(target=target, name=name, daemon=daemon))
        self._workers[-1].start()

    @property
    def working(self) -> bool:
        """Whether a check, a download or a swap still runs on its thread."""
        downloading = self._download is not None and self._download.is_alive()
        return downloading or any(worker.is_alive() for worker in self._workers)

    def stop(self, wait: bool = True) -> None:
        """Stop the timer and any download (whose file is deleted), waiting for the download to end unless told
        not to. A check under way is abandoned: it only reads. Safe to call twice."""
        self._timer.stop()
        self._quitting = True
        self._cancel.set()
        if wait and self._download is not None and self._download.is_alive():
            self._download.join(DOWNLOAD_JOIN_SECONDS)
            if self._download.is_alive():
                logger.warning("the update download didn't stop within %.0f s", DOWNLOAD_JOIN_SECONDS)

    def _on_timer(self) -> None:
        if self._settings.update_check():
            self.check_now()
        else:
            self._timer.start(int(SUCCESS_INTERVAL.total_seconds() * 1000))

    # --- checking -------------------------------------------------------------------------------------------

    def check_now(self) -> None:
        """Ask every source on a worker thread; the answer comes back through ``changed``."""
        if self._busy or self.is_source_build:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                result = self._check()
            except Exception:  # a bug must not leave Check now dimmed for ever
                logger.exception("the update check failed unexpectedly")
                result = CheckResult(None, (SourceFailure("Vitralis", Failure(Reason.UNREADABLE)),))
            self._checked.emit(result)

        self._work(worker, "vitralis-update")

    def _on_checked(self, result: CheckResult) -> None:
        self._set_busy(False)
        if result.release is not None:
            self._latest, self._failures, self._checked_at = result.release, (), self._clock()
            self._settings.set_last_check(self._wall())
            interval = SUCCESS_INTERVAL
            logger.info("update check: %s %s", result.release.source, result.release.version)
        else:
            self._failures = result.failures
            interval = FAILURE_INTERVAL
            reasons = "; ".join(
                f"{f.source}: {f.failure.reason.value.format(status=f.failure.status)}" for f in result.failures
            )
            logger.warning("couldn't check for updates: %s", reasons)
        if not self._quitting:
            self._timer.start(int(interval.total_seconds() * 1000))
        self._publish()

    def skip(self) -> None:
        if self._latest is None:
            return
        self._settings.set_skipped_version(str(self._latest.version))
        logger.info("skipping version %s", self._latest.version)
        if self._install.kind is InstallKind.FAILED:
            self._install = InstallState()
        self._publish()

    def unskip(self) -> None:
        """Offer the skipped version again, and check at once."""
        self._settings.set_skipped_version("")
        logger.info("no version skipped any more")
        self._publish()
        self.check_now()

    # --- installing -----------------------------------------------------------------------------------------

    def install(self, quit_app: Callable[[], None]) -> None:
        """**Update and restart**: prove and download the offered exe on a worker thread, put it in place and
        quit through ``quit_app`` (the clean shutdown); the new exe starts once this one has gone."""
        offer = self._status.offer
        if (
            self._installer is None
            or offer is None
            or self._install.kind in (InstallKind.DOWNLOADING, InstallKind.REPLACING)
        ):
            return
        version = str(offer.release.version)
        folder = self._installer.exe.parent
        if not self._installer.writable(folder):
            self._set_install(self._failed(offer, FailureKind.NOT_REPLACED, FOLDER_NOT_WRITABLE))
            return
        self._quit_app = quit_app
        self._cancel = threading.Event()  # a fresh one: an earlier Cancel mustn't stop this download
        cancel = self._cancel
        self._set_install(InstallState(InstallKind.DOWNLOADING, version, page_url=offer.release.page_url))
        installer = self._installer
        last_step = -1

        def progress(received: int, total: int | None) -> None:
            nonlocal last_step
            step = received * 100 // total if total else received >> 20  # a percent, else whole MiB
            if step != last_step:
                last_step = step
                page = offer.release.page_url
                self._install_step.emit(InstallState(InstallKind.DOWNLOADING, version, received, total, page_url=page))

        def worker() -> None:
            logger.info("downloading %s", offer.asset)
            try:
                path = installer.download(offer, progress, cancel)
            except UpdateCancelled:
                logger.info("the download of %s was cancelled", offer.asset)
                self._install_step.emit(InstallState())
            except ChecksumMismatch as ex:
                logger.error("refused %s: %s", offer.asset, ex)
                self._install_step.emit(self._failed(offer, FailureKind.DAMAGED))
            except NotSigned as ex:
                logger.error("refused %s: %s", offer.asset, ex)
                self._install_step.emit(self._failed(offer, FailureKind.NOT_SIGNED))
            except DownloadFailed as ex:
                logger.warning("couldn't download %s: %s", offer.asset, ex)
                self._install_step.emit(replace(self._failed(offer, FailureKind.NOT_DOWNLOADED), reason=ex.failure))
            except UpdateError as ex:
                logger.warning("couldn't download %s: %s", offer.asset, ex)
                self._install_step.emit(self._failed(offer, FailureKind.NOT_DOWNLOADED, str(ex)))
            except Exception as ex:  # a bug must not leave the download line up for ever
                logger.exception("the update download failed unexpectedly")
                self._install_step.emit(self._failed(offer, FailureKind.NOT_DOWNLOADED, f"{type(ex).__name__}: {ex}"))
            else:
                self._downloaded.emit(offer, path)

        self._download = threading.Thread(target=worker, name="vitralis-update-download", daemon=True)
        self._download.start()

    def cancel(self) -> None:
        """Stop the download; its file is deleted and the offer stays."""
        if self._install.kind is InstallKind.DOWNLOADING:
            self._cancel.set()

    def _failed(self, offer: Offer, failure: FailureKind, detail: str = "") -> InstallState:
        path = str(self._installer.exe) if self._installer is not None else ""
        version = str(offer.release.version)
        page = offer.release.page_url
        return InstallState(InstallKind.FAILED, version, failure=failure, detail=detail, path=path, page_url=page)

    def _on_downloaded(self, offer: Offer, path: Path) -> None:
        """Put the proven exe in place on a thread of its own (across drives it is copied, which takes a
        while), then quit. Not a daemon: a quit that comes meanwhile waits for the exe to be whole."""
        if self._quitting or self._cancel.is_set() or self._installer is None:
            try:
                path.unlink(missing_ok=True)
            except OSError as ex:
                logger.warning("couldn't delete %s: %s", path, ex)
            self._set_install(InstallState())
            return
        installer = self._installer
        self._set_install(InstallState(InstallKind.REPLACING, str(offer.release.version)))

        def worker() -> None:
            try:
                installer.swap(installer.exe, path, self._current_text, os.getpid())
            except SwapFailed as ex:
                logger.error("couldn't install %s: %s", offer.release.version, ex)
                self._install_step.emit(self._failed(offer, FailureKind.NOT_REPLACED, str(ex)))
            except Exception as ex:  # a bug must not leave the install line up for ever
                logger.exception("putting the update in place failed unexpectedly")
                self._install_step.emit(self._failed(offer, FailureKind.NOT_REPLACED, f"{type(ex).__name__}: {ex}"))
            else:
                logger.info("installed %s; restarting into it", offer.release.version)
                self._replaced.emit()

        self._work(worker, "vitralis-update-swap", daemon=False)

    def _on_replaced(self) -> None:
        quit_app, self._quit_app = self._quit_app, None
        if quit_app is not None:
            quit_app()

    def _set_install(self, state: InstallState) -> None:
        if state.kind is not self._install.kind:
            logger.info("update install: %s %s", state.kind.value, state.version)
        self._install = state
        self._publish()

    # --- publishing -----------------------------------------------------------------------------------------

    def _compute(self) -> UpdateStatus:
        kind, offer = self._kind, None
        if self._latest is not None and self._target is not None:
            asset = asset_name(self._latest.version, self._target)
            kind, offer = decide(self._current, self._latest, self._settings.skipped_version(), asset)
        elif self._failures and self._target is not None:
            kind = CheckKind.FAILED
        return UpdateStatus(
            current=self._current_text,
            target=self._target,
            kind=kind,
            latest=self._latest,
            offer=offer,
            checked_at=self._checked_at,
            failures=self._failures,
            install=self._install,
            can_install=self._installer is not None and offer is not None,
        )

    def _publish(self) -> None:
        self._status = self._compute()
        offer = self._status.offer
        if offer is not None and str(offer.release.version) not in self._announced:
            self._announced.add(str(offer.release.version))
            logger.info("version %s is available (running %s)", offer.release.version, self._current_text)
        self.changed.emit(self._status)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)
