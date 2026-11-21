#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:50.993967
Revised: 2026/11/21 18:28:50.993967

The two hashes a release file is proven by, taken in one pass over its bytes: BLAKE3, which the ``.b3`` file
names and the signature's trusted comment repeats, and BLAKE2b-512, which minisign's prehashed signature is
made over.
"""

import hashlib
from pathlib import Path

from blake3 import blake3

READ_BYTES = 1 << 20


class FileHashes:
    """Both hashes, fed chunk by chunk as a download arrives."""

    def __init__(self) -> None:
        self._blake3 = blake3()
        self._blake2b = hashlib.blake2b(digest_size=64)

    def update(self, chunk: bytes) -> None:
        self._blake3.update(chunk)
        self._blake2b.update(chunk)

    @property
    def blake3(self) -> str:
        """Lowercase hex, as the ``.b3`` file and the trusted comment hold it."""
        return self._blake3.hexdigest()

    @property
    def blake2b(self) -> bytes:
        """The 64 bytes minisign signs."""
        return self._blake2b.digest()


def hash_file(path: Path) -> FileHashes:
    hashes = FileHashes()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(READ_BYTES), b""):
            hashes.update(chunk)
    return hashes


def hash_bytes(data: bytes) -> FileHashes:
    hashes = FileHashes()
    hashes.update(data)
    return hashes
