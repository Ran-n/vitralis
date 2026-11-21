#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:54.082543
Revised: 2026/11/21 18:28:54.082543

What the download tests share: the exe a release server on localhost serves, its ``.b3`` line and ``.minisig``,
the offer pointing at them, a progress recorder, and a download run against the test key.
"""

import base64
import threading

from blake3 import blake3

from tests.updates.fakes import PUBLIC, SECRET, TARGET, minisig, release
from tests.updates.server import ReleaseServer
from vitralis.updates.download import download_offer
from vitralis.updates.rules import Offer, parse_version
from vitralis.updates.target import asset_name

VERSION = parse_version("1.4.0")
ASSET = asset_name(VERSION, TARGET)
EXE = b"MZ" + bytes(range(256)) * 1000


def b3_line(data: bytes) -> bytes:
    return f"{blake3(data).hexdigest()}  {ASSET}\n".encode()


def signed(data: bytes, secret: str = SECRET, version: str = "1.4.0", asset: str = ASSET, **more) -> bytes:
    return minisig(data, secret, version, asset, **more).encode()


def legacy(text: bytes) -> bytes:
    """``text`` with its first signature's tag changed to minisign's legacy (non-prehashed) mode."""
    lines = text.decode().splitlines()
    raw = base64.b64decode(lines[1])
    lines[1] = base64.b64encode(b"Ed" + raw[2:]).decode()
    return ("\n".join(lines) + "\n").encode()


def offer(server: ReleaseServer) -> Offer:
    return Offer(release("1.4.0"), ASSET, server.url("/exe"), server.url("/exe.b3"), server.url("/exe.minisig"))


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
