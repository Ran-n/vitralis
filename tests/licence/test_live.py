#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:59.607530
Revised: 2026/11/14 17:09:09.811095

Contract test against the real licence server (clavren.breren.com): a test licence key activates, the token
verifies with the keys the app ships, and a signed check renews it. The licence is kept in memory, never in the
app's data folder.

Deselected by default (it needs the network); run it with ``uv run pytest -m live``. The refusal of an unknown
key runs as it is; the activation needs a test licence's key in ``VITRALIS_LICENCE_TEST_KEY`` and is skipped
without one. The key is never written in the repository: a test licence works on any number of computers. Each
run with a key adds an activation named ``<computer> (live test)`` to that licence.
"""

import os

import httpx
import pytest

from tests.licence.fakes import MemoryLicenceStore, licence_config
from vitralis.licence.client import Licence, utc_now
from vitralis.licence.crypto import Ed25519Crypto
from vitralis.licence.rules import LicenceKind
from vitralis.licence.server import HttpLicenceServer
from vitralis.net import secure_client

pytestmark = pytest.mark.live

KEY_ENV = "VITRALIS_LICENCE_TEST_KEY"
UNKNOWN_KEY = "BRN-0000-0000-0000-0000"


def real_licence(http: httpx.Client, device_name: str) -> Licence:
    """A licence that talks to the real server over the app's own connection, kept in memory."""
    return Licence(
        licence_config(device_name=device_name), MemoryLicenceStore(), HttpLicenceServer(http), Ed25519Crypto(), utc_now
    )


@pytest.fixture
def http():
    with secure_client() as client:
        yield client


def test_a_test_key_activates_and_checks_against_the_real_server(http):
    key = os.environ.get(KEY_ENV)
    if not key:
        pytest.skip(f"set {KEY_ENV} to a Vitralis test licence's key")
    licence = real_licence(http, f"{os.environ.get('COMPUTERNAME', 'computer')} (live test)")
    activated = licence.activate(key)
    assert activated.licensed and activated.test
    checked = licence.check()
    assert checked.licensed and checked.offline_until >= activated.offline_until


def test_an_unknown_key_is_refused_by_the_real_server(http):
    """Needs no key: the server answers, in the shape the app reads, that there is no such licence."""
    status = real_licence(http, "live test").activate(UNKNOWN_KEY)
    assert status.kind is LicenceKind.INVALID_KEY and not status.licensed
