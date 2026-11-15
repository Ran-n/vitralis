#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:48.374452
Revised: 2026/11/15 14:24:48.374452

One check: every source is asked at the same time, each on its own thread, so a slow one costs only its own
time and one forge can't hide a release. The newest version any of them reports is the one considered; on a
tie the earlier source's files are used. A source that fails (network, any status but 200, an answer that
can't be read, a crash) is ignored while another answers; only when all fail has the check failed, with each
one's reason in order.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vitralis.updates.http import RequestFailed
from vitralis.updates.rules import Failure, Reason, Release, SourceFailure, newest
from vitralis.updates.sources import ReleaseSource

logger = logging.getLogger("vitralis.updates.check")

CHECK_SECONDS = 30.0
"""The longest a whole check may take; a source that hasn't answered by then has timed out."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    release: Release | None
    """The newest release any source reported; ``None`` when every source failed."""
    failures: tuple[SourceFailure, ...] = ()
    """Each failed source's reason, in the sources' order."""


def ask_all(
    sources: Sequence[ReleaseSource], seconds: float = CHECK_SECONDS, now: Callable[[], float] = time.monotonic
) -> CheckResult:
    answers: list[Release | Failure | None] = [None] * len(sources)

    def ask(index: int, source: ReleaseSource) -> None:
        try:
            answers[index] = source.latest()
        except RequestFailed as ex:
            answers[index] = ex.failure
        except Exception:  # a bug in one source must not stop the other from answering
            logger.exception("%s's release check crashed", source.name)
            answers[index] = Failure(Reason.UNREADABLE)

    threads = [
        threading.Thread(target=ask, args=(index, source), name=f"vitralis-update-{source.name.lower()}", daemon=True)
        for index, source in enumerate(sources)
    ]
    deadline = now() + seconds
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(max(0.0, deadline - now()))
    releases: list[Release] = []
    failures: list[SourceFailure] = []
    for source, thread, answer in zip(sources, threads, answers, strict=True):
        if isinstance(answer, Release):
            releases.append(answer)
        elif thread.is_alive() or answer is None:
            logger.warning("%s didn't answer within %.0f s", source.name, seconds)
            failures.append(SourceFailure(source.name, Failure(Reason.TIMED_OUT)))
        else:
            failures.append(SourceFailure(source.name, answer))
    return CheckResult(newest(releases), tuple(failures))
