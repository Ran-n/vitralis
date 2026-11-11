#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:56.247340
Revised: 2026/11/11 11:06:53.636980

What the licence use case needs from the outside: somewhere protected to keep its state, the Clavren server,
and Ed25519 for the device key and the server's tokens.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from vitralis.licence.rules import Claims


class LicenceStoreError(Exception):
    """The saved state couldn't be read back (damaged, or another Windows account's) or couldn't be saved."""


class LicenceStoreUnreadable(LicenceStoreError):
    """The saved state exists but couldn't be read (another program has it open): it must not be overwritten."""


class LicenceStore(Protocol):
    def load(self) -> bytes | None:
        """The saved state, ``None`` when there is none; raises ``LicenceStoreError``."""
        ...

    def save(self, data: bytes) -> None:
        """Replace the saved state whole; raises ``LicenceStoreError``."""
        ...


class ServerUnreachable(Exception):
    """No answer from the licence server (network, TLS, timeout)."""


@dataclass(frozen=True, slots=True)
class ServerAnswer:
    status: int
    body: dict[str, Any] | None
    """The JSON object answered; ``None`` when the body isn't one (a proxy's page)."""
    retry_after: int | None = None
    """``Retry-After`` in seconds, when given."""


class LicenceServer(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> ServerAnswer:
        """POST ``body`` as JSON to ``path`` (``/api/v1/…``); raises ``ServerUnreachable``."""
        ...


class TokenError(Exception):
    """A token the app can't run on: malformed, signed by a key it doesn't trust, for another product, expired."""


class LicenceCrypto(Protocol):
    def new_device_key(self) -> bytes:
        """A fresh Ed25519 private key's 32-byte seed."""
        ...

    def public_key(self, seed: bytes) -> bytes:
        """The 32-byte public key of ``seed``."""
        ...

    def sign(self, seed: bytes, message: bytes) -> bytes:
        """The 64-byte Ed25519 signature of ``message``."""
        ...

    def device_hash(self, public_key: bytes) -> str:
        """base64url of the BLAKE3 hash of ``public_key``, as the token's ``dev`` claim."""
        ...

    def verify_token(self, token: str, product: str, now: int) -> Claims:
        """The claims of ``token`` when a trusted key signed it for ``product`` and it hasn't expired at ``now``
        (Unix seconds); raises ``TokenError``."""
        ...
