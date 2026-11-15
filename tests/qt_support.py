#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 22:44:53.436707
Revised: 2026/11/15 22:44:53.436707

Qt for the tests: one offscreen ``QApplication``, the icon folders, a clean-up after each test so no Qt object
is left for a later test to trip over, a way to wait for a worker thread's answer, and workers made slow to
end, for the tests that guard against a worker outliving its result.
"""

import time

import pytest
from PyQt6.QtWidgets import QApplication

from vitralis.icons import init_icons_dir


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture(scope="session")
def icons():
    """The icon folders, which ``main()`` sets up before building any window."""
    init_icons_dir()


@pytest.fixture(autouse=True)
def no_qt_leftovers():
    """After each test, and after its own fixtures' teardown (this one is set up first, so it ends last):
    the windows it let go of are deleted now, and its reference cycles collected now. Left for later, Python
    collected them at a random moment of another test's event processing, deleting a Qt object while Qt was
    using it: an access violation in CI in whichever test came next. Now a fault shows in the test that left
    the object behind."""
    import gc

    from PyQt6.QtCore import QCoreApplication, QEvent

    yield
    if QCoreApplication.instance() is None:
        return
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def wait_until(qapp, condition, timeout: float = 5.0) -> None:
    """Process Qt events until ``condition()`` holds (a worker thread's answer arrives as a queued signal)."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the licence worker")
        qapp.processEvents()
        time.sleep(0.005)


LINGER_SECONDS = 0.2


@pytest.fixture
def lingering_workers(monkeypatch):
    """Every thread started in the test stays alive ``LINGER_SECONDS`` after its work, as a worker that is
    slow to wind down after handing back its last result: what let a test drop the last reference to a Qt
    object while the worker still held one."""
    import threading

    run = threading.Thread.run

    def lingering(self) -> None:
        run(self)
        time.sleep(LINGER_SECONDS)

    monkeypatch.setattr(threading.Thread, "run", lingering)
