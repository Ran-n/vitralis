#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:06.319135
Revised: 2026/11/14 00:23:20.818259

The GitHub release feed (through respx): a real-shaped answer gives the version, page and asset URLs; every
failure (HTTP status, rate limit, malformed JSON, a bad tag, no connection) becomes a ``ReleaseFeedError``
with a readable reason, logged at WARNING with the URL.
"""

import logging

import httpx
import pytest
import respx

from vitralis.updates.github import RELEASES_URL, GitHubReleases, ReleaseFeedError
from vitralis.updates.rules import FeedFailure, Version
from vitralis.version import USER_AGENT

DOWNLOAD = "https://github.com/Ran-n/vitralis/releases/download/v1.4.0"


def answer(tag: str = "v1.4.0", assets: list[str] | None = None) -> dict:
    names = ["vitralis-1.4.0.exe", "vitralis-1.4.0.exe.b3", "vitralis-1.4.0.tar.gz"] if assets is None else assets
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/Ran-n/vitralis/releases/tag/{tag}",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": n, "browser_download_url": f"{DOWNLOAD}/{n}"} for n in names],
    }


def latest():
    with httpx.Client() as http:
        return GitHubReleases(http).latest()


@respx.mock
def test_a_real_shaped_answer_gives_the_version_page_and_assets():
    route = respx.get(RELEASES_URL).mock(return_value=httpx.Response(200, json=answer()))
    release = latest()
    assert release.version == Version(1, 4, 0)
    assert release.page_url == "https://github.com/Ran-n/vitralis/releases/tag/v1.4.0"
    assert release.exe_url == f"{DOWNLOAD}/vitralis-1.4.0.exe"
    assert release.checksum_url == f"{DOWNLOAD}/vitralis-1.4.0.exe.b3"
    sent = route.calls.last.request
    assert sent.headers["User-Agent"] == USER_AGENT
    assert sent.headers["Accept"] == "application/vnd.github+json"


@respx.mock
def test_a_release_without_the_exe_has_no_exe_url():
    respx.get(RELEASES_URL).mock(return_value=httpx.Response(200, json=answer(assets=["vitralis-1.4.0.tar.gz"])))
    release = latest()
    assert release.exe_url is None and release.checksum_url is None and not release.installable


@respx.mock
def test_an_asset_off_https_is_ignored():
    body = answer()
    body["assets"][0]["browser_download_url"] = "http://evil.example/vitralis-1.4.0.exe"
    respx.get(RELEASES_URL).mock(return_value=httpx.Response(200, json=body))
    assert latest().exe_url is None


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(404), "HTTP 404"),
        (httpx.Response(500), "HTTP 500"),
        (httpx.Response(403), "rate limit"),
        (httpx.Response(429), "rate limit"),
        (httpx.Response(200, text="not json"), "unexpected answer"),
        (httpx.Response(200, json=[]), "unexpected answer"),
        (httpx.Response(200, json={"html_url": "https://x"}), "tag_name"),
        (httpx.Response(200, json=answer(tag="v1.2")), "not a version"),
        (httpx.Response(200, json={**answer(), "html_url": "javascript:alert(1)"}), "unexpected release page"),
    ],
)
@respx.mock
def test_every_failure_is_a_feed_error_with_a_reason(response, reason, caplog):
    respx.get(RELEASES_URL).mock(return_value=response)
    with caplog.at_level(logging.WARNING, "vitralis.updates.github"), pytest.raises(ReleaseFeedError) as raised:
        latest()
    assert reason in str(raised.value)
    assert any(r.levelno == logging.WARNING and RELEASES_URL in r.getMessage() for r in caplog.records)


@respx.mock
def test_no_connection_is_a_feed_error():
    respx.get(RELEASES_URL).mock(side_effect=httpx.ConnectError("no route"))
    with pytest.raises(ReleaseFeedError, match="ConnectError") as raised:
        latest()
    assert raised.value.kind is FeedFailure.OFFLINE


@respx.mock
def test_a_timeout_is_a_feed_error():
    respx.get(RELEASES_URL).mock(side_effect=httpx.ReadTimeout(""))
    with pytest.raises(ReleaseFeedError, match="ReadTimeout") as raised:
        latest()
    assert raised.value.kind is FeedFailure.OFFLINE


@pytest.mark.parametrize(
    ("answer_or_error", "kind"),
    [
        (httpx.Response(403), FeedFailure.RATE_LIMITED),
        (httpx.Response(429), FeedFailure.RATE_LIMITED),
        (httpx.Response(500), FeedFailure.OTHER),
        (httpx.Response(200, text="not json"), FeedFailure.OTHER),
        (httpx.TooManyRedirects("loop"), FeedFailure.OTHER),
    ],
)
@respx.mock
def test_each_failure_says_what_kind_it_is(answer_or_error, kind):
    """The kind picks the sentence the user reads: only the unexpected show their raw reason."""
    if isinstance(answer_or_error, Exception):
        respx.get(RELEASES_URL).mock(side_effect=answer_or_error)
    else:
        respx.get(RELEASES_URL).mock(return_value=answer_or_error)
    with pytest.raises(ReleaseFeedError) as raised:
        latest()
    assert raised.value.kind is kind


def test_a_feed_error_is_unexpected_unless_said_otherwise():
    assert ReleaseFeedError("HTTP 500").kind is FeedFailure.OTHER


def test_a_feed_off_https_is_refused():
    with httpx.Client() as http, pytest.raises(ValueError):
        GitHubReleases(http, "http://example.com/releases/latest")


@respx.mock
def test_a_local_feed_is_allowed_for_tests():
    respx.get("http://127.0.0.1:8765/latest").mock(return_value=httpx.Response(200, json=answer("v99.0.0")))
    with httpx.Client() as http:
        assert GitHubReleases(http, "http://127.0.0.1:8765/latest").latest().version == Version(99, 0, 0)
