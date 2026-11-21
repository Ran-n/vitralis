#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:54.314614
Revised: 2026/11/21 18:28:54.314614

The download's proof, against a real server on localhost: a good download is proven, streamed and verified; a
malformed ``.b3``, a stranger's signature, a genuine signature for other bytes or another version, minisign's
legacy mode, the older hex format and a missing ``.minisig`` are all refused with not one request for the exe; a
right trusted comment over a first signature for other bytes, and an exe that doesn't match its checksum, are
refused once the exe has arrived, and the exe deleted; plain HTTP off this machine is never sent.
"""

import threading

import pytest
from blake3 import blake3

from tests.updates.download.support import ASSET, EXE, PUBLIC, Progress, legacy, run, signed
from tests.updates.fakes import OTHER_SECRET
from tests.updates.server import Route
from vitralis.updates.download import TEMP_PREFIX, download_offer, file_hash
from vitralis.updates.rules import ChecksumMismatch, DownloadFailed, NotSigned, Offer, Reason


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
        ("/exe.minisig", Route(signed(EXE, OTHER_SECRET)), NotSigned),
        ("/exe.minisig", Route(signed(b"other bytes")), NotSigned),
        ("/exe.minisig", Route(signed(EXE, version="1.3.0")), NotSigned),
        ("/exe.minisig", Route(signed(EXE, asset="vitralis-1.4.0-windows-x86_64-setup.exe")), NotSigned),
        ("/exe.minisig", Route(b"not a signature"), NotSigned),
        ("/exe.minisig", Route(b"\xff" * 10), NotSigned),
        ("/exe.minisig", Route(legacy(signed(EXE))), NotSigned),
        ("/exe.minisig", Route(b"ab" * 64 + b"\n"), NotSigned),  # the older hex ``.sig`` format
        ("/exe.minisig", Route(b"missing", 404), DownloadFailed),
        ("/exe.b3", Route(b"missing", 404), DownloadFailed),
        ("/exe.minisig", Route(b"a" * 2000), DownloadFailed),
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


def test_a_right_comment_over_another_file_s_signature_is_refused_once_the_exe_arrives(http, server, tmp_path):
    """The trusted comment and its signature hold, but the first signature is over other bytes: only the bytes
    that arrived can tell, so the exe is fetched, refused and deleted."""
    server.routes["/exe.minisig"] = Route(signed(EXE, signed_bytes=b"other bytes"))
    with pytest.raises(NotSigned):
        run(http, server, tmp_path)
    assert "/exe" in server.requests and list(tmp_path.iterdir()) == []


def test_a_download_that_doesnt_match_its_checksum_is_deleted(http, server, tmp_path):
    server.routes["/exe"] = Route(EXE[:-1] + b"!")
    with pytest.raises(ChecksumMismatch):
        run(http, server, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_plain_http_off_this_machine_is_refused_unsent(http, tmp_path):
    from tests.updates.fakes import release

    far = Offer(
        release("1.4.0"), ASSET, "http://example.com/exe", "http://example.com/b3", "http://example.com/minisig"
    )
    with pytest.raises(DownloadFailed) as raised:
        download_offer(http, far, tmp_path, Progress(), threading.Event(), (PUBLIC,))
    assert raised.value.failure.reason is Reason.NOT_HTTPS
