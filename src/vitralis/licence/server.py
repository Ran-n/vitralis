#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:57.542529
Revised: 2026/11/11 11:06:53.855039

Clavren's application API over HTTPS (``../clavren/docs/api.md``, "Application API"). A plain ``http://``
address is refused unless it is this computer, because the key travels in the activation.
"""

from typing import Any
from urllib.parse import urlsplit

import httpx

from vitralis.licence.ports import ServerAnswer, ServerUnreachable
from vitralis.version import app_version

LICENCE_SERVER = "https://clavren.breren.com"
TIMEOUT_SECONDS = 15.0
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
USER_AGENT = f"vitralis/{app_version()}"
"""How the app introduces itself to its licence server."""


class HttpLicenceServer:
    def __init__(self, http: httpx.Client, base_url: str = LICENCE_SERVER) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS):
            raise ValueError(f"the licence server must be reached over HTTPS: {base_url}")
        self._http = http
        self._base = base_url.rstrip("/")

    def post(self, path: str, body: dict[str, Any]) -> ServerAnswer:
        url = self._base + path
        try:
            response = self._http.post(url, json=body, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as ex:
            raise ServerUnreachable(f"{url}: {type(ex).__name__}: {ex}") from ex
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        retry_after = response.headers.get("Retry-After", "")
        return ServerAnswer(
            status=response.status_code,
            body=parsed if isinstance(parsed, dict) else None,
            retry_after=int(retry_after) if retry_after.isdigit() else None,
        )
