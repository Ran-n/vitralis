#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.064124
Revised: 2026/11/14 00:23:15.851129

What a drawing is made of: the tools and the strokes they leave, as they are kept in ``strokes.json`` and in
the snapshots.
"""

import math
from dataclasses import dataclass
from enum import Enum, auto

MAX_WIDTH = 200
"""Wider than any size the toolbar offers; a saved width beyond it is damage, not a choice."""


class Tool(Enum):
    PEN = auto()
    ERASER = auto()
    LINE = auto()
    ARROW = auto()
    RECT = auto()
    ELLIPSE = auto()


TOOL_NAMES = frozenset(tool.name for tool in Tool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass
class Stroke:
    tool: str
    color: str  # "#rrggbb"
    width: int
    points: list[list[float]]  # [x, y] pairs
    filled: bool = False
    created: float = 0.0
    """When it was drawn (``time.time()``), so Undo takes the latest stroke on any screen; 0 in files written
    before this was kept."""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "color": self.color,
            "width": self.width,
            "points": self.points,
            "filled": self.filled,
            "created": self.created,
        }

    @staticmethod
    def from_dict(d: object) -> "Stroke":
        """The stroke a saved entry describes; ``ValueError`` when the entry is damaged, so a bad file can
        never reach the painter."""
        if not isinstance(d, dict):
            raise ValueError("a stroke must be an object")
        tool, color, width, points = d.get("tool"), d.get("color"), d.get("width"), d.get("points")
        if tool not in TOOL_NAMES:
            raise ValueError(f"unknown tool {tool!r}")
        if not isinstance(color, str):
            raise ValueError(f"the colour must be text, not {color!r}")
        if not isinstance(width, int) or isinstance(width, bool) or not 1 <= width <= MAX_WIDTH:
            raise ValueError(f"the width must be a whole number from 1 to {MAX_WIDTH}, not {width!r}")
        if not isinstance(points, list) or not points:
            raise ValueError("a stroke needs at least one point")
        for point in points:
            if not (isinstance(point, list) and len(point) == 2 and all(_is_number(part) for part in point)):
                raise ValueError(f"a point must be two numbers, not {point!r}")
        created = d.get("created", 0.0)
        return Stroke(
            tool=tool,
            color=color,
            width=width,
            points=[[float(x), float(y)] for x, y in points],
            filled=bool(d.get("filled", False)),
            created=float(created) if _is_number(created) else 0.0,
        )
