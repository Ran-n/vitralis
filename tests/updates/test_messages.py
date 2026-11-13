#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:10.341228
Revised: 2026/11/14 00:23:20.897378

What Vitralis says about updates: every sentence is translated into every UI language with the same
placeholders, and each state's sentence is filled in.
"""

import re

import pytest

from tests.updates.fakes import NOON, release
from vitralis.translations import _TRANSLATIONS, set_language
from vitralis.updates.checker import FailureKind, InstallKind, InstallState, UpdateStatus
from vitralis.updates.messages import (
    ALL,
    error_line,
    install_line,
    out_message,
    result_line,
    settings_tooltip,
    updated_message,
)
from vitralis.updates.rules import FeedFailure

LANGUAGES = list(_TRANSLATIONS)


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "English"])
def test_every_update_sentence_is_translated_with_the_same_placeholders(language):
    table = _TRANSLATIONS[language]
    for key in ALL:
        assert table.get(key), f"{language} lacks {key!r}"
        assert set(re.findall(r"\{\w+\}", table[key])) == set(re.findall(r"\{\w+\}", key)), (language, key)


OUT = UpdateStatus("1.3.0", latest=release("v1.4.0"), offered=release("v1.4.0"), newer=True, checked_at=NOON)
STATES = [
    UpdateStatus("1.3.0", latest=release("v1.3.0"), checked_at=NOON),
    OUT,
    UpdateStatus("1.3.0", latest=release("v1.4.0"), newer=True),
    UpdateStatus("1.3.0", error="HTTP 500", error_kind=FeedFailure.OTHER),
    UpdateStatus("1.3.0", error="ConnectError: [Errno 11001] getaddrinfo failed", error_kind=FeedFailure.OFFLINE),
    UpdateStatus("1.3.0", error="GitHub's rate limit was reached (HTTP 403)", error_kind=FeedFailure.RATE_LIMITED),
]
INSTALLS = [
    InstallState(InstallKind.DOWNLOADING, "1.4.0", 5, 10),
    InstallState(InstallKind.DOWNLOADING, "1.4.0", 5 << 20),
    InstallState(InstallKind.FAILED, "1.4.0", failure=FailureKind.DAMAGED),
    InstallState(InstallKind.FAILED, "1.4.0", failure=FailureKind.NOT_WRITABLE, detail="C:\\Program Files"),
    InstallState(InstallKind.FAILED, "1.4.0", failure=FailureKind.OTHER, detail="denied"),
    InstallState(InstallKind.FAILED, "1.4.0", failure=FailureKind.OFFLINE),
]


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_state_has_a_filled_in_sentence_in_every_language(language):
    set_language(language)
    texts = [result_line(s) or error_line(s) for s in STATES]
    texts += [install_line(s) for s in INSTALLS]
    texts += [settings_tooltip(OUT), out_message(OUT), updated_message("1.4.0")]
    assert all(text and not re.search(r"[{}]", text) for text in texts), texts


def test_the_english_sentences():
    assert result_line(STATES[0]) == f"Vitralis 1.3.0 is up to date · checked {NOON:%H:%M}"
    assert result_line(OUT) == "Vitralis 1.4.0 is out"
    assert result_line(STATES[2]) == "Vitralis 1.4.0 is out (skipped)"
    assert result_line(UpdateStatus("1.3.0")) == ""
    assert error_line(STATES[3]) == "Couldn't check for updates: HTTP 500"
    assert install_line(INSTALLS[0]) == "Downloading 1.4.0… 50%"
    assert install_line(InstallState()) == ""
    assert settings_tooltip(OUT) == "Settings · Vitralis 1.4.0 is out"
    assert settings_tooltip(None) == settings_tooltip(STATES[0]) == "Settings"
    assert updated_message("1.4.0") == "Updated to 1.4.0"


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_connection_failure_never_shows_its_technical_reason(language):
    """No exception name or error code reaches the screen for what the user can fix: the log keeps those."""
    set_language(language)
    for status in STATES[4:]:
        line = error_line(status)
        assert line and status.error not in line and "Error" not in line and "HTTP" not in line
    assert "ConnectError" not in install_line(INSTALLS[5])


def test_the_english_failure_sentences():
    assert error_line(STATES[4]) == (
        "Couldn't check for updates: GitHub can't be reached. Check your internet connection and try again."
    )
    assert error_line(STATES[5]) == (
        "Couldn't check for updates: GitHub is taking no more requests from this network for now. Try again in an hour."
    )
    assert install_line(INSTALLS[5]) == "The download failed. Check your internet connection and try again."
    assert error_line(UpdateStatus("1.3.0", error="odd")) == "Couldn't check for updates: odd"
