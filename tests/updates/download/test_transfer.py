#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:54.890448
Revised: 2026/11/21 18:28:54.890448

The download's transfer, against a real server on localhost: an oversize body (declared or real), Cancel (also
during the hash check), a stall, a download that takes too long, a truncated body and an error status all leave
no file behind, and a folder or disk that refuses the file is said as such, not as a network failure.
"""

import threading

import pytest

from tests.updates.download.support import EXE, Progress, run
from tests.updates.server import Route
from vitralis.updates import download as download_module
from vitralis.updates.download import TEMP_PREFIX
from vitralis.updates.rules import ChecksumMismatch, DownloadFailed, Reason, UpdateCancelled


def test_a_declared_length_over_the_limit_is_refused_before_the_body(http, server, tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "MAX_BYTES", 1000)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path)
    assert raised.value.failure.reason is Reason.TOO_LARGE and list(tmp_path.iterdir()) == []


def test_a_body_over_the_limit_without_a_length_is_cut_off(http, server, tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "MAX_BYTES", 100_000)
    server.routes["/exe"] = Route(EXE, length=-1)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path)
    assert raised.value.failure.reason is Reason.TOO_LARGE and list(tmp_path.iterdir()) == []


def test_a_truncated_body_is_a_failed_connection(http, server, tmp_path):
    server.routes["/exe"] = Route(EXE, length=len(EXE) + 500)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path)
    assert raised.value.failure.reason is Reason.CONNECTION and list(tmp_path.iterdir()) == []


def test_cancel_stops_the_download_and_deletes_it(http, server, tmp_path):
    cancel = threading.Event()
    server.routes["/exe"] = Route(EXE, chunk=4096, pace=0.002)
    with pytest.raises(UpdateCancelled):
        run(http, server, tmp_path, Progress(lambda received, _: received > 20_000 and cancel.set()), cancel)
    assert list(tmp_path.iterdir()) == []


def test_a_cancel_during_the_hash_check_still_stops_the_replace(http, server, tmp_path):
    cancel = threading.Event()
    with pytest.raises(UpdateCancelled):
        run(http, server, tmp_path, Progress(lambda received, total: received == total and cancel.set()), cancel)
    assert list(tmp_path.iterdir()) == []


def test_a_stalled_download_times_out_and_is_deleted(http, server, tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "STALL_SECONDS", 0.5)
    server.routes["/exe"] = Route(EXE, chunk=4096, stall_after=8192)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path)
    assert raised.value.failure.reason is Reason.TIMED_OUT and list(tmp_path.iterdir()) == []


def test_a_download_that_takes_too_long_in_all_is_given_up(http, server, tmp_path, caplog):
    ticks = iter(range(0, 10_000_000, 600))
    server.routes["/exe"] = Route(EXE, chunk=4096)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path, clock=lambda: next(ticks))
    assert raised.value.failure.reason is Reason.TIMED_OUT and list(tmp_path.iterdir()) == []
    assert "took over 30 minutes" in caplog.text


def test_an_error_status_for_the_exe_says_its_number(http, server, tmp_path):
    server.routes["/exe"] = Route(b"gone", 410)
    with pytest.raises(DownloadFailed) as raised:
        run(http, server, tmp_path)
    assert raised.value.failure.status == 410 and list(tmp_path.iterdir()) == []


def test_a_download_folder_that_cant_be_made_is_said(http, server, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(download_module.UpdateError, match="can't be written"):
        run(http, server, blocker / "updates")


def test_a_disk_that_refuses_the_file_is_not_a_network_failure(http, server, tmp_path, monkeypatch):
    real = download_module._stream

    def failing_stream(http_, offer_, file, *rest):
        class Full:
            def write(self, _):
                raise OSError(28, "No space left on device")

        return real(http_, offer_, Full(), *rest)

    monkeypatch.setattr(download_module, "_stream", failing_stream)
    with pytest.raises(download_module.UpdateError, match="couldn't be saved") as raised:
        run(http, server, tmp_path)
    assert not isinstance(raised.value, DownloadFailed) and list(tmp_path.iterdir()) == []


def test_a_file_that_cant_be_deleted_after_a_failure_is_logged(http, server, tmp_path, monkeypatch, caplog):
    server.routes["/exe"] = Route(EXE[:-1] + b"!")
    real = type(tmp_path).unlink

    def refuse(self, *args, **kwargs):
        if self.name.startswith(TEMP_PREFIX):
            raise PermissionError("held by an antivirus")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "unlink", refuse)
    with pytest.raises(ChecksumMismatch):
        run(http, server, tmp_path)
    assert "the next start tries again" in caplog.text
