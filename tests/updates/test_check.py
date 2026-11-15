#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:50.621590
Revised: 2026/11/15 14:24:50.621590

One check asks every source at once: the newest answer wins, a tie goes to the first source, one source down
either way doesn't matter, both down gives both reasons in order, a hanging source times out without holding
up the other, and a crash in one is only that source's failure.
"""

import threading
import time

from tests.updates.fakes import release
from vitralis.updates.check import ask_all
from vitralis.updates.http import RequestFailed
from vitralis.updates.rules import Failure, Reason, SourceFailure


class Source:
    def __init__(self, name, answer=None, hang: threading.Event | None = None, delay: float = 0.0):
        self.name = name
        self.answer = answer
        self.hang = hang
        self.delay = delay
        self.thread = ""

    def latest(self):
        self.thread = threading.current_thread().name
        if self.hang is not None:
            self.hang.wait(10)
        time.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


DOWN = RequestFailed(Failure(Reason.ANSWERED, 503))
TIMEOUT = RequestFailed(Failure(Reason.TIMED_OUT))


def test_both_are_asked_and_the_newest_wins():
    github, gitlab = Source("GitHub", release("1.4.0")), Source("GitLab", release("1.5.0", source="GitLab"))
    result = ask_all([github, gitlab])
    assert result.release.version == release("1.5.0").version and result.release.source == "GitLab"
    assert result.failures == ()
    assert github.thread == "vitralis-update-github" and gitlab.thread == "vitralis-update-gitlab"


def test_a_tie_takes_the_first_sources_files():
    result = ask_all([Source("GitHub", release("1.4.0")), Source("GitLab", release("1.4.0", source="GitLab"))])
    assert result.release.source == "GitHub"


def test_one_source_down_either_way_is_ignored():
    for sources in (
        [Source("GitHub", DOWN), Source("GitLab", release("1.4.0", source="GitLab"))],
        [Source("GitHub", release("1.4.0")), Source("GitLab", TIMEOUT)],
    ):
        result = ask_all(sources)
        assert result.release is not None and len(result.failures) == 1


def test_both_down_gives_each_reason_in_order():
    result = ask_all([Source("GitHub", DOWN), Source("GitLab", TIMEOUT)])
    assert result.release is None
    assert result.failures == (
        SourceFailure("GitHub", Failure(Reason.ANSWERED, 503)),
        SourceFailure("GitLab", Failure(Reason.TIMED_OUT)),
    )


def test_both_are_asked_at_the_same_time():
    started = time.monotonic()
    ask_all([Source("GitHub", release("1.4.0"), delay=0.4), Source("GitLab", release("1.4.0"), delay=0.4)])
    assert time.monotonic() - started < 0.75


def test_a_hanging_source_times_out_and_the_other_still_counts():
    hang = threading.Event()
    try:
        started = time.monotonic()
        result = ask_all(
            [Source("GitHub", release("1.4.0"), hang=hang), Source("GitLab", release("1.3.9"))], seconds=0.3
        )
        assert time.monotonic() - started < 2
        assert result.release.version == release("1.3.9").version
        assert result.failures == (SourceFailure("GitHub", Failure(Reason.TIMED_OUT)),)
    finally:
        hang.set()


def test_a_crash_in_one_source_is_only_its_failure(caplog):
    result = ask_all([Source("GitHub", ZeroDivisionError("bug")), Source("GitLab", release("1.4.0"))])
    assert result.release is not None
    assert result.failures == (SourceFailure("GitHub", Failure(Reason.UNREADABLE)),)
    assert "crashed" in caplog.text
