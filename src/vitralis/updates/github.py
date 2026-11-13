#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:59.086594
Revised: 2026/11/13 09:10:59.453239

The latest Vitralis release, from GitHub's REST API (``GET /repos/Ran-n/vitralis/releases/latest``: the newest
release that is neither a draft nor a pre-release). GitHub only: GitLab and Codeberg carry the same releases,
and the landing page reads GitHub too.
"""

import logging
from typing import Protocol

import httpx

from vitralis.net import is_secure_url
from vitralis.updates.rules import Release, checksum_name, exe_name, parse_version
from vitralis.version import USER_AGENT

logger = logging.getLogger("vitralis.updates.github")

RELEASES_URL = "https://api.github.com/repos/Ran-n/vitralis/releases/latest"
TIMEOUT_SECONDS = 15.0
RATE_LIMITED = frozenset({403, 429})
"""GitHub's answers once an address has used its 60 unauthenticated calls of the hour."""


class ReleaseFeedError(Exception):
    """The latest release couldn't be read; the message is a one-line reason."""


class ReleaseFeed(Protocol):
    def latest(self) -> Release: ...


class GitHubReleases:
    def __init__(self, http: httpx.Client, url: str = RELEASES_URL) -> None:
        if not is_secure_url(url):
            raise ValueError(f"the release feed must be reached over HTTPS: {url}")
        self._http = http
        self._url = url

    def latest(self) -> Release:
        try:
            return self._read()
        except ReleaseFeedError as ex:
            logger.warning("couldn't read the latest release from %s: %s", self._url, ex)
            raise

    def _read(self) -> Release:
        try:
            response = self._http.get(
                self._url,
                timeout=TIMEOUT_SECONDS,
                headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        except httpx.HTTPError as ex:
            raise ReleaseFeedError(f"{type(ex).__name__}: {ex}" if str(ex) else type(ex).__name__) from ex
        if response.status_code in RATE_LIMITED:
            raise ReleaseFeedError(f"GitHub's rate limit was reached (HTTP {response.status_code}); try later")
        if response.status_code != 200:
            raise ReleaseFeedError(f"HTTP {response.status_code}")
        try:
            body = response.json()
            version = parse_version(body["tag_name"])
            page_url = body["html_url"]
            assets = {asset["name"]: asset["browser_download_url"] for asset in body.get("assets", [])}
        except (ValueError, KeyError, TypeError, AttributeError) as ex:
            raise ReleaseFeedError(f"unexpected answer: {type(ex).__name__}: {ex}") from ex
        if not (isinstance(page_url, str) and is_secure_url(page_url)):
            raise ReleaseFeedError(f"unexpected release page: {page_url!r}")
        return Release(
            version=version,
            page_url=page_url,
            exe_url=_secure_or_none(assets.get(exe_name(version))),
            checksum_url=_secure_or_none(assets.get(checksum_name(version))),
        )


def _secure_or_none(url: object) -> str | None:
    if isinstance(url, str) and is_secure_url(url):
        return url
    if url is not None:
        logger.warning("ignoring a release asset that isn't on HTTPS: %r", url)
    return None
