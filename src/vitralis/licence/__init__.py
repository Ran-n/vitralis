#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.061466
Revised: 2026/11/14 12:01:47.093177

Vitralis's licence from Clavren (``../clavren``, served at clavren.breren.com): a key activated once on this
computer, checked online once a day, working up to 30 days offline. A Python port of the ``clavren-client``
crate, following Bounty Board's (``../bounty_board``) layout: ``rules`` (no I/O), ``ports``, ``client`` (the
use case), the adapters ``crypto``, ``server`` and ``store``, and the Qt side in ``gate`` and ``window``.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from vitralis.licence.client import Licence, LicenceChecks, LicenceConfig, utc_now
from vitralis.licence.crypto import Ed25519Crypto
from vitralis.licence.server import HttpLicenceServer
from vitralis.licence.store import FileLicenceStore
from vitralis.net import secure_client
from vitralis.version import app_version

logger = logging.getLogger("vitralis.licence")

PRODUCT = "vitralis"
"""The product's code in Clavren."""
LICENCE_FILE = "licence.dat"
PLATFORM = "windows-x86_64"


@dataclass(frozen=True, slots=True)
class LicenceParts:
    licence: Licence
    checks: LicenceChecks
    http: httpx.Client
    """Closed at shutdown, once ``LicenceGate.shutdown`` has stopped the checks that use it."""

    def close(self, working: bool = False) -> None:
        """Close the connection, unless ``working`` (``LicenceGate.working``): a request is still under way on a
        stalled network, and closing the connection under it would only make its thread fail noisily; it ends
        with the process."""
        if working:
            logger.warning("a licence request is still under way: its connection ends with the process")
            return
        self.http.close()


def build_licence(data_dir: Path) -> LicenceParts:
    """The licence from clavren.breren.com, kept in ``data_dir`` protected for this Windows account."""
    config = LicenceConfig(
        product=PRODUCT,
        app_version=app_version(),
        device_name=os.environ.get("COMPUTERNAME", "") or "computer",
        platform=PLATFORM,
    )
    http = secure_client()
    store = FileLicenceStore.for_windows(data_dir / LICENCE_FILE, PRODUCT)
    licence = Licence(config, store, HttpLicenceServer(http), Ed25519Crypto(), utc_now)
    return LicenceParts(licence, LicenceChecks(licence), http)
