#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:22:49.939269
Revised: 2026/11/14 00:23:23.316774

A stroke as it is saved: what it writes it reads back the same (for any stroke), files from before strokes had
a time still load, and a damaged entry is refused with a reason instead of reaching the painter.
"""

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
    filled=st.booleans(),
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
    assert stroke == Stroke("PEN", "#ff0000", 3, [[1.0, 2.0], [3.5, 4.0]], filled=False, created=0.0)


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
