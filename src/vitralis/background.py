#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 11:44:52.807135
Revised: 2026/11/15 17:01:58.400030

Disk work for a window, off the UI thread: ``BackgroundTasks.run`` does the work on a thread of its own and
hands its result (or the error it raised) back on the UI thread, so a slow or sleeping disk never freezes a
window. ``finish`` is how every worker's last result waits for the worker to end, on the UI thread.
"""

import logging
import threading
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("vitralis.background")

FINISH_SECONDS = 5.0
"""How long the UI thread waits for a worker that has handed back its last result to end."""


def finish(worker: threading.Thread | None, what: str) -> None:
    """Wait, on the UI thread, for ``worker`` to end, called by the slot that gets the worker's last result. A
    worker's own references go when it ends; if one were the last reference to the Qt object it reports to,
    that object (and its timers) would be destroyed on the worker's thread, which crashes Qt. Waiting here,
    where the slot still holds the object, means the worker never lets go last. The worker's last result is
    its last statement, so this returns at once; a worker that is still alive afterwards is logged."""
    if worker is None or worker is threading.current_thread():
        return
    worker.join(FINISH_SECONDS)
    if worker.is_alive():
        logger.warning("%s still runs %.0f s after its last result", what, FINISH_SECONDS)


class BackgroundTasks(QObject):
    busy_changed = pyqtSignal(bool)
    """Work started while nothing was running, or the last work ended."""
    _finished = pyqtSignal(object, object, object, object)  # then, result, error, the worker

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
                self._finished.emit(then, result, error, threading.current_thread())
            except RuntimeError:  # the window was deleted meanwhile: nobody is left to tell
                logger.info("%s ended after its window was gone", name)

        threading.Thread(target=worker, name=f"vitralis-{name}").start()

    def _deliver(
        self, then: Callable[[object, Exception | None], None], result: object, error: object, worker: object
    ) -> None:
        finish(worker, "a background task")
        try:
            then(result, error)
        finally:
            self._running -= 1
            if self._running == 0:
                self.busy_changed.emit(False)
