#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:10.341228
Revised: 2026/11/15 14:27:07.745922

What Vitralis says about updates: every sentence is translated into every UI language with the same
placeholders, each state's sentence is filled in, and the English is the family's exact wording.
"""

import re

import pytest

from tests.updates.fakes import FAILED, NOON, TARGET, release
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
    version_line,
)
from vitralis.updates.rules import FOLDER_NOT_WRITABLE, CheckKind, Failure, Offer, Reason

LANGUAGES = list(_TRANSLATIONS)
PAGE = "https://github.com/Ran-n/vitralis/releases/tag/v1.4.0"
LATEST = release("v1.4.0")
OFFER = Offer(LATEST, "a", "b", "c", "d")


def status(kind, **kw) -> UpdateStatus:
    return UpdateStatus("1.3.0", TARGET, kind, latest=kw.pop("latest", LATEST), checked_at=NOON, **kw)


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "English"])
def test_every_update_sentence_is_translated_with_the_same_placeholders(language):
    table = _TRANSLATIONS[language]
    for key in ALL:
        assert table.get(key), f"{language} lacks {key!r}"
        assert set(re.findall(r"\{\w+\}", table[key])) == set(re.findall(r"\{\w+\}", key)), (language, key)


def test_the_check_lines_are_the_familys_wording():
    assert result_line(status(CheckKind.UP_TO_DATE)) == "Vitralis is up to date (checked 12:34)."
    assert result_line(status(CheckKind.AVAILABLE, offer=OFFER)) == "Vitralis 1.4.0 is available (checked 12:34)."
    assert result_line(status(CheckKind.NO_BUILD)) == "Vitralis 1.4.0 is out, but has no build for this system yet."
    assert result_line(status(CheckKind.SKIPPED)) == (
        "Vitralis 1.4.0 is available; you chose to skip it (checked 12:34)."
    )
    source = UpdateStatus("1.3.0", None, CheckKind.SOURCE_BUILD)
    assert result_line(source) == "This copy was built from source. Update it with git pull and a new build."
    assert result_line(UpdateStatus("1.3.0", TARGET)) == ""
    assert error_line(status(CheckKind.FAILED, failures=FAILED.failures, latest=None)) == (
        "Couldn't check for updates: GitHub: the server answered 429; GitLab: the request timed out."
    )
    assert error_line(status(CheckKind.UP_TO_DATE)) == ""


def test_the_version_line_says_which_build_this_is():
    assert version_line(status(None)) == "Version 1.3.0 · windows-x86_64"
    assert version_line(UpdateStatus("1.3.0", None)) == "Version 1.3.0 · built from source"


@pytest.mark.parametrize(
    ("reason", "text"),
    [
        (Failure(Reason.TIMED_OUT), "the request timed out"),
        (Failure(Reason.NOT_FOUND), "the server couldn't be found"),
        (Failure(Reason.CONNECTION), "the connection failed"),
        (Failure(Reason.TOO_LARGE), "the answer was too large"),
        (Failure(Reason.NOT_HTTPS), "the server didn't use HTTPS"),
        (Failure(Reason.TLS), "the secure connection failed"),
        (Failure(Reason.ANSWERED, 503), "the server answered 503"),
        (Failure(Reason.UNREADABLE), "the answer couldn't be read"),
    ],
)
def test_each_network_reason_is_short_and_carries_no_address(reason, text):
    state = InstallState(InstallKind.FAILED, "1.4.0", failure=FailureKind.NOT_DOWNLOADED, reason=reason, page_url=PAGE)
    assert (
        install_line(state) == f"Vitralis 1.4.0 couldn't be downloaded: {text}. Try again, or download it from {PAGE}"
    )


def test_the_install_lines_are_the_familys_wording():
    def failed(failure, **kw):
        return InstallState(
            InstallKind.FAILED, "1.4.0", failure=failure, page_url=PAGE, path=r"C:\Tools\vitralis.exe", **kw
        )

    assert install_line(failed(FailureKind.DAMAGED)) == (
        "The download of Vitralis 1.4.0 didn't match its checksum, so it wasn't installed."
    )
    assert install_line(failed(FailureKind.NOT_SIGNED)) == (
        "The download of Vitralis 1.4.0 isn't signed with Vitralis's release key, so it wasn't installed."
    )
    assert install_line(failed(FailureKind.NOT_REPLACED, detail="in use")) == (
        r"Vitralis couldn't replace itself at C:\Tools\vitralis.exe: in use. "
        f"Download it from the release page instead: {PAGE}"
    )
    assert "the folder can't be written to" in install_line(
        failed(FailureKind.NOT_REPLACED, detail=FOLDER_NOT_WRITABLE)
    )
    assert install_line(failed(FailureKind.NOT_DOWNLOADED, detail="disk full")) == (
        f"Vitralis 1.4.0 couldn't be downloaded: disk full. Try again, or download it from {PAGE}"
    )
    assert install_line(InstallState(InstallKind.DOWNLOADING, "1.4.0", 42, 100)) == "Downloading Vitralis 1.4.0… 42 %"
    assert (
        install_line(InstallState(InstallKind.DOWNLOADING, "1.4.0", 3_250_586)) == "Downloading Vitralis 1.4.0… 3.1 MiB"
    )
    assert install_line(InstallState(InstallKind.REPLACING, "1.4.0")) == "Installing Vitralis 1.4.0…"
    assert install_line(InstallState()) == ""


def test_the_tooltip_and_the_tray_messages():
    assert settings_tooltip(status(CheckKind.AVAILABLE, offer=OFFER)) == "Settings · Vitralis 1.4.0 is available"
    assert settings_tooltip(status(CheckKind.UP_TO_DATE)) == "Settings"
    assert settings_tooltip(None) == "Settings"
    assert out_message(status(CheckKind.AVAILABLE, offer=OFFER)) == "Vitralis 1.4.0 is available."
    assert updated_message("1.4.0") == "Updated to 1.4.0"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_line_fills_in_every_language(language):
    set_language(language)
    lines = [result_line(status(kind, offer=OFFER)) for kind in CheckKind if kind is not CheckKind.FAILED] + [
        error_line(status(CheckKind.FAILED, failures=FAILED.failures)),
        version_line(status(None)),
        version_line(UpdateStatus("1.3.0", None)),
        out_message(status(CheckKind.AVAILABLE, offer=OFFER)),
        settings_tooltip(status(CheckKind.AVAILABLE, offer=OFFER)),
        updated_message("1.4.0"),
    ]
    for failure in FailureKind:
        state = InstallState(
            InstallKind.FAILED,
            "1.4.0",
            failure=failure,
            reason=Failure(Reason.ANSWERED, 503),
            detail=FOLDER_NOT_WRITABLE,
            page_url=PAGE,
            path="C:\\x",
        )
        lines.append(install_line(state))
    lines += [
        install_line(InstallState(InstallKind.DOWNLOADING, "1.4.0", 1, 2)),
        install_line(InstallState(InstallKind.DOWNLOADING, "1.4.0", 1 << 20)),
        install_line(InstallState(InstallKind.REPLACING, "1.4.0")),
    ]
    for line in lines:
        assert line and "{" not in line, (language, line)
