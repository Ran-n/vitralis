#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:07.122997
Revised: 2026/11/13 09:11:07.718339

Downloading a release (respx, real bytes in ``tmp_path``): the verified exe lands with its checksum beside it;
a checksum mismatch, a truncated or failed stream, a bad checksum file and stopping mid-way each raise and leave
no ``.part`` file behind.
"""

import logging
import threading

import httpx
import pytest
import respx
from blake3 import blake3

from vitralis.updates.download import CHUNK_BYTES, download_release, file_hash
from vitralis.updates.rules import ChecksumMismatch, Release, UpdateCancelled, UpdateError, Version

EXE_URL = "https://github.com/Ran-n/vitralis/releases/download/v1.4.0/vitralis-1.4.0.exe"
B3_URL = EXE_URL + ".b3"
BODY = bytes(range(256)) * 1024  # 256 KiB: several chunks
HASH = blake3(BODY).hexdigest()
RELEASE = Release(Version(1, 4, 0), "https://github.com/Ran-n/vitralis/releases/tag/v1.4.0", EXE_URL, B3_URL)


def run(tmp_path, stop: threading.Event | None = None, calls: list | None = None):
    seen = [] if calls is None else calls
    with httpx.Client() as http:
        return download_release(
            http, RELEASE, tmp_path / "updates", lambda r, t: seen.append((r, t)), stop or threading.Event()
        )


def leftovers(tmp_path) -> list[str]:
    folder = tmp_path / "updates"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


@respx.mock
def test_the_verified_exe_lands_with_its_checksum_and_progress_counts_up(tmp_path):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text=f"{HASH}  vitralis-1.4.0.exe\n"))
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=BODY))
    calls = []
    path = run(tmp_path, calls=calls)
    assert path == tmp_path / "updates" / "vitralis-1.4.0.exe"
    assert path.read_bytes() == BODY and file_hash(path) == HASH
    assert (tmp_path / "updates" / "vitralis-1.4.0.exe.b3").read_text(encoding="utf-8").startswith(HASH)
    assert leftovers(tmp_path) == ["vitralis-1.4.0.exe", "vitralis-1.4.0.exe.b3"]
    assert calls[-1] == (len(BODY), len(BODY))
    assert [r for r, _ in calls] == sorted(r for r, _ in calls) and len(calls) >= len(BODY) // CHUNK_BYTES


@respx.mock
def test_without_content_length_the_total_is_unknown(tmp_path):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text=HASH))

    def stream(request):
        return httpx.Response(200, stream=httpx.ByteStream(BODY), headers={"Transfer-Encoding": "chunked"})

    respx.get(EXE_URL).mock(side_effect=stream)
    calls = []
    run(tmp_path, calls=calls)
    assert calls and all(total is None for _, total in calls)


@respx.mock
def test_a_checksum_mismatch_deletes_the_file_and_logs_both_hashes(tmp_path, caplog):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text="00" * 32))
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=BODY))
    with caplog.at_level(logging.WARNING, "vitralis.updates.download"), pytest.raises(ChecksumMismatch):
        run(tmp_path)
    assert leftovers(tmp_path) == []
    assert any(HASH in r.getMessage() and "00" * 32 in r.getMessage() for r in caplog.records)


@respx.mock
def test_one_changed_byte_is_a_mismatch(tmp_path):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text=HASH))
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=b"X" + BODY[1:]))
    with pytest.raises(ChecksumMismatch):
        run(tmp_path)


@respx.mock
def test_a_truncated_stream_raises_with_no_file_left(tmp_path):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text=HASH))
    short = BODY[: len(BODY) // 2]
    respx.get(EXE_URL).mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(short), headers={"Content-Length": str(len(BODY))})
    )
    with pytest.raises(UpdateError, match="stopped at"):
        run(tmp_path)
    assert leftovers(tmp_path) == []


@respx.mock
def test_stopping_mid_stream_leaves_no_part_file(tmp_path):
    respx.get(B3_URL).mock(return_value=httpx.Response(200, text=HASH))
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=BODY))
    stop = threading.Event()
    calls = []

    def progress(received, total):
        calls.append(received)
        stop.set()  # Vitralis quits after the first chunk

    with httpx.Client() as http, pytest.raises(UpdateCancelled):
        download_release(http, RELEASE, tmp_path / "updates", progress, stop)
    assert leftovers(tmp_path) == [] and len(calls) == 1


@pytest.mark.parametrize(
    ("b3", "exe", "match"),
    [
        (httpx.Response(404), None, "checksum"),
        (httpx.Response(200, text="not a hash"), None, "b3sum"),
        (httpx.Response(200, text=HASH), httpx.Response(500), "HTTP 500"),
    ],
)
@respx.mock
def test_server_failures_raise_a_reason(tmp_path, b3, exe, match):
    respx.get(B3_URL).mock(return_value=b3)
    respx.get(EXE_URL).mock(return_value=exe or httpx.Response(200, content=BODY))
    with pytest.raises(UpdateError, match=match):
        run(tmp_path)
    assert leftovers(tmp_path) == []


@respx.mock
def test_no_connection_raises_an_update_error(tmp_path):
    respx.get(B3_URL).mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(UpdateError, match="ConnectError"):
        run(tmp_path)


def test_a_release_without_exe_or_off_https_is_refused(tmp_path):
    with httpx.Client() as http:
        with pytest.raises(UpdateError, match="no exe"):
            download_release(
                http, Release(Version(1, 4, 0), "https://p", None, None), tmp_path, lambda *_: None, threading.Event()
            )
        insecure = Release(Version(1, 4, 0), "https://p", "http://evil.example/x.exe", "http://evil.example/x.b3")
        with pytest.raises(UpdateError, match="not HTTPS"):
            download_release(http, insecure, tmp_path, lambda *_: None, threading.Event())
