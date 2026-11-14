#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:57.610048
Revised: 2026/11/14 12:01:47.849879

Vitralis's updater: at start and once a day it asks GitHub for the latest release and, when that is newer,
says so (a dot on the toolbar's Settings button, one tray message, Settings → Updates). In the packaged exe it
also downloads the new exe, checks its BLAKE3 checksum and, on **Restart to update**, puts it at the running
exe's path and starts it. Layout as in ``vitralis.licence``: ``rules`` (no I/O), the adapters ``github``,
``download`` and ``install``, and the Qt side in ``checker`` and ``section``.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from vitralis.net import secure_client
from vitralis.updates.checker import Installer, UpdateChecker, UpdateSettings
from vitralis.updates.download import download_release
from vitralis.updates.github import RELEASES_URL, GitHubReleases
from vitralis.version import app_version

logger = logging.getLogger("vitralis.updates")

RELEASES_URL_VARIABLE = "VITRALIS_RELEASES_URL"
"""Replaces the GitHub API URL, so tests and the end-to-end update check can serve their own release JSON."""
UPDATES_DIR = "updates"


def is_packaged() -> bool:
    """The PyInstaller exe, which can replace itself; a source checkout can't."""
    return bool(getattr(sys, "frozen", False))


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


def build_updates(data_dir: Path, settings: UpdateSettings) -> UpdateParts:
    http = secure_client()
    feed = GitHubReleases(http, os.environ.get(RELEASES_URL_VARIABLE) or RELEASES_URL)
    updates_dir = data_dir / UPDATES_DIR

    def download(release, progress, stop) -> Path:
        return download_release(http, release, updates_dir, progress, stop)

    installer = Installer(Path(sys.executable), updates_dir, download) if is_packaged() else None
    return UpdateParts(UpdateChecker(feed, settings, app_version(), installer=installer), http)
