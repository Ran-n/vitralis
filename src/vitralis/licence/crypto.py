#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:56.875569
Revised: 2026/11/11 11:06:53.427681

Ed25519 for the device key and Clavren's tokens (JWTs signed ``EdDSA``), BLAKE3 for the device hash.

The app trusts only the token-signing public keys it is built with (``TRUSTED_KEYS``), by key version
(``kid``); ``clavren-admin show-public-key`` on the server prints them. To move the server to a new key without
locking anyone out: ship a version that trusts both, then switch the server once every copy in use has it.
"""

import json
import secrets
from collections.abc import Mapping

import blake3
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vitralis.licence.ports import TokenError
from vitralis.licence.rules import Claims, b64decode, b64encode, unverified_claims

TRUSTED_KEYS = {
    "v1": "j3nwtuQyGUnpr2MY888Pjx4OM92Zk5hVjNbG1vAamug",
    "v2": "ZHQ5452QCdy6syIlT7OfwNQLyPRKw_JB6DWQRkZUe2s",
}
"""clavren.breren.com's token-signing keys: ``v1`` in use, ``v2`` the next (2026-11-11)."""


class Ed25519Crypto:
    def __init__(self, trusted_keys: Mapping[str, str] = TRUSTED_KEYS) -> None:
        """``trusted_keys``: base64url public keys by ``kid``; raises ``ValueError`` when one isn't a key."""
        self._trusted: dict[str, Ed25519PublicKey] = {}
        for kid, text in trusted_keys.items():
            raw = b64decode(text)
            if raw is None or len(raw) != 32:
                raise ValueError(f"trusted key {kid} is not a 32-byte base64url Ed25519 key")
            self._trusted[kid] = Ed25519PublicKey.from_public_bytes(raw)

    def new_device_key(self) -> bytes:
        return secrets.token_bytes(32)

    def public_key(self, seed: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def sign(self, seed: bytes, message: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(seed).sign(message)

    def device_hash(self, public_key: bytes) -> str:
        return b64encode(blake3.blake3(public_key).digest())

    def verify_token(self, token: str, product: str, now: int) -> Claims:
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenError("the token is malformed")
        header_part, claims_part, signature_part = parts
        header = _json(header_part)
        if header.get("alg") != "EdDSA" or header.get("typ") != "JWT":
            raise TokenError("the token is malformed")
        key = self._trusted.get(header.get("kid"))
        if key is None:
            raise TokenError("the token was signed with a key this app doesn't trust")
        signature = b64decode(signature_part)
        if signature is None or len(signature) != 64:
            raise TokenError("the token is malformed")
        try:
            key.verify(signature, f"{header_part}.{claims_part}".encode())
        except InvalidSignature as ex:
            raise TokenError("the token's signature is wrong") from ex
        claims = unverified_claims(token)
        if claims is None:
            raise TokenError("the token is malformed")
        if claims.aud != product:
            raise TokenError("the token is for another product")
        if claims.exp <= now:
            raise TokenError("the token has expired")
        return claims


def _json(part: str) -> dict:
    raw = b64decode(part)
    try:
        value = json.loads(raw) if raw is not None else None
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise TokenError("the token is malformed")
    return value
