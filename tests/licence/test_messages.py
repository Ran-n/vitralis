#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.621999
Revised: 2026/11/11 11:06:54.885414

What Vitralis says about its licence: a sentence for every outcome, filled in and translated into every UI
language, and the dates the settings show.
"""

import datetime as dt
import re

import pytest

from vitralis.licence.messages import (
    _MESSAGES,
    CONTACT,
    EXPIRED_ON,
    PRIVACY,
    SAVE_FAILED,
    format_date,
    offline_running_low,
    save_failed_message,
    status_message,
)
from vitralis.licence.rules import LicenceKind, LicenceStatus
from vitralis.translations import _TRANSLATIONS, set_language

LANGUAGES = list(_TRANSLATIONS)
UI_STRINGS = [
    "Activate",
    "Activating…",
    "Check again",
    "Checking…",
    "Check now",
    "Status",
    "Valid until",
    "Works offline until",
    "Test license",
    "Licensed",
    "Permanent",
    "License",
    "Quit",
]
NOW = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def english():
    yield
    set_language("English")


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("kind", list(LicenceKind))
def test_every_outcome_has_a_filled_in_sentence_in_every_language(language, kind):
    set_language(language)
    status = LicenceStatus(kind, retry_after=dt.timedelta(seconds=90))
    text = status_message(status)
    assert text and not re.search(r"[{}]", text)
    if kind in (
        LicenceKind.NEEDS_ACTIVATION,
        LicenceKind.ALREADY_ACTIVATED_ELSEWHERE,
        LicenceKind.REVOKED,
        LicenceKind.EXPIRED,
    ):
        assert CONTACT in text


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "English"])
def test_every_licence_string_is_translated(language):
    table = _TRANSLATIONS[language]
    for key in [*_MESSAGES.values(), EXPIRED_ON, SAVE_FAILED, PRIVACY, *UI_STRINGS]:
        assert table.get(key), f"{language} lacks {key!r}"
        assert set(re.findall(r"\{\w+\}", table[key])) == set(re.findall(r"\{\w+\}", key)), key


def test_every_language_has_the_same_keys():
    keys = {language: set(table) for language, table in _TRANSLATIONS.items() if language != "English"}
    first = next(iter(keys.values()))
    assert all(found == first for found in keys.values()), {k: first ^ v for k, v in keys.items() if v != first}


def test_an_expired_licence_says_when_it_ended():
    ended = dt.datetime(2026, 9, 1, 12, tzinfo=dt.UTC)
    text = status_message(LicenceStatus(LicenceKind.EXPIRED, licence_expires_at=ended))
    assert text == f"This license expired on {format_date(ended)}. Contact {CONTACT} to extend it."


def test_an_expired_licence_without_a_date_still_says_so():
    assert status_message(LicenceStatus(LicenceKind.EXPIRED)).startswith("This license has expired.")


def test_rate_limited_says_how_many_seconds():
    text = status_message(LicenceStatus(LicenceKind.RATE_LIMITED, retry_after=dt.timedelta(seconds=90)))
    assert text == "Too many attempts. Wait 90 seconds and try again."


def test_a_save_failure_names_the_reason():
    assert save_failed_message("disk full") == "Vitralis couldn't save its license: disk full"


def test_dates_are_local_calendar_dates():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", format_date(NOW))


@pytest.mark.parametrize(
    ("left", "low"),
    [(dt.timedelta(days=30), False), (dt.timedelta(days=5), False), (dt.timedelta(days=4, hours=23), True)],
)
def test_offline_runs_low_under_five_days(left, low):
    status = LicenceStatus(LicenceKind.LICENSED, offline_until=NOW + left)
    assert offline_running_low(status, NOW) is low


def test_no_offline_date_is_never_low():
    assert not offline_running_low(LicenceStatus(LicenceKind.NEEDS_CHECK), NOW)
