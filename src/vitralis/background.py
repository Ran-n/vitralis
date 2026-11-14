#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 11:44:52.807135
Revised: 2026/11/14 11:44:54.000078

Disk work for a window, off the UI thread: ``BackgroundTasks.run`` does the work on a thread of its own and
hands its result (or the error it raised) back on the UI thread, so a slow or sleeping disk never freezes a
window.
"""

import logging
import threading
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("vitralis.background")


class BackgroundTasks(QObject):
    busy_changed = pyqtSignal(bool)
    """Work started while nothing was running, or the last work ended."""
    _finished = pyqtSignal(object, object, object)  # then, result, error

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = 0
        self._finished.connect(self._deliver)

    @property
    def busy(self) -> bool:
        return self._running > 0

    def run(self, name: str, work: Callable[[], object], then: Callable[[object, Exception | None], None]) -> None:
        """Do ``work()`` off the UI thread, then call ``then(result, error)`` on it: ``error`` is what ``work``
        raised (and ``result`` is ``None``), or ``None``. The thread isn't a daemon: work that was started is
        finished even while the app quits."""
        self._running += 1
        if self._running == 1:
            self.busy_changed.emit(True)

        def worker() -> None:
            try:
                result, error = work(), None
            except Exception as ex:  # handed to ``then``, which says it; nothing is swallowed here
                result, error = None, ex
            try:
                self._finished.emit(then, result, error)
            except RuntimeError:  # the window was deleted meanwhile: nobody is left to tell
                logger.info("%s ended after its window was gone", name)

        threading.Thread(target=worker, name=f"vitralis-{name}").start()

    def _deliver(self, then: Callable[[object, Exception | None], None], result: object, error: object) -> None:
        try:
            then(result, error)
        finally:
            self._running -= 1
            if self._running == 0:
                self.busy_changed.emit(False)
