#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:51.217424
Revised: 2026/11/21 18:29:11.986948

GitHub's and GitLab's answers, from checked-in golden copies of what each forge sends: version, page and files
are read; bad tags, missing fields, files off HTTPS, oversize answers and error statuses are refused with a
short reason; requests carry nothing but the URL, ``Accept`` and ``User-Agent``.
"""

import json
from pathlib import Path

import httpx
import pytest

from tests.updates.server import ReleaseServer, Route
from vitralis.net import secure_client
from vitralis.updates.http import RELEASE_CAP, RequestFailed
from vitralis.updates.rules import Reason, parse_version
from vitralis.updates.sources import GITHUB_URL, GITLAB_URL, GitHubReleases, GitLabReleases, default_sources

GOLDEN = Path(__file__).parent / "golden"


def golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.fixture
def server():
    running = ReleaseServer()
    yield running
    running.close()


@pytest.fixture
def http():
    with secure_client() as client:
        yield client


def serve(server: ReleaseServer, body, status: int = 200) -> str:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    server.routes["/latest"] = Route(raw, status)
    return server.url("/latest")


def test_githubs_answer_is_read(server, http):
    url = serve(server, golden("github_latest.json"))
    release = GitHubReleases(http, url, allow_http=True).latest()
    assert release.version == parse_version("1.4.0") and release.source == "GitHub"
    assert release.page_url == "https://github.com/Ran-n/vitralis/releases/tag/v1.4.0"
    name = "vitralis-1.4.0-windows-x86_64-portable.exe"
    assert release.assets[name] == f"https://github.com/Ran-n/vitralis/releases/download/v1.4.0/{name}"
    assert {name + ".b3", name + ".minisig", "vitralis-1.4.0-windows-x86_64-setup.exe"} <= set(release.assets)


def test_gitlabs_answer_is_read_preferring_the_direct_url(server, http):
    url = serve(server, golden("gitlab_latest.json"))
    release = GitLabReleases(http, url, allow_http=True).latest()
    assert release.version == parse_version("1.4.0") and release.source == "GitLab"
    assert release.page_url == "https://gitlab.com/Ran-n/vitralis/-/releases/v1.4.0"
    assert release.assets["vitralis-1.4.0-windows-x86_64-portable.exe"].endswith(
        "/downloads/vitralis-1.4.0-windows-x86_64-portable.exe"
    )
    assert (
        release.assets["vitralis-1.4.0-windows-x86_64-portable.exe.b3"] == "https://gitlab.com/files/exe.b3"
    )  # no direct URL


def test_requests_carry_nothing_identifying(server, http):
    GitHubReleases(http, serve(server, golden("github_latest.json")), allow_http=True).latest()
    sent = {name.lower(): value for name, value in server.seen_headers[-1].items()}
    assert sent["accept"] == "application/vnd.github+json"
    assert sent["user-agent"].startswith("Vitralis/")
    assert set(sent) <= {"host", "accept", "accept-encoding", "connection", "user-agent"}
    GitLabReleases(http, serve(server, golden("gitlab_latest.json")), allow_http=True).latest()
    assert server.seen_headers[-1]["Accept"] == "application/json"


@pytest.mark.parametrize(
    ("change", "source"),
    [
        (lambda body: body.pop("tag_name"), GitHubReleases),
        (lambda body: body.update(tag_name="latest"), GitHubReleases),
        (lambda body: body.pop("html_url"), GitHubReleases),
        (lambda body: body.update(assets="none"), GitHubReleases),
        (lambda body: body["assets"][0].pop("browser_download_url"), GitHubReleases),
        (lambda body: body.pop("_links"), GitLabReleases),
        (lambda body: body["assets"].update(links={}), GitLabReleases),
        (lambda body: body["assets"]["links"][1].pop("url"), GitLabReleases),
        (lambda body: body.update(tag_name=7), GitLabReleases),
    ],
)
def test_an_answer_missing_what_it_needs_cant_be_read(server, http, change, source):
    body = golden("github_latest.json" if source is GitHubReleases else "gitlab_latest.json")
    change(body)
    with pytest.raises(RequestFailed) as raised:
        source(http, serve(server, body), allow_http=True).latest()
    assert raised.value.failure.reason is Reason.UNREADABLE


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'"text"', b"[" * 100_000])
def test_an_answer_that_isnt_a_release_cant_be_read(server, http, raw):
    with pytest.raises(RequestFailed) as raised:
        GitHubReleases(http, serve(server, raw), allow_http=True).latest()
    assert raised.value.failure.reason is Reason.UNREADABLE


def test_a_file_off_https_is_left_out_and_a_page_off_https_cant_be_read(http, caplog):
    """The forge's own answer is HTTPS; what it points at must be too (the test server can't be, so the
    reading after the request is checked on its own)."""
    body = golden("github_latest.json")
    body["assets"][0]["browser_download_url"] = "http://evil.example/vitralis.exe"
    source = GitHubReleases(http, GITHUB_URL)
    found = source._secure(source.parse(body))
    assert body["assets"][0]["name"] not in found.assets and len(found.assets) == len(body["assets"]) - 1
    assert "isn't on HTTPS" in caplog.text
    body["html_url"] = "http://github.com/Ran-n/vitralis/releases/tag/v1.4.0"
    with pytest.raises(ValueError):
        source._secure(source.parse(body))


@pytest.mark.parametrize(("status", "reason"), [(404, Reason.ANSWERED), (429, Reason.ANSWERED), (503, Reason.ANSWERED)])
def test_an_error_status_is_said_with_its_number(server, http, status, reason):
    with pytest.raises(RequestFailed) as raised:
        GitLabReleases(http, serve(server, b"{}", status), allow_http=True).latest()
    assert raised.value.failure.reason is reason and raised.value.failure.status == status
    assert str(raised.value) == f"the server answered {status}"


def test_an_answer_over_a_mebibyte_is_refused_unread(server, http):
    with pytest.raises(RequestFailed) as raised:
        GitHubReleases(http, serve(server, b" " * (RELEASE_CAP + 1)), allow_http=True).latest()
    assert raised.value.failure.reason is Reason.TOO_LARGE
    server.routes["/latest"] = Route(b" " * (RELEASE_CAP + 10), length=-1)  # no length: counted as it comes
    with pytest.raises(RequestFailed) as raised:
        GitHubReleases(http, server.url("/latest"), allow_http=True).latest()
    assert raised.value.failure.reason is Reason.TOO_LARGE


def test_plain_http_off_this_machine_is_refused_unsent():
    transport = httpx.MockTransport(lambda request: pytest.fail("sent"))
    with httpx.Client(transport=transport) as client, pytest.raises(RequestFailed) as raised:
        GitHubReleases(client, "http://api.github.com/repos/Ran-n/vitralis/releases/latest").latest()
    assert raised.value.failure.reason is Reason.NOT_HTTPS


def test_a_server_that_isnt_there_is_said_plainly(http):
    with pytest.raises(RequestFailed) as raised:
        GitHubReleases(http, "http://127.0.0.1:9/latest", allow_http=True).latest()
    assert raised.value.failure.reason in (Reason.CONNECTION, Reason.TIMED_OUT)


def test_the_real_sources_are_github_then_gitlab_and_a_test_can_point_them_elsewhere(monkeypatch):
    client = httpx.Client()
    sources = default_sources(client)
    assert [source.name for source in sources] == ["GitHub", "GitLab"]
    assert [source._url for source in sources] == [GITHUB_URL, GITLAB_URL]
    assert not any(source._allow_http for source in sources)
    monkeypatch.setenv("VITRALIS_UPDATE_SOURCES", "http://127.0.0.1:1/gh|http://127.0.0.1:1/gl")
    sources = default_sources(client)
    assert [source._url for source in sources] == ["http://127.0.0.1:1/gh", "http://127.0.0.1:1/gl"]
    assert all(source._allow_http for source in sources)
    client.close()
