#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.064124
Revised: 2026/04/28 15:57:04.064124
"""

from dataclasses import dataclass
from enum import Enum, auto


class Tool(Enum):
    PEN = auto()
    ERASER = auto()
    LINE = auto()
    ARROW = auto()
    RECT = auto()
    ELLIPSE = auto()


@dataclass
class Stroke:
    tool: str
    color: str  # "#rrggbb"
    width: int
    points: list  # list of [x, y]
    filled: bool = False

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "color": self.color,
            "width": self.width,
            "points": self.points,
            "filled": self.filled,
        }

    @staticmethod
    def from_dict(d: dict) -> "Stroke":
        return Stroke(
            tool=d["tool"],
            color=d["color"],
            width=d["width"],
            points=d["points"],
            filled=d.get("filled", False),
        )
