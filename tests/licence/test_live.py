#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:59.607530
Revised: 2026/11/11 11:06:54.798581

Contract test against the real licence server (clavren.breren.com): a test licence key activates, the token
verifies with the keys the app ships, and a signed check renews it. The licence is kept in memory, never in the
app's data folder.

Deselected by default (it needs the network); run it with ``uv run pytest -m live`` and a test licence's key
in ``VITRALIS_LICENCE_TEST_KEY``. The key is never written in the repository: a test licence works on any
number of computers. Each run adds an activation named ``<computer> (live test)`` to that licence.
"""

import os

import httpx
import pytest

from tests.licence.fakes import MemoryLicenceStore, licence_config
from vitralis.licence.client import Licence, utc_now
from vitralis.licence.crypto import Ed25519Crypto
from vitralis.licence.rules import LicenceKind
from vitralis.licence.server import HttpLicenceServer

pytestmark = pytest.mark.live

KEY_ENV = "VITRALIS_LICENCE_TEST_KEY"


@pytest.fixture
def live_licence():
    key = os.environ.get(KEY_ENV)
    if not key:
        pytest.skip(f"set {KEY_ENV} to a Vitralis test licence's key")
    config = licence_config(device_name=f"{os.environ.get('COMPUTERNAME', 'computer')} (live test)")
    with httpx.Client() as http:
        yield Licence(config, MemoryLicenceStore(), HttpLicenceServer(http), Ed25519Crypto(), utc_now), key


def test_a_test_key_activates_and_checks_against_the_real_server(live_licence):
    licence, key = live_licence
    activated = licence.activate(key)
    assert activated.licensed and activated.test
    checked = licence.check()
    assert checked.licensed and checked.offline_until >= activated.offline_until


def test_an_unknown_key_is_refused_by_the_real_server(live_licence):
    licence, _ = live_licence
    assert licence.activate("BRN-0000-0000-0000-0000").kind is LicenceKind.INVALID_KEY
