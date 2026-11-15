#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:04.824444
Revised: 2026/11/15 14:27:06.562703

Stand-ins for the updater's tests: a check that answers what it is told, in-memory update settings, a fixed
clock, release factories, and a test signing key.
"""

import datetime as dt
import threading

from vitralis.updates.check import CheckResult
from vitralis.updates.rules import Failure, Reason, Release, SourceFailure, parse_version
from vitralis.updates.signature import public_key
from vitralis.updates.target import asset_name

NOON = dt.datetime(2026, 11, 13, 12, 34, tzinfo=dt.UTC)
TARGET = "windows-x86_64"
SECRET = bytes(range(32)).hex()
"""A test signing key: never one of the release keys."""
PUBLIC = public_key(SECRET)
OTHER_SECRET = bytes(range(32, 64)).hex()
"""Someone else's key."""


def release(text: str, files: bool = True, source: str = "GitHub", missing: str = "") -> Release:
    """A release as a forge describes it; ``missing`` names one of ``"exe"``, ``"b3"``, ``"sig"`` to leave out."""
    v = parse_version(text)
    base = f"https://github.com/Ran-n/vitralis/releases/download/v{v}"
    exe = asset_name(v, TARGET)
    assets = {}
    if files:
        for kind, name in (("exe", exe), ("b3", exe + ".b3"), ("sig", exe + ".sig")):
            if kind != missing:
                assets[name] = f"{base}/{name}"
    return Release(v, f"https://github.com/Ran-n/vitralis/releases/tag/v{v}", assets, source)


FAILED = CheckResult(
    None,
    (SourceFailure("GitHub", Failure(Reason.ANSWERED, 429)), SourceFailure("GitLab", Failure(Reason.TIMED_OUT))),
)
"""Both sources down."""


class FakeFeed:
    """A check that answers ``answer`` (a ``Release``, a ``CheckResult`` or an exception to raise); ``gate``
    holds the answer back."""

    def __init__(self, answer: Release | CheckResult | Exception | None = None) -> None:
        self.answer = answer if answer is not None else release("v1.4.0")
        self.calls = 0
        self.threads: list[str] = []
        self.gate = threading.Event()
        self.gate.set()

    def __call__(self) -> CheckResult:
        self.calls += 1
        self.threads.append(threading.current_thread().name)
        self.gate.wait(5)
        if isinstance(self.answer, Exception):
            raise self.answer
        if isinstance(self.answer, CheckResult):
            return self.answer
        return CheckResult(self.answer)


class MemorySettings:
    def __init__(self, check: bool = True, skipped: str = "", last: float | None = None) -> None:
        self.check = check
        self.skipped = skipped
        self.last = last

    def update_check(self) -> bool:
        return self.check

    def set_update_check(self, enabled: bool) -> None:
        self.check = enabled

    def skipped_version(self) -> str:
        return self.skipped

    def set_skipped_version(self, version: str) -> None:
        self.skipped = version

    def last_check(self) -> float | None:
        return self.last

    def set_last_check(self, when: float) -> None:
        self.last = when
