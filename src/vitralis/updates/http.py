#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:48.675269
Revised: 2026/11/15 14:24:48.675269

The updater's requests: HTTPS only (unless a test allowed plain HTTP), capped in size, carrying nothing but the
URL, ``Accept`` and ``User-Agent: Vitralis/<version>``. Every failure comes back as a short ``Failure`` the
user can read: no URL, no header, no stack.
"""

import ssl

import httpx

from vitralis.net import InsecureAddress, is_secure_url
from vitralis.updates.rules import Failure, Reason
from vitralis.version import app_version

CONNECT_SECONDS = 10.0
READ_SECONDS = 30.0
RELEASE_CAP = 1 << 20
"""A release's JSON."""
SMALL_CAP = 1 << 10
"""A ``.b3`` or ``.sig``."""
USER_AGENT = f"Vitralis/{app_version()}"


class RequestFailed(Exception):
    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.reason.value.format(status=failure.status))
        self.failure = failure


def timeout() -> httpx.Timeout:
    return httpx.Timeout(READ_SECONDS, connect=CONNECT_SECONDS)


def headers(accept: str) -> dict[str, str]:
    return {"Accept": accept, "User-Agent": USER_AGENT}


def check_url(url: str, allow_http: bool = False) -> str:
    if is_secure_url(url) or (allow_http and url.startswith("http://")):
        return url
    raise RequestFailed(Failure(Reason.NOT_HTTPS))


def failure_of(ex: Exception) -> Failure:
    """The short reason for a request's exception."""
    if isinstance(ex, RequestFailed):
        return ex.failure
    if isinstance(ex, InsecureAddress):  # a redirect to plain HTTP, refused before it was sent
        return Failure(Reason.NOT_HTTPS)
    if isinstance(ex, httpx.TimeoutException):
        return Failure(Reason.TIMED_OUT)
    text = f"{ex} {ex.__cause__ or ''} {ex.__context__ or ''}".lower()
    if isinstance(ex, httpx.ConnectError) and ("getaddrinfo" in text or "11001" in text or "name or service" in text):
        return Failure(Reason.NOT_FOUND)
    if isinstance(ex, ssl.SSLError) or isinstance(ex.__cause__, ssl.SSLError) or "ssl" in text or "certificate" in text:
        return Failure(Reason.TLS)
    if isinstance(ex, (httpx.TransportError, OSError)):
        return Failure(Reason.CONNECTION)
    return Failure(Reason.UNREADABLE)


def get_capped(http: httpx.Client, url: str, accept: str, cap: int, allow_http: bool = False) -> bytes:
    """The body of a 200 answer, at most ``cap`` bytes; ``RequestFailed`` otherwise. Redirects are followed,
    and each hop must be HTTPS as well."""
    check_url(url, allow_http)
    try:
        with http.stream("GET", url, timeout=timeout(), headers=headers(accept), follow_redirects=True) as response:
            check_url(str(response.url), allow_http)
            if response.status_code != 200:
                raise RequestFailed(Failure(Reason.ANSWERED, response.status_code))
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > cap:
                raise RequestFailed(Failure(Reason.TOO_LARGE))
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > cap:
                    raise RequestFailed(Failure(Reason.TOO_LARGE))
            return bytes(body)
    except RequestFailed:
        raise
    except (httpx.HTTPError, OSError) as ex:
        raise RequestFailed(failure_of(ex)) from ex
