#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:59.829681
Revised: 2026/11/13 09:11:00.247372

Downloads a release's exe into ``%APPDATA%\\Vitralis\\updates`` and checks it against the release's BLAKE3
checksum before it may be installed. The exe streams to ``<name>.part`` and only becomes ``<name>`` once its
hash matches; the checksum is kept beside it (``<name>.b3``) so a later start can trust it again.
"""

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from blake3 import blake3

from vitralis.net import is_secure_url
from vitralis.updates.rules import (
    ChecksumMismatch,
    Release,
    UpdateCancelled,
    UpdateError,
    checksum_name,
    exe_name,
    parse_b3,
)
from vitralis.version import USER_AGENT

logger = logging.getLogger("vitralis.updates.download")

CHUNK_BYTES = 64 * 1024
TIMEOUT_SECONDS = 30.0
_HEADERS = {"User-Agent": USER_AGENT}

Progress = Callable[[int, int | None], None]
"""(bytes received, total bytes or ``None`` when the server didn't say)."""


def file_hash(path: Path) -> str:
    hasher = blake3()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_release(
    http: httpx.Client, release: Release, target_dir: Path, progress: Progress, stop: threading.Event
) -> Path:
    """The verified exe in ``target_dir``; ``UpdateError`` (or ``ChecksumMismatch``, ``UpdateCancelled``) with
    no ``.part`` file left behind otherwise."""
    if not release.installable:
        raise UpdateError(f"release {release.version} has no exe with a checksum")
    name = exe_name(release.version)
    final = target_dir / name
    part = target_dir / (name + ".part")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        expected = parse_b3(_get_text(http, release.checksum_url))
        received, total, actual = _stream(http, release.exe_url, part, progress, stop)
        if total is not None and received != total:
            raise UpdateError(f"the download stopped at {received} of {total} bytes")
        if actual != expected:
            logger.warning("checksum mismatch for %s: expected %s, got %s", name, expected, actual)
            raise ChecksumMismatch(f"checksum mismatch for {name}")
        os.replace(part, final)
        (target_dir / checksum_name(release.version)).write_text(f"{expected}  {name}\n", encoding="utf-8")
        logger.info("downloaded and verified %s (%d bytes)", final, received)
        return final
    except UpdateError:
        raise
    except httpx.HTTPError as ex:
        raise UpdateError(f"{type(ex).__name__}: {ex}" if str(ex) else type(ex).__name__) from ex
    except ValueError as ex:
        raise UpdateError(str(ex)) from ex
    except OSError as ex:
        raise UpdateError(f"{type(ex).__name__}: {ex}") from ex
    finally:
        try:
            part.unlink(missing_ok=True)
        except OSError as ex:
            logger.warning("couldn't delete %s: %s", part, ex)


def _check_url(url: str | None) -> str:
    if url is None or not is_secure_url(url):
        raise UpdateError(f"refusing to download from {url!r}: not HTTPS")
    return url


def _get_text(http: httpx.Client, url: str | None) -> str:
    response = http.get(_check_url(url), timeout=TIMEOUT_SECONDS, headers=_HEADERS, follow_redirects=True)
    if response.status_code != 200:
        raise UpdateError(f"HTTP {response.status_code} for the checksum")
    return response.text


def _stream(
    http: httpx.Client, url: str | None, part: Path, progress: Progress, stop: threading.Event
) -> tuple[int, int | None, str]:
    hasher = blake3()
    received = 0
    with http.stream("GET", _check_url(url), timeout=TIMEOUT_SECONDS, headers=_HEADERS, follow_redirects=True) as r:
        if r.status_code != 200:
            raise UpdateError(f"HTTP {r.status_code} for the exe")
        length = r.headers.get("Content-Length", "")
        encoded = r.headers.get("Content-Encoding", "identity") != "identity"  # the length then counts the encoding
        total = int(length) if length.isdigit() and not encoded else None
        with part.open("wb") as file:
            for chunk in r.iter_bytes(CHUNK_BYTES):
                if stop.is_set():
                    logger.info("download of %s stopped: Vitralis is quitting", part.name)
                    raise UpdateCancelled("the download was stopped")
                file.write(chunk)
                hasher.update(chunk)
                received += len(chunk)
                progress(received, total)
    return received, total, hasher.hexdigest()
