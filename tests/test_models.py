#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:22:49.939269
Revised: 2026/11/14 18:00:30.455255

A stroke as it is saved: what it writes it reads back the same (for any stroke), files from before strokes had
a time still load, and a damaged entry is refused with a reason instead of reaching the painter.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vitralis.models import MAX_WIDTH, TOOL_NAMES, Stroke, Tool

coordinates = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
strokes = st.builds(
    Stroke,
    tool=st.sampled_from(sorted(TOOL_NAMES)),
    color=st.from_regex(r"#[0-9a-f]{6}", fullmatch=True),
    width=st.integers(min_value=1, max_value=MAX_WIDTH),
    points=st.lists(st.lists(coordinates, min_size=2, max_size=2), min_size=1, max_size=20),
    created=st.floats(min_value=0, max_value=4e9, allow_nan=False),
)

VALID = {"tool": "PEN", "color": "#ff0000", "width": 3, "points": [[1, 2], [3.5, 4]]}


@pytest.mark.property
@given(strokes)
def test_any_stroke_reads_back_as_it_was_written(stroke):
    assert Stroke.from_dict(stroke.to_dict()) == stroke


def test_the_tool_names_are_the_tools():
    assert {tool.name for tool in Tool} == TOOL_NAMES


def test_an_entry_from_before_strokes_had_a_time_loads_with_time_zero():
    stroke = Stroke.from_dict(VALID)
    assert stroke == Stroke("PEN", "#ff0000", 3, [[1.0, 2.0], [3.5, 4.0]], created=0.0)


def test_the_filled_of_earlier_versions_is_ignored():
    assert Stroke.from_dict({**VALID, "filled": True}) == Stroke.from_dict(VALID)
    assert "filled" not in Stroke.from_dict(VALID).to_dict()


# --- how near a click is to what a stroke draws -------------------------------------------------------------


def shape(tool: str, *points: tuple[float, float]) -> Stroke:
    return Stroke(tool, "#ff0000", 3, [list(point) for point in points])


def test_a_rectangle_is_its_four_sides_not_its_diagonal():
    """Regression guard: a click on a rectangle's edge missed it, and a click in its empty middle deleted it."""
    rectangle = shape("RECT", (0, 0), (400, 300))
    assert rectangle.distance_to(200, 0) == 0 and rectangle.distance_to(400, 150) == 0
    assert rectangle.distance_to(200, 150) == 150  # the middle: as far from the sides as it gets
    assert rectangle.distance_to(-30, -40) == 50


def test_an_ellipse_is_its_curve():
    ellipse = shape("ELLIPSE", (0, 0), (400, 200))
    assert ellipse.distance_to(400, 100) == pytest.approx(0, abs=0.5)  # its right end
    assert ellipse.distance_to(200, 0) == pytest.approx(0, abs=0.5)  # its top
    assert ellipse.distance_to(200, 100) == pytest.approx(100, abs=0.5)  # its centre
    assert ellipse.distance_to(0, 0) > 40  # the corner of its box, where nothing is drawn


@pytest.mark.parametrize("tool", ["LINE", "ARROW"])
def test_a_line_is_the_segment_between_its_ends(tool):
    line = shape(tool, (0, 0), (100, 0))
    assert line.distance_to(50, 7) == 7 and line.distance_to(130, 40) == 50


def test_a_freehand_stroke_is_every_segment_and_a_dot_is_its_point():
    assert shape("PEN", (0, 0), (100, 0), (100, 100)).distance_to(90, 50) == 10
    assert shape("PEN", (5, 5)).distance_to(8, 9) == 5
    assert shape("LINE", (5, 5)).distance_to(8, 9) == 5  # a damaged shape of one point is still measured


@pytest.mark.property
@given(strokes, coordinates, coordinates)
def test_a_stroke_is_never_farther_than_the_points_its_line_goes_through(stroke, x, y):
    """Freehand goes through every saved point; a shape's line through its two ends (a rectangle's two corners)."""
    measured = stroke.distance_to(x, y)
    assert measured >= 0 and math.isfinite(measured)
    on_the_line = stroke.points if stroke.tool in ("PEN", "ERASER") else [stroke.points[0], stroke.points[-1]]
    if stroke.tool != "ELLIPSE":  # an ellipse touches the sides of its box, not its corners
        assert measured <= min(math.hypot(px - x, py - y) for px, py in on_the_line) + 1e-6


def test_a_damaged_time_reads_as_zero():
    assert Stroke.from_dict({**VALID, "created": "yesterday"}).created == 0.0


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ([1, 2], "must be an object"),
        ("PEN", "must be an object"),
        ({**VALID, "tool": "LASER"}, "unknown tool"),
        ({k: v for k, v in VALID.items() if k != "tool"}, "unknown tool"),
        ({**VALID, "color": 255}, "colour"),
        ({**VALID, "width": "3"}, "width"),
        ({**VALID, "width": True}, "width"),
        ({**VALID, "width": 0}, "width"),
        ({**VALID, "width": MAX_WIDTH + 1}, "width"),
        ({**VALID, "points": []}, "at least one point"),
        ({**VALID, "points": "1,2"}, "at least one point"),
        ({**VALID, "points": [[1, 2, 3]]}, "two numbers"),
        ({**VALID, "points": [[1, "2"]]}, "two numbers"),
        ({**VALID, "points": [[1, float("nan")]]}, "two numbers"),
        ({**VALID, "points": [[1, float("inf")]]}, "two numbers"),
        ({**VALID, "points": [[True, 2]]}, "two numbers"),
        ({**VALID, "points": [{"x": 1, "y": 2}]}, "two numbers"),
    ],
)
def test_a_damaged_entry_is_refused_with_a_reason(entry, reason):
    with pytest.raises(ValueError, match=reason):
        Stroke.from_dict(entry)


# --- what mutation testing found unchecked ------------------------------------------------------------------


def test_a_stroke_is_made_at_no_time_unless_told():
    assert shape("LINE", [0, 0]).created == 0.0


def test_a_shape_of_one_point_is_its_own_outline():
    for tool in ("LINE", "ARROW", "RECT", "ELLIPSE"):
        assert shape(tool, [3.0, 4.0]).outline() == [[3.0, 4.0]]


def test_a_shape_is_outlined_between_its_first_and_last_point():
    """A shape keeps the two ends of its drag; a damaged one with more is still measured between its ends."""
    assert shape("LINE", [0, 0], [50, 50], [10, 0]).outline() == [[0, 0], [10, 0]]
    assert shape("PEN", [0, 0], [50, 50], [10, 0]).outline() == [[0, 0], [50, 50], [10, 0]]


def test_a_rectangles_outline_is_its_four_sides_closed():
    assert shape("RECT", [10, 20], [110, 80]).outline() == [[10, 20], [110, 20], [110, 80], [10, 80], [10, 20]]


def test_an_ellipses_outline_goes_once_round_its_box():
    outline = shape("ELLIPSE", [10, 20], [111, 81]).outline()
    assert len(outline) == 65  # 64 sides, closed
    assert outline[0] == pytest.approx([111, 50.5]) == outline[-1]  # starts and ends at its right end
    assert outline[16] == pytest.approx([60.5, 81])  # a quarter of the way: its bottom (y grows downwards)
    assert outline[32] == pytest.approx([10, 50.5])  # half way: its left end
    assert outline[48] == pytest.approx([60.5, 20])  # its top
    for x, y in outline:  # every point is on the ellipse
        assert ((x - 60.5) / 50.5) ** 2 + ((y - 50.5) / 30.5) ** 2 == pytest.approx(1.0)


def test_an_ellipse_dragged_backwards_is_the_same_ellipse():
    forwards, backwards = shape("ELLIPSE", [10, 20], [110, 80]), shape("ELLIPSE", [110, 80], [10, 20])
    flat = [part for point in forwards.outline() for part in point]
    assert [part for point in backwards.outline() for part in point] == pytest.approx(flat)


def test_the_distance_to_a_line_is_measured_to_its_nearest_point():
    line = shape("LINE", [0, 10], [100, 10])
    assert line.distance_to(50, 14) == pytest.approx(4)  # beside its middle
    assert line.distance_to(-3, 14) == pytest.approx(5)  # past its start: to the start itself
    assert line.distance_to(103, 6) == pytest.approx(5)  # past its end
    slanted = shape("LINE", [0, 10], [10, 20])
    assert slanted.distance_to(10, 10) == pytest.approx(math.sqrt(50))
    assert slanted.distance_to(5, 15) == pytest.approx(0)


def test_the_distance_to_a_very_short_line_still_counts_its_length():
    """A line shorter than a pixel is still a line: the click is measured to it, not to its ends only."""
    short = shape("LINE", [0, 0], [0.5, 0])
    assert short.distance_to(0.25, 3) == pytest.approx(3)
    assert shape("LINE", [5, 5], [5, 5]).distance_to(8, 9) == pytest.approx(5)  # no length at all: a dot


def test_the_widest_width_is_the_last_one_read():
    entry = shape("LINE", [0, 0], [1, 1]).to_dict()
    assert MAX_WIDTH == 200
    assert Stroke.from_dict({**entry, "width": 200}).width == 200
    with pytest.raises(ValueError, match="width"):
        Stroke.from_dict({**entry, "width": 201})


@pytest.mark.parametrize("point", [[1.0], [], [1.0, 2.0, 3.0]])
def test_a_point_is_exactly_two_numbers(point):
    entry = shape("LINE", [0, 0], [1, 1]).to_dict()
    with pytest.raises(ValueError, match="two numbers"):
        Stroke.from_dict({**entry, "points": [[0.0, 0.0], point]})
