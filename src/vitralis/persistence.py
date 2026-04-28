#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.127720
Revised: 2026/04/28 15:57:04.127720
"""

import contextlib
import json
import os
from pathlib import Path

from PyQt6.QtCore import QRect

from vitralis.models import Stroke

DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "Vitralis"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STROKES_FILE = DATA_DIR / "strokes.json"


def _screen_key(geo: QRect) -> str:
    return f"{geo.x()},{geo.y()}"


def load_strokes_for(geo: QRect) -> list[Stroke]:
    if not STROKES_FILE.exists():
        return []
    try:
        data = json.loads(STROKES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [Stroke.from_dict(s) for s in data] if geo.x() == 0 and geo.y() == 0 else []
        key = _screen_key(geo)
        return [Stroke.from_dict(s) for s in data.get(key, [])]
    except Exception:
        return []


def save_strokes_for(geo: QRect, strokes: list[Stroke]) -> None:
    with contextlib.suppress(Exception):
        try:
            data = json.loads(STROKES_FILE.read_text(encoding="utf-8")) if STROKES_FILE.exists() else {}
            if isinstance(data, list):
                data = {}
        except Exception:
            data = {}
        data[_screen_key(geo)] = [s.to_dict() for s in strokes]
        STROKES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
