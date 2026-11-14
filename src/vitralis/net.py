#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:18.246169
Revised: 2026/11/14 12:01:47.629997

Which addresses Vitralis talks to: HTTPS, or plain HTTP to this computer only (tests and local end-to-end
checks), for the licence server, the release feed and the downloads alike. ``secure_client`` makes the HTTP
client that holds to it on every request, the ones a redirect leads to included.
"""

from urllib.parse import urlsplit

import httpx

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_secure_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS)


class InsecureAddress(httpx.RequestError):
    """A request to an address that isn't HTTPS; it was never sent."""


def _refuse_insecure(request: httpx.Request) -> None:
    if not is_secure_url(str(request.url)):
        raise InsecureAddress(f"refusing {request.url.scheme}://{request.url.host}: not HTTPS", request=request)


def secure_client() -> httpx.Client:
    """A client that sends nothing to an address ``is_secure_url`` refuses. A download checks its first address
    itself, but GitHub answers with redirects, and each hop goes through here before it is sent."""
    return httpx.Client(event_hooks={"request": [_refuse_insecure]})
