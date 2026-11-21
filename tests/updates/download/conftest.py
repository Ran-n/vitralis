#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:53.506191
Revised: 2026/11/21 18:28:53.506191

The download tests' release server, serving a signed exe, and an HTTP client that refuses what the app refuses.
"""

import pytest

from tests.updates.download.support import EXE, b3_line, signed
from tests.updates.server import ReleaseServer, Route
from vitralis.net import secure_client


@pytest.fixture
def server():
    running = ReleaseServer()
    running.routes = {
        "/exe": Route(EXE),
        "/exe.b3": Route(b3_line(EXE)),
        "/exe.minisig": Route(signed(EXE)),
    }
    yield running
    running.close()


@pytest.fixture
def http():
    with secure_client() as client:
        yield client
