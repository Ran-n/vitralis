#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:01.548894
Revised: 2026/11/14 00:23:16.448983

Asks for the latest release at start (after ``FIRST_CHECK_DELAY_MS``, so start-up isn't slowed) and then
every ``UPDATE_CHECK_EVERY``, and, in the packaged exe, downloads and installs it on request. The network work
runs on worker threads whose results come back through queued signals, as in ``LicenceGate``, so the UI never
waits on the network. Everything the UI shows comes from one ``UpdateStatus``, sent on ``changed``.
"""

import datetime as dt
import enum
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from vitralis.updates.github import ReleaseFeed, ReleaseFeedError
from vitralis.updates.install import can_write, pending, swap_and_start
from vitralis.updates.rules import (
    ChecksumMismatch,
    DownloadUnreachable,
    FeedFailure,
    Release,
    UpdateCancelled,
    UpdateError,
    Version,
    exe_version,
    is_newer,
    parse_version_or_none,
    update_to_offer,
)

logger = logging.getLogger("vitralis.updates.checker")

UPDATE_CHECK_EVERY = dt.timedelta(hours=24)
FIRST_CHECK_DELAY_MS = 10_000
DOWNLOAD_JOIN_SECONDS = 5.0
"""How long quitting waits for a stopped download to delete its ``.part`` file."""


class UpdateSettings(Protocol):
    """The saved update settings; ``SettingsManager`` in the app."""

    def update_check(self) -> bool: ...

    def set_update_check(self, enabled: bool) -> None: ...

    def skipped_version(self) -> str: ...

    def set_skipped_version(self, version: str) -> None: ...


class InstallKind(enum.Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"


class FailureKind(enum.Enum):
    DAMAGED = "damaged"
    """The checksum didn't match."""
    NOT_WRITABLE = "not_writable"
    """The exe's folder can't be written to; ``detail`` is the folder."""
    OFFLINE = "offline"
    """The download's server couldn't be reached, or the connection broke."""
    OTHER = "other"
    """``detail`` is the reason."""


@dataclass(frozen=True, slots=True)
class InstallState:
    kind: InstallKind = InstallKind.IDLE
    version: str = ""
    received: int = 0
    total: int | None = None
    path: Path | None = None
    failure: FailureKind | None = None
    detail: str = ""

    @property
    def percent(self) -> int | None:
        return None if not self.total else min(100, self.received * 100 // self.total)


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    current: str
    latest: Release | None = None
    offered: Release | None = None
    """``latest`` when it is newer than the running version and not skipped."""
    newer: bool = False
    """``latest`` is newer than the running version, skipped or not."""
    checked_at: dt.datetime | None = None
    error: str = ""
    """Why the last check failed, for the log and for failures the user can't act on; ``""`` when it worked."""
    error_kind: FeedFailure | None = None
    """What kind of failure ``error`` is; ``None`` when the last check worked."""
    install: InstallState = field(default_factory=InstallState)
    can_install: bool = False
    """This is the packaged exe and the offered release carries an exe with a checksum."""


@dataclass(frozen=True, slots=True)
class Installer:
    """What installing needs; only the packaged exe has one."""

    exe: Path
    updates_dir: Path
    download: Callable[[Release, Callable[[int, int | None], None], threading.Event], Path]
    swap: Callable[[Path, Path, str, int], None] = swap_and_start
    find_pending: Callable[[Path, Version | None], Path | None] = pending
    writable: Callable[[Path], bool] = can_write


def local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


class UpdateChecker(QObject):
    changed = pyqtSignal(object)
    """The ``UpdateStatus``, on the UI thread, after every check, skip and install step."""
    busy_changed = pyqtSignal(bool)
    """Whether a check is under way."""
    _checked = pyqtSignal(object, object, object)
    """(release or ``None``, error text or ``None``, its ``FeedFailure`` or ``None``) from the check thread."""
    _install_step = pyqtSignal(object)
    """An ``InstallState`` from the download or pending thread."""

    def __init__(
        self,
        feed: ReleaseFeed,
        settings: UpdateSettings,
        current: str,
        clock: Callable[[], dt.datetime] = local_now,
        installer: Installer | None = None,
    ) -> None:
        super().__init__()
        self._feed = feed
        self._settings = settings
        self._current_text = current
        self._current = parse_version_or_none(current)
        self._clock = clock
        self._installer = installer
        self._busy = False
        self._latest: Release | None = None
        self._checked_at: dt.datetime | None = None
        self._error = ""
        self._error_kind: FeedFailure | None = None
        self._install = InstallState()
        self._announced: set[Version] = set()
        self._stop = threading.Event()
        self._download: threading.Thread | None = None
        self._status = self._compute()
        self._checked.connect(self._on_checked)
        self._install_step.connect(self._on_install_step)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)

    # --- state ----------------------------------------------------------------------------------------------

    @property
    def status(self) -> UpdateStatus:
        return self._status

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def check_enabled(self) -> bool:
        return self._settings.update_check()

    def set_check_enabled(self, enabled: bool) -> None:
        self._settings.set_update_check(enabled)
        logger.info("automatic update checks %s", "on" if enabled else "off")

    # --- life cycle -----------------------------------------------------------------------------------------

    def start(self) -> None:
        """The first check in ``FIRST_CHECK_DELAY_MS``, then one every ``UPDATE_CHECK_EVERY`` while the switch is
        on; in the packaged exe, an update downloaded earlier is offered for a restart straight away."""
        self._stop.clear()
        self._timer.start(FIRST_CHECK_DELAY_MS)
        if self._installer is not None and self._install.kind is InstallKind.IDLE:
            threading.Thread(target=self._find_pending, name="vitralis-update-pending", daemon=True).start()

    def stop(self) -> None:
        """Stop the timer and any download (whose ``.part`` file is deleted). Safe to call twice."""
        self._timer.stop()
        self._stop.set()
        if self._download is not None and self._download.is_alive():
            self._download.join(DOWNLOAD_JOIN_SECONDS)
            if self._download.is_alive():
                logger.warning("the update download didn't stop within %.0f s", DOWNLOAD_JOIN_SECONDS)

    def _on_timer(self) -> None:
        self._timer.setInterval(int(UPDATE_CHECK_EVERY.total_seconds() * 1000))
        if self._settings.update_check():
            self.check_now()

    # --- checking -------------------------------------------------------------------------------------------

    def check_now(self) -> None:
        """Ask the feed on a worker thread; the answer comes back through ``changed``."""
        if self._busy:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                self._checked.emit(self._feed.latest(), None, None)
            except ReleaseFeedError as ex:
                self._checked.emit(None, str(ex), ex.kind)
            except Exception as ex:  # a bug must not leave Check now dimmed for ever
                logger.exception("the update check failed unexpectedly")
                self._checked.emit(None, f"{type(ex).__name__}: {ex}", FeedFailure.OTHER)

        threading.Thread(target=worker, name="vitralis-update-check", daemon=True).start()

    def _on_checked(self, release: Release | None, error: str | None, kind: FeedFailure | None) -> None:
        if release is not None:
            self._latest, self._error, self._error_kind, self._checked_at = release, "", None, self._clock()
            if is_newer(self._current, release) and release.version not in self._announced:
                self._announced.add(release.version)
                logger.info("version %s is out (running %s)", release.version, self._current_text)
        else:
            self._error, self._error_kind = error or "", kind or FeedFailure.OTHER
        self._set_busy(False)
        self._publish()

    def skip(self) -> None:
        if self._latest is None:
            return
        self._settings.set_skipped_version(str(self._latest.version))
        logger.info("skipping version %s", self._latest.version)
        self._publish()

    def unskip(self) -> None:
        self._settings.set_skipped_version("")
        logger.info("no version skipped any more")
        self._publish()

    # --- installing -----------------------------------------------------------------------------------------

    def install(self) -> None:
        """Download and verify the offered release on a worker thread (packaged exe only)."""
        release = self._status.offered
        if (
            self._installer is None
            or release is None
            or not release.installable
            or self._install.kind in (InstallKind.DOWNLOADING, InstallKind.READY)
        ):
            return
        version = str(release.version)
        folder = self._installer.exe.parent
        if not self._installer.writable(folder):
            self._set_install(
                InstallState(InstallKind.FAILED, version, failure=FailureKind.NOT_WRITABLE, detail=str(folder))
            )
            return
        self._stop.clear()
        self._set_install(InstallState(InstallKind.DOWNLOADING, version))
        installer = self._installer
        last_step = -1

        def progress(received: int, total: int | None) -> None:
            nonlocal last_step
            step = received * 100 // total if total else received >> 20  # a percent, else whole MB
            if step != last_step:
                last_step = step
                self._install_step.emit(InstallState(InstallKind.DOWNLOADING, version, received, total))

        def worker() -> None:
            try:
                path = installer.download(release, progress, self._stop)
                self._install_step.emit(InstallState(InstallKind.READY, version, path=path))
            except UpdateCancelled:
                self._install_step.emit(InstallState())
            except ChecksumMismatch:
                self._install_step.emit(InstallState(InstallKind.FAILED, version, failure=FailureKind.DAMAGED))
            except DownloadUnreachable as ex:
                logger.warning("couldn't download %s: %s", version, ex)
                self._install_step.emit(InstallState(InstallKind.FAILED, version, failure=FailureKind.OFFLINE))
            except UpdateError as ex:
                logger.warning("couldn't download %s: %s", version, ex)
                self._install_step.emit(
                    InstallState(InstallKind.FAILED, version, failure=FailureKind.OTHER, detail=str(ex))
                )
            except Exception as ex:  # a bug must not leave the download line up for ever
                logger.exception("the update download failed unexpectedly")
                detail = f"{type(ex).__name__}: {ex}"
                self._install_step.emit(
                    InstallState(InstallKind.FAILED, version, failure=FailureKind.OTHER, detail=detail)
                )

        self._download = threading.Thread(target=worker, name="vitralis-update-download", daemon=True)
        self._download.start()

    def restart_to_update(self, quit_app: Callable[[], None]) -> None:
        """Put the downloaded exe in place, start it, then quit through ``quit_app`` (the clean shutdown)."""
        if self._installer is None or self._install.kind is not InstallKind.READY or self._install.path is None:
            return
        try:
            self._installer.swap(self._installer.exe, self._install.path, self._current_text, os.getpid())
        except UpdateError as ex:
            logger.error("couldn't install %s: %s", self._install.version, ex)
            self._set_install(
                replace(self._install, kind=InstallKind.FAILED, failure=FailureKind.OTHER, detail=str(ex))
            )
            return
        logger.info("restarting into %s", self._install.version)
        quit_app()

    def _find_pending(self) -> None:
        try:
            path = self._installer.find_pending(self._installer.updates_dir, self._current)
        except Exception:
            logger.exception("looking for a downloaded update failed")
            return
        if path is not None:
            version = exe_version(path.name)
            logger.info("found the downloaded update %s", path)
            self._install_step.emit(InstallState(InstallKind.READY, str(version), path=path))

    def _on_install_step(self, state: InstallState) -> None:
        self._set_install(state)

    def _set_install(self, state: InstallState) -> None:
        if state.kind is not self._install.kind:
            logger.info("update install: %s %s", state.kind.value, state.version)
        self._install = state
        self._publish()

    # --- publishing -----------------------------------------------------------------------------------------

    def _compute(self) -> UpdateStatus:
        latest = self._latest
        offered = None if latest is None else update_to_offer(self._current, latest, self._settings.skipped_version())
        return UpdateStatus(
            current=self._current_text,
            latest=latest,
            offered=offered,
            newer=latest is not None and is_newer(self._current, latest),
            checked_at=self._checked_at,
            error=self._error,
            error_kind=self._error_kind if self._error else None,
            install=self._install,
            can_install=self._installer is not None and offered is not None and offered.installable,
        )

    def _publish(self) -> None:
        self._status = self._compute()
        self.changed.emit(self._status)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)
