#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:59.829681
Revised: 2026/11/21 18:29:10.933076

Downloads an offered release's exe, proven before a single byte of it is asked for: the ``.b3`` gives the
hash, and the ``.minisig``'s trusted comment must be a trusted key's, for this version, this file name and that
hash. Only then is the exe streamed, in 64 KiB chunks, into a ``vitralis-update-*`` file in the download
folder, hashed as it comes; its BLAKE3 hash must match and the signature must hold over its BLAKE2b-512
hash. It stops on Cancel, past ``MAX_BYTES``, after ``STALL_SECONDS`` without data or ``TOTAL_SECONDS``
in all; on any failure the file is deleted.
"""

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from vitralis.updates.http import SMALL_CAP, RequestFailed, check_url, failure_of, get_capped, headers
from vitralis.updates.rules import (
    ChecksumMismatch,
    DownloadFailed,
    Failure,
    NotSigned,
    Offer,
    Reason,
    UpdateCancelled,
    UpdateError,
    parse_b3,
)
from vitralis.updates.signature import Unreadable
from vitralis.updates.signature.hashes import FileHashes, hash_file
from vitralis.updates.signature.minisign import Minisig, accept, check_file, trusted_comment

logger = logging.getLogger("vitralis.updates.download")

CHUNK_BYTES = 64 * 1024
MAX_BYTES = 200 << 20
STALL_SECONDS = 60.0
TOTAL_SECONDS = 30 * 60.0
CONNECT_SECONDS = 10.0
TEMP_PREFIX = "vitralis-update-"
"""Every download's file starts with it, so a later start can tell what is the updater's to tidy."""

Progress = Callable[[int, int | None], None]
"""(bytes received, total bytes or ``None`` when the server didn't say)."""


def file_hash(path: Path) -> str:
    return hash_file(path).blake3


@dataclass(frozen=True, slots=True)
class Proof:
    """What a release file must turn out to be: its BLAKE3 hash, and the signature (by ``key``) its bytes must
    satisfy."""

    blake3: str
    key: str
    minisig: Minisig


def prove(http: httpx.Client, offer: Offer, keys: tuple[str, ...], allow_http: bool = False) -> Proof:
    """The exe's expected hash and signature, once its checksum has been read and the signature's trusted
    comment checked; raises otherwise. Nothing here asks for the exe itself."""
    try:
        expected = parse_b3(get_capped(http, offer.checksum_url, "text/plain", SMALL_CAP, allow_http).decode())
    except RequestFailed as ex:
        raise DownloadFailed(ex.failure) from ex
    except (ValueError, UnicodeDecodeError) as ex:
        raise ChecksumMismatch("the checksum file can't be read") from ex
    try:
        signature = get_capped(http, offer.signature_url, "text/plain", SMALL_CAP, allow_http).decode()
    except RequestFailed as ex:
        raise DownloadFailed(ex.failure) from ex
    except UnicodeDecodeError as ex:
        raise NotSigned("the signature can't be read") from ex
    try:
        key, minisig = accept(keys, signature, trusted_comment(offer.release.version, offer.asset, expected))
    except Unreadable as ex:
        raise NotSigned(str(ex)) from ex
    return Proof(expected, key, minisig)


def download_offer(
    http: httpx.Client,
    offer: Offer,
    folder: Path,
    progress: Progress,
    cancel: threading.Event,
    keys: tuple[str, ...],
    allow_http: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> Path:
    """The proven, verified exe in ``folder``; ``UpdateError`` (one of its kinds) with nothing left behind
    otherwise."""
    proof = prove(http, offer, keys, allow_http)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=".exe", dir=folder)
    except OSError as ex:
        raise UpdateError(f"the download folder can't be written to: {ex}") from ex
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as file:
            actual = _stream(http, offer, file, progress, cancel, allow_http, clock)
            file.flush()
            os.fsync(file.fileno())
        if actual.blake3 != proof.blake3:
            logger.error("checksum mismatch for %s: expected %s, got %s", offer.asset, proof.blake3, actual.blake3)
            raise ChecksumMismatch(f"checksum mismatch for {offer.asset}")
        check_file(proof.key, proof.minisig, actual.blake2b)
        if cancel.is_set():  # a quit or Cancel during the hash check must not lead to a replace
            raise UpdateCancelled("the download was stopped")
        logger.info("downloaded and verified %s as %s", offer.asset, path)
        return path
    except BaseException:
        _delete(path)
        raise


def _stream(
    http, offer: Offer, file, progress: Progress, cancel: threading.Event, allow_http: bool, clock
) -> FileHashes:
    hasher = FileHashes()
    received = 0
    started = clock()
    timeout = httpx.Timeout(STALL_SECONDS, connect=CONNECT_SECONDS)
    try:
        url = check_url(offer.asset_url, allow_http)
        accept = headers("application/octet-stream")
        with http.stream("GET", url, timeout=timeout, headers=accept, follow_redirects=True) as response:
            check_url(str(response.url), allow_http)
            if response.status_code != 200:
                raise RequestFailed(Failure(Reason.ANSWERED, response.status_code))
            length = response.headers.get("Content-Length", "")
            encoded = response.headers.get("Content-Encoding", "identity") != "identity"
            total = int(length) if length.isdigit() and not encoded else None
            if total is not None and total > MAX_BYTES:
                raise RequestFailed(Failure(Reason.TOO_LARGE))
            for chunk in response.iter_bytes(CHUNK_BYTES):
                if cancel.is_set():
                    logger.info("the download of %s was cancelled", offer.asset)
                    raise UpdateCancelled("the download was stopped")
                received += len(chunk)
                if received > MAX_BYTES:
                    raise RequestFailed(Failure(Reason.TOO_LARGE))
                if clock() - started > TOTAL_SECONDS:
                    logger.warning("the download of %s took over %.0f minutes", offer.asset, TOTAL_SECONDS / 60)
                    raise RequestFailed(Failure(Reason.TIMED_OUT))
                file.write(chunk)
                hasher.update(chunk)
                progress(received, total)  # a body short of its declared length raises in httpx itself
    except RequestFailed as ex:
        raise DownloadFailed(ex.failure) from ex
    except httpx.HTTPError as ex:
        raise DownloadFailed(failure_of(ex)) from ex
    except OSError as ex:  # the disk, not the network: full, or the folder went away
        raise UpdateError(f"the download couldn't be saved: {ex}") from ex
    return hasher


def _delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as ex:
        logger.warning("couldn't delete %s (the next start tries again): %s", path, ex)
