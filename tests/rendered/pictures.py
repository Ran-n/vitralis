#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 16:56:37.809690
Revised: 2026/11/15 14:27:04.282364

The rendered tests' reviewed pictures: a capture is compared with the PNG checked in under ``baselines/``, and
what differs is written to ``failures/`` (ignored by git) as the capture and a picture of where it differs.

A baseline is made, or replaced after a deliberate change of look, by running the tests with
``VITRALIS_UPDATE_BASELINES=1`` and looking at every PNG it wrote before committing it.
"""

import os
from pathlib import Path

from PyQt6.QtGui import QImage, qAlpha, qBlue, qGreen, qRed, qRgb

HERE = Path(__file__).parent
BASELINES = HERE / "baselines"
FAILURES = HERE / "failures"
UPDATE_FLAG = "VITRALIS_UPDATE_BASELINES"
CHANNEL_TOLERANCE = 24
"""How far a channel may be off before the pixel counts as different: text is smoothed a little differently
from one graphics driver to the next."""
DIFFERENT_ALLOWED = 64
"""How many pixels may differ: the toolbar's small focus dot (which follows whether the test copy really has
the keyboard, and the tests never take it) and a few text edges, never a changed word, a missing button or a
moved row. Two full runs on unchanged code differ in no pixel at all; a share of the picture (0.4 % until
2026-11-15) let a changed sentence of 779 pixels through on the tall Settings window."""


def differing(seen: QImage, wanted: QImage) -> tuple[int, QImage]:
    """How many pixels differ, and a picture with those in red."""
    marks = QImage(seen.size(), QImage.Format.Format_RGB32)
    marks.fill(qRgb(255, 255, 255))
    count = 0
    red = qRgb(255, 0, 0)
    for y in range(seen.height()):
        for x in range(seen.width()):
            a, b = seen.pixel(x, y), wanted.pixel(x, y)
            parts = ((qRed(a), qRed(b)), (qGreen(a), qGreen(b)), (qBlue(a), qBlue(b)), (qAlpha(a), qAlpha(b)))
            if any(abs(one - other) > CHANNEL_TOLERANCE for one, other in parts):
                count += 1
                marks.setPixel(x, y, red)
    return count, marks


def check(seen: QImage, name: str) -> None:
    """Fail unless ``seen`` is the reviewed picture ``name``."""
    path = BASELINES / f"{name}.png"
    if os.environ.get(UPDATE_FLAG):
        BASELINES.mkdir(exist_ok=True)
        if not seen.save(str(path)):
            raise OSError(f"couldn't write {path}")
        return
    if not path.exists():
        raise AssertionError(f"no baseline {path.name}: run with {UPDATE_FLAG}=1 and review what it writes")
    wanted = QImage(str(path)).convertToFormat(seen.format())
    problem = ""
    marks = None
    if wanted.size() != seen.size():
        problem = f"is {seen.width()}x{seen.height()}, the baseline {wanted.width()}x{wanted.height()}"
    else:
        count, marks = differing(seen, wanted)
        if count > DIFFERENT_ALLOWED:
            problem = f"differs from the baseline in {count} pixels"
    if problem:
        FAILURES.mkdir(exist_ok=True)
        seen.save(str(FAILURES / f"{name}.png"))
        if marks is not None:
            marks.save(str(FAILURES / f"{name}.diff.png"))
        raise AssertionError(f"{name} {problem}; see {FAILURES}")
