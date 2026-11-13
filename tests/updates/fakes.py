#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:04.824444
Revised: 2026/11/13 09:11:05.222156

Stand-ins for the updater's tests: a release feed that answers what it is told, in-memory update settings, a
fixed clock, and release factories.
"""

import datetime as dt
import threading

from vitralis.updates.github import ReleaseFeedError
from vitralis.updates.rules import Release, checksum_name, exe_name, parse_version

NOON = dt.datetime(2026, 11, 13, 12, 34, tzinfo=dt.UTC)


def release(text: str, exe: bool = True) -> Release:
    v = parse_version(text)
    base = f"https://github.com/Ran-n/vitralis/releases/download/v{v}"
    return Release(
        v,
        f"https://github.com/Ran-n/vitralis/releases/tag/v{v}",
        f"{base}/{exe_name(v)}" if exe else None,
        f"{base}/{checksum_name(v)}" if exe else None,
    )


class FakeFeed:
    """Answers with ``answer`` (a ``Release`` or an exception to raise); ``gate`` holds the answer back."""

    def __init__(self, answer: Release | Exception | None = None) -> None:
        self.answer = answer if answer is not None else release("v1.4.0")
        self.calls = 0
        self.gate = threading.Event()
        self.gate.set()

    def latest(self) -> Release:
        self.calls += 1
        self.gate.wait(5)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class MemorySettings:
    def __init__(self, check: bool = True, skipped: str = "") -> None:
        self.check = check
        self.skipped = skipped

    def update_check(self) -> bool:
        return self.check

    def set_update_check(self, enabled: bool) -> None:
        self.check = enabled

    def skipped_version(self) -> str:
        return self.skipped

    def set_skipped_version(self, version: str) -> None:
        self.skipped = version


OFFLINE = ReleaseFeedError("ConnectError: no route")
