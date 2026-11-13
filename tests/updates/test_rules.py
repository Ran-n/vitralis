#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:05.584374
Revised: 2026/11/13 12:59:12.055120

The updater's pure rules: versions parse and order numerically, which release is offered (newer, not skipped),
release file names, and the b3sum format.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vitralis.net import is_secure_url
from vitralis.updates.rules import (
    Release,
    Version,
    checksum_name,
    exe_name,
    exe_version,
    is_newer,
    parse_b3,
    parse_version,
    parse_version_or_none,
    update_to_offer,
)

HASH = "ab" * 32


def release(text: str, exe: bool = True) -> Release:
    v = parse_version(text)
    page = f"https://github.com/Ran-n/vitralis/releases/tag/v{v}"
    exe_url = f"https://x/{exe_name(v)}" if exe else None
    return Release(v, page, exe_url, f"https://x/{checksum_name(v)}" if exe else None)


@pytest.mark.parametrize("text", ["v1.2.3", "1.2.3"])
def test_versions_parse_with_or_without_the_v(text):
    assert parse_version(text) == Version(1, 2, 3)


@pytest.mark.parametrize("text", ["1.2", "v1.2.3-rc1", "?", "", "1.2.3.999", " 1.2.3", "a.b.c"])
def test_anything_else_is_refused(text):
    with pytest.raises(ValueError):
        parse_version(text)
    assert parse_version_or_none(text) is None


def test_versions_compare_numerically_not_as_text():
    assert parse_version("1.10.0") > parse_version("1.9.0")
    assert str(parse_version("v1.10.0")) == "1.10.0"


@pytest.mark.property
@given(st.tuples(st.integers(0, 10**6), st.integers(0, 10**6), st.integers(0, 10**6)), st.booleans())
def test_a_version_round_trips_through_its_text(parts, with_v):
    version = Version(*parts)
    assert parse_version(("v" if with_v else "") + str(version)) == version


@pytest.mark.property
@given(st.tuples(*[st.integers(0, 999)] * 3), st.tuples(*[st.integers(0, 999)] * 3))
def test_versions_order_like_their_number_tuples(a, b):
    assert (Version(*a) < Version(*b)) == (a < b)
    assert (Version(*a) == Version(*b)) == (a == b)


def test_a_newer_release_is_offered():
    assert update_to_offer(Version(1, 3, 0), release("v1.4.0"), "") == release("v1.4.0")


@pytest.mark.parametrize("latest", ["v1.3.0", "v1.2.9"])
def test_the_same_or_an_older_release_is_not_offered(latest):
    assert update_to_offer(Version(1, 3, 0), release(latest), "") is None


def test_the_skipped_release_is_not_offered():
    assert update_to_offer(Version(1, 3, 0), release("v1.4.0"), "1.4.0") is None


def test_a_release_newer_than_the_skipped_one_is_offered():
    assert update_to_offer(Version(1, 3, 0), release("v1.5.0"), "1.4.0") is not None


def test_an_unknown_running_version_is_always_offered():
    assert update_to_offer(None, release("v0.0.1"), "") is not None
    assert is_newer(None, release("v0.0.1"))


@pytest.mark.parametrize("skipped", ["?", "garbage", "1.4"])
def test_a_malformed_skipped_value_is_ignored(skipped):
    assert update_to_offer(Version(1, 3, 0), release("v1.4.0"), skipped) is not None


def test_a_release_is_installable_only_with_exe_and_checksum():
    assert release("1.4.0").installable
    assert not release("1.4.0", exe=False).installable
    assert not Release(Version(1, 4, 0), "https://p", "https://x/e", None).installable


def test_file_names_match_what_build_makes():
    assert exe_name(Version(1, 4, 0)) == "vitralis-1.4.0.exe"
    assert checksum_name(Version(1, 4, 0)) == "vitralis-1.4.0.exe.b3"
    assert exe_version("vitralis-1.4.0.exe") == Version(1, 4, 0)
    assert exe_version("vitralis.exe") is None
    assert exe_version("vitralis-1.4.0.exe.part") is None


@pytest.mark.parametrize(
    "text", [f"{HASH}  vitralis-1.4.0.exe\n", f"{HASH}\n", HASH, f"{HASH.upper()}  x", f"{HASH} *vitralis.exe"]
)
def test_b3sum_lines_parse(text):
    """Regression guard: the releases' .b3 files are b3sum output, "<hash>  <name>"."""
    assert parse_b3(text) == HASH


@pytest.mark.parametrize("text", ["", "abc", "zz" * 32, HASH + "ff"])
def test_anything_but_a_b3sum_line_is_refused(text):
    with pytest.raises(ValueError):
        parse_b3(text)


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://github.com/x", True),
        ("http://127.0.0.1:8000/x", True),
        ("http://localhost/x", True),
        ("http://example.com/x", False),
        ("ftp://github.com/x", False),
        ("file:///C:/x", False),
    ],
)
def test_only_https_or_this_computer_is_allowed(url, ok):
    assert is_secure_url(url) is ok
