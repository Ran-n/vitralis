#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.995834
Revised: 2026/04/28 16:22:10.913820
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

_ICONS_DIR: Path | None = None


def init_icons_dir() -> None:
    global _ICONS_DIR
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    _ICONS_DIR = base / "media" / "icons"


def svg_icon(name: str, size: int = 20) -> QIcon:
    path = _ICONS_DIR / f"{name}.svg"
    px = QPixmap(str(path))
    if not px.isNull():
        px = px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    icon = QIcon()
    icon.addPixmap(px)
    return icon


def media_base() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
