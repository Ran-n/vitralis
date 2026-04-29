#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.995834
Revised: 2026/04/29 13:04:58.715678
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap

_ICONS_DIR: Path | None = None
_FLAGS_DIR: Path | None = None


def init_icons_dir() -> None:
    global _ICONS_DIR, _FLAGS_DIR
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    _ICONS_DIR = base / "media" / "icons"
    _FLAGS_DIR = _ICONS_DIR / "flags"


def svg_icon(name: str, size: int = 20) -> QIcon:
    path = _ICONS_DIR / f"{name}.svg"
    px = QPixmap(str(path))
    if not px.isNull():
        px = px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    icon = QIcon()
    icon.addPixmap(px, QIcon.Mode.Normal)
    # disabled pixmap: same image at 30% opacity to match disabled text alpha
    disabled_px = QPixmap(px.size())
    disabled_px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(disabled_px)
    painter.setOpacity(0.45)
    painter.drawPixmap(0, 0, px)
    painter.end()
    icon.addPixmap(disabled_px, QIcon.Mode.Disabled)
    return icon


def flag_icon(code: str, width: int = 20, height: int = 14) -> QIcon:
    path = _FLAGS_DIR / f"flag_{code}.svg"
    px = QPixmap(str(path))
    if not px.isNull():
        px = px.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    icon = QIcon()
    icon.addPixmap(px)
    return icon


def media_base() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
