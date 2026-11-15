#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:07.444893
Revised: 2026/11/15 14:27:07.131071

The verified download, against a real server on localhost: a good download is proven and verified; a checksum
mismatch, an oversize body (declared or real), Cancel, a stall, a download that takes too long and a truncated
body all leave no file behind; and a malformed ``.b3``, a stranger's signature, a genuine signature for other
bytes or another version, and a missing ``.sig`` are all refused with not one request for the exe.
"""

import threading

import pytest
from blake3 import blake3

from tests.updates.fakes import OTHER_SECRET, PUBLIC, SECRET, TARGET
from tests.updates.server import ReleaseServer, Route
from vitralis.net import secure_client
from vitralis.updates import download as download_module
from vitralis.updates.download import TEMP_PREFIX, download_offer, file_hash
from vitralis.updates.rules import (
    ChecksumMismatch,
    DownloadFailed,
    NotSigned,
    Offer,
    Reason,
    UpdateCancelled,
    parse_version,
)
from vitralis.updates.signature import sign, statement
from vitralis.updates.target import asset_name

VERSION = parse_version("1.4.0")
ASSET = asset_name(VERSION, TARGET)
EXE = b"MZ" + bytes(range(256)) * 1000


def b3_line(data: bytes) -> bytes:
    return f"{blake3(data).hexdigest()}  {ASSET}\n".encode()


def signed(data: bytes, secret: str = SECRET, version: str = "1.4.0", asset: str = ASSET) -> bytes:
    return sign(secret, statement(version, asset, blake3(data).hexdigest())).encode()


@pytest.fixture
def server():
    running = ReleaseServer()
    running.routes = {
        "/exe": Route(EXE),
        "/exe.b3": Route(b3_line(EXE)),
        "/exe.sig": Route(signed(EXE)),
    }
    yield running
    running.close()


@pytest.fixture
def http():
    with secure_client() as client:
        yield client


def offer(server: ReleaseServer) -> Offer:
    from tests.updates.fakes import release

    return Offer(release("1.4.0"), ASSET, server.url("/exe"), server.url("/exe.b3"), server.url("/exe.sig"))


class Progress:
    def __init__(self, then=None):
        self.seen: list[tuple[int, int | None]] = []
        self.then = then

    def __call__(self, received, total):
        self.seen.append((received, total))
        if self.then is not None:
            self.then(received, total)


def run(http, server, folder, progress=None, cancel=None, **kw):
    return download_offer(
        http, offer(server), folder, progress or Progress(), cancel or threading.Event(), (PUBLIC,), True, **kw
    )


def test_a_good_download_is_proven_streamed_and_verified(http, server, tmp_path):
    progress = Progress()
    path = run(http, server, tmp_path, progress)
    assert path.parent == tmp_path and path.name.startswith(TEMP_PREFIX)
    assert path.read_bytes() == EXE and file_hash(path) == blake3(EXE).hexdigest()
    assert progress.seen[-1] == (len(EXE), len(EXE))
    assert list(tmp_path.iterdir()) == [path]
    exe_request = [h for h in server.seen_headers if h.get("Accept") == "application/octet-stream"]
    assert len(exe_request) == 1 and exe_request[0]["User-Agent"].startswith("Vitralis/")


@pytest.mark.parametrize(
    ("route", "change", "error"),
    [
        ("/exe.b3", Route(b"not a checksum"), ChecksumMismatch),
        ("/exe.b3", Route(b"\xff\xfe" + b"a" * 64), ChecksumMismatch),
        ("/exe.sig", Route(signed(EXE, OTHER_SECRET)), NotSigned),
        ("/exe.sig", Route(signed(b"other bytes")), NotSigned),
        ("/exe.sig", Route(signed(EXE, version="1.3.0")), NotSigned),
        ("/exe.sig", Route(signed(EXE, asset="vitralis-1.4.0-windows-x86_64-setup.exe")), NotSigned),
        ("/exe.sig", Route(b"not a signature"), NotSigned),
        ("/exe.sig", Route(b"\xff" * 10), NotSigned),
        ("/exe.sig", Route(b"missing", 404), DownloadFailed),
        ("/exe.b3", Route(b"missing", 404), DownloadFailed),
        ("/exe.sig", Route(b"a" * 2000), DownloadFailed),
    ],
)
def test_a_release_that_doesnt_prove_itself_is_refused_without_asking_for_the_exe(
    http, server, tmp_path, route, change, error
):
    server.routes[route] = change
    with pytest.raises(error):
        run(http, server, tmp_path)
    assert "/exe" not in server.requests
    assert list(tmp_path.iterdir()) == []


def test_a_download_that_doesnt_match_its_checksum_is_deleted(http, server, tmp_path):
    server.routes["/exe"] = Route(EXE[:-1] + b"!")
    with pytest.raises(ChecksumMismatch):
        run(http, server, tmp_path)
    assert list(tmp_path.iterdir()) == []


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


def test_plain_http_off_this_machine_is_refused_unsent(http, tmp_path):
    from tests.updates.fakes import release

    far = Offer(release("1.4.0"), ASSET, "http://example.com/exe", "http://example.com/b3", "http://example.com/sig")
    with pytest.raises(DownloadFailed) as raised:
        download_offer(http, far, tmp_path, Progress(), threading.Event(), (PUBLIC,))
    assert raised.value.failure.reason is Reason.NOT_HTTPS


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
