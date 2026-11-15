#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:57.610048
Revised: 2026/11/15 14:27:01.681509

Vitralis's updater: a minute after start and then once a day it asks GitHub and GitLab for the latest
release and, when that is newer, says so (a dot on the toolbar's Settings button, one tray message, Settings
→ Updates). In the packaged release exe, **Update and restart** proves the release (its BLAKE3 checksum and
an Ed25519 signature by Vitralis's release key) before downloading it, puts it at the running exe's path and
starts it. A build from source asks nobody. Layout: ``rules`` (no I/O), ``target`` (which build, which file
names), ``signature``, the adapters ``http``, ``sources``, ``check``, ``download`` and ``install``, and the
Qt side in ``checker`` and ``section``.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from vitralis.net import secure_client
from vitralis.updates.check import ask_all
from vitralis.updates.checker import Installer, UpdateChecker, UpdateSettings
from vitralis.updates.download import download_offer
from vitralis.updates.signature import release_keys
from vitralis.updates.sources import default_sources
from vitralis.updates.target import DIR_VARIABLE, SOURCES_VARIABLE, is_packaged, override, release_target
from vitralis.version import app_version

logger = logging.getLogger("vitralis.updates")

UPDATES_DIR = "updates"


def download_dir() -> Path:
    """Where downloads go: ``%LOCALAPPDATA%\\Vitralis\\updates``, a cache that never roams with the profile."""
    given = override(DIR_VARIABLE)
    if given:
        return Path(given)
    return Path(os.getenv("LOCALAPPDATA", Path.home())) / "Vitralis" / UPDATES_DIR


def legacy_download_dir(data_dir: Path) -> Path:
    """Where Vitralis 1.3 kept a downloaded update, tidied once."""
    return data_dir / UPDATES_DIR


@dataclass(frozen=True, slots=True)
class UpdateParts:
    checker: UpdateChecker
    http: httpx.Client
    """Closed at shutdown, once ``UpdateChecker.stop`` has stopped the download that uses it."""

    def close(self) -> None:
        """Close the connection, unless a request is still under way on a worker thread (a stalled network):
        closing it under the request would only make that thread fail noisily; it ends with the process."""
        if self.checker.working:
            logger.warning("an update request is still under way: its connection ends with the process")
            return
        self.http.close()


def build_updates(settings: UpdateSettings) -> UpdateParts:
    http = secure_client()
    sources = default_sources(http)
    target = release_target()
    allow_http = override(SOURCES_VARIABLE) is not None
    keys = release_keys()
    folder = download_dir()

    def download(offer, progress, cancel) -> Path:
        return download_offer(http, offer, folder, progress, cancel, keys, allow_http)

    installer = Installer(Path(sys.executable), download) if is_packaged() and target is not None else None
    checker = UpdateChecker(lambda: ask_all(sources), settings, app_version(), target, installer=installer)
    return UpdateParts(checker, http)
