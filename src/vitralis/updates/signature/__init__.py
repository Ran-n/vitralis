#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:50.902301
Revised: 2026/11/21 18:28:50.902301

Release keys. Every release file has ``<file>.minisig``, a signature in minisign's format by Vitralis's release
key (``minisign.py``); anyone can check a download with ``minisign -Vm <file> -P <key>``, and the updater
downloads nothing before the signature checks out.

Two public keys are built in and either one is enough: the first signs every release, the second is a backup
whose secret is kept apart. If the first is lost or stolen, the next release is signed with the backup and
ships the backup plus a new key here. A secret key is one line of hex (32 bytes), so it can live in a password
manager and be piped in.
"""

import base64
import secrets

from blake3 import blake3
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vitralis.updates.target import KEY_VARIABLE, override

RELEASE_KEYS: tuple[str, str] = (
    "65bb6c98382751dd8ac6d76f08694cb54bd7934ea5a149d54f0135ab2dcdac5b",
    "3039469ef988ac4cd38c4f02a313a2cfe0e0e15636ea1089153fb842ee4e8a83",
)
"""The trusted public keys (hex): the signing key, then the backup. They are Vitralis's own; no other app
trusts them, and the signature's trusted comment names the app as well."""
KEY_ID_BYTES = 8
PUBLIC_KEY_PREFIX = b"Ed"
"""minisign's algorithm tag in a public key: Ed25519."""


class Unreadable(ValueError):
    """A key or a signature that isn't in the form it must be; the message names which."""


class UnreadableSignature(Unreadable):
    pass


class UnreadableKey(Unreadable):
    pass


def release_keys() -> tuple[str, ...]:
    """The built-in keys, or the test key a copy run from source was given."""
    test_key = override(KEY_VARIABLE)
    return (test_key,) if test_key else RELEASE_KEYS


def decode_hex(text: str, size: int, what: str, error: type[Unreadable] = UnreadableKey) -> bytes:
    text = text.strip()
    try:
        if len(text) != 2 * size or not text.isascii():
            raise ValueError(text)
        return bytes.fromhex(text)
    except ValueError as ex:
        raise error(f"{what} isn't {2 * size} hex digits") from ex


def key_id(public: bytes) -> bytes:
    """The first 8 bytes of the public key's BLAKE3 hash: the same key always has the same ID, so it needs no
    storing. It proves nothing (anyone can copy it); only the signatures do."""
    return blake3(public).digest()[:KEY_ID_BYTES]


def minisign_public(public_hex: str) -> str:
    """The public key in minisign's form: base64 of ``Ed``, the key ID and the key (56 characters, ``RW…``)."""
    public = decode_hex(public_hex, 32, "the release key")
    return base64.b64encode(PUBLIC_KEY_PREFIX + key_id(public) + public).decode("ascii")


def generate() -> str:
    """A new secret key: 32 random bytes as one line of hex."""
    return secrets.token_bytes(32).hex()


def private_key(secret: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(decode_hex(secret, 32, "the secret key"))  # any 32 bytes are a key


def public_key(secret: str) -> str:
    """The public key (hex) of a secret key."""
    return private_key(secret).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
