#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:48.964752
Revised: 2026/11/15 16:48:30.951759

Release signatures: every release file has ``<file>.sig``, an Ed25519 signature by Vitralis's release key over
a four-line statement of the version, the file's name and its BLAKE3 hash. Signing the version and the name
as well as the hash means a genuine older build, or another file of the release, can't be served as the
offered one. The updater downloads nothing before the signature checks out.

Two public keys are built in and either one is enough: the first signs every release, the second is a backup
whose secret is kept apart. If the first is lost or stolen, the next release is signed with the backup and
ships the backup plus a new key here.
"""

import secrets

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vitralis.updates.rules import NotSigned, Version
from vitralis.updates.target import APP, KEY_VARIABLE, override

STATEMENT_TAG = f"{APP}-release-v1"
RELEASE_KEYS: tuple[str, str] = (
    "91a53e4c73984752cf512f5714b9a87a38625a1c1eb3035bdec9ba1121d8d8a0",
    "98aa67221c8896fa8ae95daf0f9dede5fd88e89935a124696ce3e4fd91698b54",
)
"""The trusted public keys (hex): the signing key, then the backup. They are Vitralis's own; no other app
trusts them, and the statement's first line names the app as well."""


class Unreadable(ValueError):
    """A key or a signature that isn't the hex it must be; the message names which."""


class UnreadableSignature(Unreadable):
    pass


class UnreadableKey(Unreadable):
    pass


def release_keys() -> tuple[str, ...]:
    """The built-in keys, or the test key a copy run from source was given."""
    test_key = override(KEY_VARIABLE)
    return (test_key,) if test_key else RELEASE_KEYS


def statement(version: Version | str, asset: str, file_hash: str) -> bytes:
    return f"{STATEMENT_TAG}\n{version}\n{asset}\n{file_hash.lower()}\n".encode()


def _decode(text: str, size: int, what: str, error: type[Unreadable] = UnreadableKey) -> bytes:
    text = text.strip()
    try:
        if len(text) != 2 * size or not text.isascii():
            raise ValueError(text)
        return bytes.fromhex(text)
    except ValueError as ex:
        raise error(f"{what} isn't {2 * size} hex digits") from ex


def verify(key: str, signed: bytes, signature: str) -> None:
    """Silent when ``signature`` (the ``.sig`` text) is ``key``'s over ``signed``; ``Unreadable`` when either
    isn't hex of the right length, ``NotSigned`` when it is someone else's or over something else."""
    raw = _decode(signature.splitlines()[0] if signature.strip() else "", 64, "the signature", UnreadableSignature)
    public = Ed25519PublicKey.from_public_bytes(_decode(key, 32, "the release key"))  # takes any 32 bytes
    try:
        public.verify(raw, signed)
    except InvalidSignature as ex:
        raise NotSigned("the signature isn't by this key, or not over this file") from ex


def verify_any(keys: tuple[str, ...], signed: bytes, signature: str) -> None:
    """Silent when any key in ``keys`` signed ``signed``. An unreadable signature is said at once; an
    unreadable key among good ones hides neither a match nor a refusal."""
    unreadable_key: UnreadableKey | None = None
    refused = False
    for key in keys:
        try:
            verify(key, signed, signature)
            return
        except UnreadableKey as ex:
            unreadable_key = unreadable_key or ex
        except NotSigned:
            refused = True
    if refused or unreadable_key is None:
        raise NotSigned("the signature isn't by a key Vitralis trusts")
    raise unreadable_key


def generate() -> str:
    """A new secret key: 32 random bytes as one line of hex."""
    return secrets.token_bytes(32).hex()


def _private(secret: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_decode(secret, 32, "the secret key"))  # any 32 bytes are a key


def public_key(secret: str) -> str:
    raw = _private(secret).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return raw.hex()


def sign(secret: str, signed: bytes) -> str:
    """The ``.sig`` text: 128 hex digits and a line break."""
    return _private(secret).sign(signed).hex() + "\n"
