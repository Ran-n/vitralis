#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.064124
Revised: 2026/11/14 12:31:23.913180

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
FREEHAND = frozenset({Tool.PEN.name, Tool.ERASER.name})
"""Tools that keep every point of the drag; the others keep its two ends."""
ELLIPSE_SIDES = 64
"""How many straight sides stand for an ellipse when measuring how near a click is to it."""


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass
class Stroke:
    tool: str
    color: str  # "#rrggbb"
    width: int
    points: list[list[float]]  # [x, y] pairs
    created: float = 0.0
    """When it was drawn (``time.time()``), so Undo takes the latest stroke on any screen; 0 in files written
    before this was kept."""

    def to_dict(self) -> dict:
        """The saved form. It shares ``points`` with the stroke, and is written to disk from another thread: a
        finished stroke's points are replaced (``stroke.points = [...]``), never changed in place."""
        return {
            "tool": self.tool,
            "color": self.color,
            "width": self.width,
            "points": self.points,
            "created": self.created,
        }

    def outline(self) -> list[list[float]]:
        """The line the stroke draws, as the points of a polyline: what a click must be near to mean this stroke
        (a rectangle's four sides and an ellipse's curve, not the diagonal between their two saved corners)."""
        if self.tool in FREEHAND or len(self.points) < 2:
            return self.points
        (x0, y0), (x1, y1) = self.points[0], self.points[-1]
        if self.tool == Tool.RECT.name:
            return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
        if self.tool == Tool.ELLIPSE.name:
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
            turn = 2 * math.pi / ELLIPSE_SIDES
            return [[cx + rx * math.cos(i * turn), cy + ry * math.sin(i * turn)] for i in range(ELLIPSE_SIDES + 1)]
        return [[x0, y0], [x1, y1]]

    def distance_to(self, x: float, y: float) -> float:
        """How far ``(x, y)`` is from the line the stroke draws."""
        outline = self.outline()
        nearest = min(math.hypot(px - x, py - y) for px, py in outline)
        for (ax, ay), (bx, by) in zip(outline, outline[1:], strict=False):
            dx, dy = bx - ax, by - ay
            length_squared = dx * dx + dy * dy
            if length_squared > 0:
                along = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_squared))
                nearest = min(nearest, math.hypot(ax + along * dx - x, ay + along * dy - y))
        return nearest

    @staticmethod
    def from_dict(d: object) -> "Stroke":
        """The stroke a saved entry describes; ``ValueError`` when the entry is damaged, so a bad file can
        never reach the painter. Entries of earlier versions carry a ``filled`` no tool ever set: it is ignored."""
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
            created=float(created) if _is_number(created) else 0.0,
        )
