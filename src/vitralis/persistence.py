#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.127720
Revised: 2026/04/29 09:40:37.312177
"""

import contextlib
import json
import os
import re
from pathlib import Path

from PyQt6.QtCore import QRect

from vitralis.models import Stroke

DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "Vitralis"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STROKES_FILE = DATA_DIR / "strokes.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_NAME = re.compile(r"[^\w\- ]+")


def _snapshot_path(name: str) -> Path:
    safe = _SAFE_NAME.sub("_", name).strip()
    return SNAPSHOTS_DIR / f"{safe}.json"


def list_snapshots() -> list[str]:
    """Return snapshot names sorted alphabetically."""
    names = []
    for f in SNAPSHOTS_DIR.iterdir():
        if f.suffix == ".json":
            names.append(f.stem)
    return sorted(names)


def save_snapshot(name: str, screens: dict[str, list[Stroke]]) -> None:
    """Save a named snapshot of all screens' strokes."""
    with contextlib.suppress(Exception):
        data = {key: [s.to_dict() for s in strokes] for key, strokes in screens.items()}
        _snapshot_path(name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_snapshot(name: str) -> dict[str, list[Stroke]]:
    """Load a named snapshot; returns dict of screen_key → strokes."""
    path = _snapshot_path(name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {key: [Stroke.from_dict(s) for s in strokes] for key, strokes in data.items()}
    except Exception:
        return {}


def delete_snapshot(name: str) -> None:
    """Delete a named snapshot file."""
    with contextlib.suppress(Exception):
        _snapshot_path(name).unlink(missing_ok=True)


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
