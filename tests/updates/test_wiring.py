#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:51.776850
Revised: 2026/11/15 14:24:51.776850

How the app's updater is put together, and the short reasons a request fails for: downloads go to the local
cache (or a test's folder), the packaged release exe gets an installer and a build from source doesn't, the
connection is kept open while a request still runs, and every kind of network error reads as one sentence.
"""

import ssl
import sys
import types
from pathlib import Path

import httpx
import pytest

from vitralis import updates
from vitralis.net import InsecureAddress
from vitralis.updates.http import RequestFailed, check_url, failure_of
from vitralis.updates.rules import Failure, Reason


def test_downloads_go_to_the_local_cache_and_a_test_may_move_them(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert updates.download_dir() == tmp_path / "Vitralis" / "updates"
    monkeypatch.setenv("VITRALIS_UPDATE_DIR", str(tmp_path / "mine"))
    assert updates.download_dir() == tmp_path / "mine"
    assert updates.legacy_download_dir(Path("D:/data")) == Path("D:/data/updates")


def test_a_copy_run_from_source_checks_but_never_installs(qapp, monkeypatch):
    monkeypatch.setenv("VITRALIS_RELEASE_TARGET", "windows-x86_64")
    parts = updates.build_updates(MemorySettingsStandIn())
    try:
        assert not parts.checker.is_source_build and not parts.checker.status.can_install
        assert parts.checker._installer is None
    finally:
        parts.checker.stop()
        parts.close()


def test_a_build_from_source_asks_nobody(qapp):
    parts = updates.build_updates(MemorySettingsStandIn())
    try:
        assert parts.checker.is_source_build
    finally:
        parts.close()


def test_the_packaged_release_exe_gets_an_installer_that_downloads_into_the_cache(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setitem(sys.modules, "vitralis._release", types.SimpleNamespace(TARGET="windows-x86_64"))
    updates.release_target.cache_clear()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    seen = []
    monkeypatch.setattr(updates, "download_offer", lambda *args: seen.append(args) or tmp_path / "x.exe")
    parts = updates.build_updates(MemorySettingsStandIn())
    try:
        installer = parts.checker._installer
        assert installer is not None and installer.exe == Path(sys.executable)
        assert installer.download("offer", "progress", "cancel") == tmp_path / "x.exe"
        http, offer, folder, progress, cancel, keys, allow_http = seen[0]
        assert folder == tmp_path / "Vitralis" / "updates" and allow_http is False
        assert keys == updates.release_keys()
    finally:
        parts.checker.stop()
        parts.close()


def test_the_connection_is_kept_while_a_request_still_runs(caplog):
    closed = []

    class Http:
        def close(self):
            closed.append(True)

    class Busy:
        working = True

    updates.UpdateParts(Busy(), Http()).close()
    assert closed == [] and "still under way" in caplog.text
    Busy.working = False
    updates.UpdateParts(Busy(), Http()).close()
    assert closed == [True]


class MemorySettingsStandIn:
    def update_check(self):
        return True

    def set_update_check(self, enabled):
        pass

    def skipped_version(self):
        return ""

    def set_skipped_version(self, version):
        pass

    def last_check(self):
        return None

    def set_last_check(self, when):
        pass


def connect_error(text: str, cause: Exception | None = None) -> httpx.ConnectError:
    error = httpx.ConnectError(text)
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx.ReadTimeout("slow"), Reason.TIMED_OUT),
        (httpx.ConnectTimeout("slow"), Reason.TIMED_OUT),
        (connect_error("[Errno 11001] getaddrinfo failed"), Reason.NOT_FOUND),
        (connect_error("[Errno -2] Name or service not known"), Reason.NOT_FOUND),
        (connect_error("handshake", ssl.SSLError("bad")), Reason.TLS),
        (connect_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"), Reason.TLS),
        (connect_error("[WinError 10061] refused"), Reason.CONNECTION),
        (httpx.RemoteProtocolError("peer closed"), Reason.CONNECTION),
        (OSError("reset"), Reason.CONNECTION),
        (InsecureAddress("http://elsewhere/"), Reason.NOT_HTTPS),
        (RequestFailed(Failure(Reason.TOO_LARGE)), Reason.TOO_LARGE),
        (ValueError("odd"), Reason.UNREADABLE),
    ],
)
def test_every_network_error_reads_as_one_short_reason(error, reason):
    assert failure_of(error).reason is reason


def test_plain_http_is_only_for_a_test_that_allowed_it():
    assert check_url("https://github.com/x") == "https://github.com/x"
    assert check_url("http://example.com/x", allow_http=True) == "http://example.com/x"
    with pytest.raises(RequestFailed):
        check_url("http://example.com/x")
    with pytest.raises(RequestFailed):
        check_url("ftp://example.com/x", allow_http=True)
