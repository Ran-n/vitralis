#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 11:44:52.875213
Revised: 2026/11/14 11:44:54.074260

Disk work off the UI thread (``BackgroundTasks``): the work runs on a thread of its own, its result or its error
comes back on the UI thread, ``busy`` holds from the first work started to the last one ended, one failing
doesn't touch the others, and work that outlives its window is finished and told to nobody.
"""

import logging
import threading

import pytest

from tests.conftest import wait_until
from vitralis.background import BackgroundTasks


@pytest.fixture
def tasks(qapp):
    made = BackgroundTasks()
    made.changes = []
    made.busy_changed.connect(made.changes.append)
    yield made
    wait_until(qapp, lambda: not made.busy)


def test_the_work_runs_off_the_ui_thread_and_its_result_comes_back_on_it(qapp, tasks):
    seen = {}

    def work() -> int:
        seen["work"] = threading.current_thread()
        return 42

    def then(result, error) -> None:
        seen["then"] = threading.current_thread()
        seen["answer"] = (result, error)

    tasks.run("answer", work, then)
    assert tasks.busy and "then" not in seen  # nothing is told before the UI thread's next turn
    wait_until(qapp, lambda: "then" in seen)
    assert seen["answer"] == (42, None)
    assert seen["then"] is threading.main_thread() and seen["work"] is not threading.main_thread()
    assert seen["work"].name == "vitralis-answer" and not seen["work"].daemon
    assert not tasks.busy and tasks.changes == [True, False]


def test_what_the_work_raises_is_handed_over_not_lost(qapp, tasks):
    told = []

    def work() -> None:
        raise PermissionError("read-only")

    tasks.run("refused", work, lambda result, error: told.append((result, error)))
    wait_until(qapp, lambda: bool(told))
    result, error = told[0]
    assert result is None and isinstance(error, PermissionError) and str(error) == "read-only"


def test_busy_holds_until_the_last_work_ends_and_one_failure_leaves_the_others(qapp, tasks):
    release = threading.Event()
    told = []

    def slow() -> str:
        assert release.wait(5)
        return "slow"

    def broken() -> None:
        raise ValueError("no")

    tasks.run("slow", slow, lambda result, error: told.append(result))
    tasks.run("broken", broken, lambda result, error: told.append(type(error).__name__))
    tasks.run("quick", lambda: "quick", lambda result, error: told.append(result))
    wait_until(qapp, lambda: len(told) == 2)
    assert sorted(told) == ["ValueError", "quick"] and tasks.busy and tasks.changes == [True]
    release.set()
    wait_until(qapp, lambda: not tasks.busy)
    assert told[-1] == "slow" and tasks.changes == [True, False]


def test_a_then_that_raises_still_ends_the_busy_state(qapp, tasks, monkeypatch):
    raised = []
    monkeypatch.setattr("sys.excepthook", lambda kind, error, trace: raised.append(error))  # as app.py's hook

    def then(result, error) -> None:
        raise RuntimeError("the window's own bug")

    tasks.run("oops", lambda: 1, then)
    wait_until(qapp, lambda: not tasks.busy)
    assert tasks.changes == [True, False] and [str(error) for error in raised] == ["the window's own bug"]


def test_work_that_outlives_its_window_is_finished_and_told_to_nobody(qapp, caplog):
    """Regression guard: emitting on a deleted window raised in the worker thread."""
    import PyQt6.sip as sip

    tasks = BackgroundTasks()
    release, done, told = threading.Event(), threading.Event(), []

    def work() -> None:
        assert release.wait(5)
        done.set()

    with caplog.at_level(logging.INFO, "vitralis.background"):
        tasks.run("late", work, lambda result, error: told.append(1))
        sip.delete(tasks)  # the window closed for good while the disk was still busy
        release.set()
        assert done.wait(5)
        wait_until(qapp, lambda: any("late" in r.getMessage() for r in caplog.records))
    assert told == []
