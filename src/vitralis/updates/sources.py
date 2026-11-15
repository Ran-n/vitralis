#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:49.250623
Revised: 2026/11/15 14:24:49.250623

Where releases are read: GitHub and GitLab, both asked on every check (``vitralis.updates.check``), so one
forge being down or slow can't hide a release. Each answers ``latest()`` with the newest published release
that isn't a pre-release, or raises ``RequestFailed`` with a short reason.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Protocol

import httpx

from vitralis.net import is_secure_url
from vitralis.updates.http import RELEASE_CAP, RequestFailed, get_capped
from vitralis.updates.rules import Failure, Reason, Release, parse_version
from vitralis.updates.target import SOURCES_VARIABLE, override

logger = logging.getLogger("vitralis.updates.sources")

GITHUB_URL = "https://api.github.com/repos/Ran-n/vitralis/releases/latest"
GITLAB_URL = "https://gitlab.com/api/v4/projects/Ran-n%2Fvitralis/releases/permalink/latest"


class ReleaseSource(Protocol):
    name: str

    def latest(self) -> Release: ...


class MissingField(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"the answer has no {name}")


def _field(body: object, *path: str) -> object:
    value = body
    for name in path:
        if not isinstance(value, dict) or name not in value:
            raise MissingField(".".join(path))
        value = value[name]
    return value


def _text(body: object, *path: str) -> str:
    value = _field(body, *path)
    if not isinstance(value, str):
        raise MissingField(".".join(path))
    return value


class _JsonSource(ABC):
    name = ""
    accept = "application/json"

    def __init__(self, http: httpx.Client, url: str, allow_http: bool = False) -> None:
        self._http = http
        self._url = url
        self._allow_http = allow_http

    def latest(self) -> Release:
        try:
            raw = get_capped(self._http, self._url, self.accept, RELEASE_CAP, self._allow_http)
            try:
                return self._secure(self.parse(json.loads(raw)))
            except (ValueError, RecursionError) as ex:
                logger.warning("%s's answer can't be read: %s", self.name, ex)
                raise RequestFailed(Failure(Reason.UNREADABLE)) from ex
        except RequestFailed as ex:
            logger.warning("couldn't read the latest release from %s: %s", self.name, ex)
            raise

    @abstractmethod
    def parse(self, body: object) -> Release:
        """The release a forge's answer describes; ``ValueError`` when it doesn't."""

    def _secure(self, release: Release) -> Release:
        """Only files served over HTTPS (or plain HTTP where a test allowed it) count as the release's."""

        def ok(url: str) -> bool:
            return is_secure_url(url) or (self._allow_http and url.startswith("http://"))

        if not ok(release.page_url):
            raise ValueError("the release page isn't on HTTPS")
        kept = {name: url for name, url in release.assets.items() if ok(url)}
        for name in release.assets.keys() - kept.keys():
            logger.warning("%s: ignoring %s, which isn't on HTTPS", self.name, name)
        return replace(release, assets=kept)


class GitHubReleases(_JsonSource):
    name = "GitHub"
    accept = "application/vnd.github+json"

    def parse(self, body: object) -> Release:
        version = parse_version(_text(body, "tag_name"))
        page = _text(body, "html_url")
        assets = _field(body, "assets")
        if not isinstance(assets, list):
            raise MissingField("assets")
        found = {_text(asset, "name"): _text(asset, "browser_download_url") for asset in assets}
        return Release(version, page, found, self.name)


class GitLabReleases(_JsonSource):
    name = "GitLab"

    def parse(self, body: object) -> Release:
        version = parse_version(_text(body, "tag_name"))
        page = _text(body, "_links", "self")
        links = _field(body, "assets", "links")
        if not isinstance(links, list):
            raise MissingField("assets.links")
        found = {}
        for link in links:
            url = link.get("direct_asset_url") if isinstance(link, dict) else None
            found[_text(link, "name")] = url if isinstance(url, str) else _text(link, "url")
        return Release(version, page, found, self.name)


def default_sources(http: httpx.Client) -> list[ReleaseSource]:
    """GitHub, then GitLab; a copy run from source may point both elsewhere (plain HTTP allowed)."""
    given = override(SOURCES_VARIABLE)
    if given:
        github, _, gitlab = given.partition("|")
        return [GitHubReleases(http, github, allow_http=True), GitLabReleases(http, gitlab, allow_http=True)]
    return [GitHubReleases(http, GITHUB_URL), GitLabReleases(http, GITLAB_URL)]
