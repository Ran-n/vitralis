#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:05.981441
Revised: 2026/11/15 14:27:08.020736

The updater's rules with no I/O: versions as semantic versioning orders them, the pre-release rule, what a
check comes to, the newest of several answers, and the checksum format.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.updates.fakes import TARGET, release
from vitralis.updates.rules import (
    CheckKind,
    Version,
    decide,
    is_offered_version,
    newest,
    parse_b3,
    parse_version,
    parse_version_or_none,
)
from vitralis.updates.target import asset_name

ASSET = asset_name("1.4.0", TARGET)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.4.0", Version(1, 4, 0)),
        ("v1.4.0", Version(1, 4, 0)),
        ("1.4.0-rc.1", Version(1, 4, 0, ("rc", "1"))),
        ("v2.0.0-beta+build.7", Version(2, 0, 0, ("beta",))),
        ("10.20.30", Version(10, 20, 30)),
    ],
)
def test_versions_read(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("text", ["1.2", "1.2.3.4000", "01.2.3", "1.2.3-", "1.2.3-01", "?", "", "v", "1.2.3 ", "x" * 70])
def test_what_isnt_a_version_is_refused(text):
    with pytest.raises(ValueError):
        parse_version(text)
    assert parse_version_or_none(text) is None


def test_a_version_that_isnt_text_is_none():
    assert parse_version_or_none(None) is None
    assert parse_version_or_none(140) is None


def test_versions_print_as_written():
    assert str(parse_version("v1.4.0-rc.1")) == "1.4.0-rc.1"
    assert str(Version(1, 4, 0)) == "1.4.0"


@pytest.mark.parametrize(
    "order",
    [
        ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11"],
        ["1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "2.0.0"],
        ["1.9.0", "1.10.0", "1.11.0"],
    ],
)
def test_versions_order_as_semver_says(order):
    versions = [parse_version(text) for text in order]
    assert sorted(reversed(versions)) == versions
    assert all(a < b and b > a and a != b for a, b in zip(versions, versions[1:], strict=False))


def test_a_version_never_compares_with_something_else():
    assert Version(1, 0, 0).__lt__("1.0.0") is NotImplemented
    assert Version(1, 0, 0) != "1.0.0"


def test_a_pre_release_is_offered_only_to_a_pre_release():
    assert is_offered_version(parse_version("1.3.0"), parse_version("1.4.0"))
    assert not is_offered_version(parse_version("1.3.0"), parse_version("1.4.0-rc.1"))
    assert is_offered_version(parse_version("1.4.0-rc.1"), parse_version("1.4.0-rc.2"))
    assert is_offered_version(parse_version("1.4.0-rc.1"), parse_version("1.4.0"))
    assert not is_offered_version(parse_version("1.4.0"), parse_version("1.4.0"))
    assert not is_offered_version(parse_version("1.4.0"), parse_version("1.3.9"))


versions = st.builds(
    Version,
    st.integers(0, 5),
    st.integers(0, 5),
    st.integers(0, 5),
    st.lists(st.sampled_from(["rc", "1", "2", "beta"]), max_size=2).map(tuple),
)


@pytest.mark.property
@given(versions, versions)
def test_offered_means_newer_and_a_pre_release_only_to_a_pre_release(current, candidate):
    offered = is_offered_version(current, candidate)
    assert offered == (candidate > current and (not candidate.is_prerelease or current.is_prerelease))
    assert parse_version(str(candidate)) == candidate


def test_a_newer_release_with_all_three_files_is_available():
    kind, offer = decide(parse_version("1.3.0"), release("1.4.0"), "", ASSET)
    assert kind is CheckKind.AVAILABLE
    assert offer.asset == ASSET and offer.asset_url.endswith(ASSET)
    assert offer.checksum_url.endswith(ASSET + ".b3") and offer.signature_url.endswith(ASSET + ".sig")


@pytest.mark.parametrize("current", ["1.4.0", "1.5.0"])
def test_the_same_or_an_older_release_is_up_to_date(current):
    assert decide(parse_version(current), release("1.4.0"), "", ASSET) == (CheckKind.UP_TO_DATE, None)


@pytest.mark.parametrize("missing", ["exe", "b3", "sig"])
def test_a_release_missing_one_of_its_files_has_no_build_and_is_never_offered(missing):
    """A release nobody signed is never offered."""
    assert decide(parse_version("1.3.0"), release("1.4.0", missing=missing), "", ASSET) == (CheckKind.NO_BUILD, None)


def test_another_targets_files_dont_count():
    assert decide(parse_version("1.3.0"), release("1.4.0"), "", "vitralis-1.4.0-linux-x86_64")[0] is CheckKind.NO_BUILD


@pytest.mark.parametrize(
    ("skipped", "kind"),
    [
        ("1.4.0", CheckKind.SKIPPED),
        ("1.5.0", CheckKind.SKIPPED),
        ("1.3.5", CheckKind.AVAILABLE),
        ("not one", CheckKind.AVAILABLE),
    ],
)
def test_a_skipped_version_or_an_older_one_is_skipped_until_a_newer_one(skipped, kind):
    assert decide(parse_version("1.3.0"), release("1.4.0"), skipped, ASSET)[0] is kind


def test_an_unknown_running_version_hears_of_any_release():
    assert decide(None, release("0.0.1"), "", asset_name("0.0.1", TARGET))[0] is CheckKind.AVAILABLE


def test_the_newest_answer_wins_and_a_tie_goes_to_the_first_source():
    github, gitlab = release("1.4.0", source="GitHub"), release("1.4.0", source="GitLab")
    assert newest([github, gitlab]).source == "GitHub"
    assert newest([release("1.3.0"), gitlab]).source == "GitLab"
    assert newest([]) is None


@pytest.mark.parametrize("text", ["A" * 64, "a" * 64 + "  vitralis.exe\n", "0" * 64 + "\n"])
def test_a_b3sum_line_gives_its_hash_lower_case(text):
    assert parse_b3(text) == text[:64].lower()


@pytest.mark.parametrize("text", ["", "a" * 63, "g" * 64, "a" * 65, "  vitralis.exe"])
def test_what_isnt_a_b3sum_line_is_refused(text):
    with pytest.raises(ValueError):
        parse_b3(text)
