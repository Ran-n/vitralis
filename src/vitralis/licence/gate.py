#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.187945
Revised: 2026/11/11 11:06:53.501959

Keeps Vitralis behind its licence. The overlay, the toolbar, the tray and the global hotkeys only exist while
the licence holds (``on_unlock`` builds them, ``on_lock`` tears them down); otherwise the licence window asks
for a key or for an online check.

Everything that goes to the server (activating, checking) runs on a worker thread; its result comes back to
the UI thread through a queued signal, so the UI never waits on the network. The daily check runs in
``LicenceChecks``; a watch timer also asks the saved licence now and then, so 30 days offline or a clock set
back lock the app while it runs, not only at the next start.
"""

import datetime as dt
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from vitralis.licence.client import Licence, LicenceCheckFailed, LicenceChecks
from vitralis.licence.messages import save_failed_message, status_message
from vitralis.licence.ports import LicenceStoreError
from vitralis.licence.rules import LicenceKind, LicenceStatus

logger = logging.getLogger("vitralis.licence.gate")

WATCH_INTERVAL_MS = 60_000
"""How often the saved licence is asked while the app runs (offline; costs nothing)."""


class LicencePrompt(Protocol):
    """The window that asks for a key; ``LicenceWindow`` in the app, a fake in tests."""

    def show_status(self, status: LicenceStatus) -> None: ...

    def show_error(self, text: str) -> None: ...

    def set_busy(self, busy: bool) -> None: ...

    def dismiss(self) -> None: ...


class LicenceGate(QObject):
    changed = pyqtSignal(object)
    """The licence's ``LicenceStatus``, on the UI thread, after every change, activation and check."""
    busy_changed = pyqtSignal(bool)
    """Whether an activation or a check is under way."""
    error = pyqtSignal(str)
    """A translated sentence for something that went wrong without changing the licence."""
    _finished = pyqtSignal(object, object)
    """(status or ``None``, error text or ``None``) from a worker thread."""
    _reported = pyqtSignal(object)
    """A status from the daily checker's thread."""

    def __init__(
        self,
        licence: Licence,
        checks: LicenceChecks,
        on_unlock: Callable[[], None],
        on_lock: Callable[[], None],
        make_prompt: Callable[["LicenceGate"], LicencePrompt],
    ) -> None:
        super().__init__()
        self._licence = licence
        self._checks = checks
        self._on_unlock = on_unlock
        self._on_lock = on_lock
        self._make_prompt = make_prompt
        self._prompt: LicencePrompt | None = None
        self._unlocked = False
        self._busy = False
        self._started = False
        self._finished.connect(self._on_finished)
        self._reported.connect(self.apply)
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_INTERVAL_MS)
        self._watch.timeout.connect(self.refresh)

    # --- state ----------------------------------------------------------------------------------------------

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    @property
    def busy(self) -> bool:
        return self._busy

    def status(self) -> LicenceStatus:
        return self._licence.status()

    def server_time(self) -> dt.datetime:
        return self._licence.server_time()

    # --- life cycle -----------------------------------------------------------------------------------------

    def begin(self) -> None:
        """Unlock straight away on a saved licence, or show the licence window; start the daily checks."""
        self._checks.subscribe(self._reported.emit)
        self._checks.start()
        self._started = True
        self._watch.start()
        self.apply(self._licence.status())
        if self._licence.unreadable is not None:  # another program holds the file: say so, never overwrite it
            self._report_error(save_failed_message(self._licence.unreadable))

    def shutdown(self) -> None:
        """Stop the watch and the daily checks (a check under way finishes first). Safe to call twice."""
        self._watch.stop()
        if self._started:
            self._started = False
            self._checks.stop()
        if self._prompt is not None:
            self._prompt.dismiss()
            self._prompt = None

    def refresh(self) -> None:
        """Ask the saved licence again and act on it (lock when it no longer holds)."""
        self.apply(self._licence.status())

    def apply(self, status: LicenceStatus) -> None:
        """Unlock on a licence that holds; otherwise lock and show why."""
        if status.licensed:
            if self._prompt is not None:
                self._prompt.dismiss()
                self._prompt = None
            if not self._unlocked:
                self._unlocked = True
                logger.info("licensed: starting Vitralis")
                self._on_unlock()
        else:
            if self._unlocked:
                self._unlocked = False
                logger.warning("the licence no longer holds (%s): locking Vitralis", status.kind)
                self._on_lock()
            if self._prompt is None:
                self._prompt = self._make_prompt(self)
            self._prompt.show_status(status)
        self.changed.emit(status)

    # --- online ---------------------------------------------------------------------------------------------

    def activate(self, typed_key: str) -> None:
        """Activate ``typed_key`` on a worker thread; the outcome comes back through ``apply``."""
        self._run("activate", lambda: self._licence.activate(typed_key))

    def check_now(self) -> None:
        """Check the licence online on a worker thread."""
        self._run("check", self._licence.check)

    def _run(self, name: str, work: Callable[[], LicenceStatus]) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                self._finished.emit(work(), None)
            except LicenceCheckFailed as ex:
                logger.warning("licence check failed: %s", ex)
                self._finished.emit(None, status_message(LicenceStatus(LicenceKind.UNREACHABLE)))
            except LicenceStoreError as ex:
                logger.error("the licence couldn't be saved: %s", ex)
                self._finished.emit(None, save_failed_message(str(ex)))
            except Exception as ex:  # a bug must not leave the window waiting for ever
                logger.exception("licence %s failed unexpectedly", name)
                self._finished.emit(None, save_failed_message(f"{type(ex).__name__}: {ex}"))

        threading.Thread(target=worker, name=f"vitralis-licence-{name}", daemon=True).start()

    def _on_finished(self, status: LicenceStatus | None, error: str | None) -> None:
        self._set_busy(False)
        self.apply(status if status is not None else self._licence.status())
        if error is not None:
            self._report_error(error)

    def _report_error(self, text: str) -> None:
        self.error.emit(text)
        if self._prompt is not None:
            self._prompt.show_error(text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if self._prompt is not None:
            self._prompt.set_busy(busy)
        self.busy_changed.emit(busy)
