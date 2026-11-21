#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:51.094676
Revised: 2026/11/21 18:28:51.094676

The ``.minisig`` file, in minisign's format (https://jedisct1.github.io/minisign/), prehashed mode only:

    untrusted comment: signature from vitralis-sign
    <base64 of "ED" + key ID + Ed25519 signature over the file's BLAKE2b-512 hash>
    trusted comment: vitralis-release-v2 version:<version> file:<file name> blake3:<BLAKE3 hash>
    <base64 of the Ed25519 signature over the first signature's 64 bytes + the trusted comment>

The trusted comment is the release statement: signing the version and the name as well as the hash means a
genuine older build, or another file of the release, can't be served as the offered one. It is checked twice:
before the download, the second signature and the comment, for the offered version, name and ``.b3`` hash;
after it, the first signature, over the bytes that arrived.
"""

import base64
import binascii
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from vitralis.updates.rules import NotSigned, Version
from vitralis.updates.signature import (
    KEY_ID_BYTES,
    UnreadableKey,
    UnreadableSignature,
    decode_hex,
    key_id,
    private_key,
    public_key,
)
from vitralis.updates.target import APP

COMMENT_TAG = f"{APP}-release-v2"
UNTRUSTED_PREFIX = "untrusted comment: "
TRUSTED_PREFIX = "trusted comment: "
UNTRUSTED_COMMENT = f"{UNTRUSTED_PREFIX}signature from {APP}-sign"
PREHASHED = b"ED"
LEGACY = b"Ed"
SIGNATURE_BYTES = 64


@dataclass(frozen=True, slots=True)
class Minisig:
    key_id: bytes
    signature: bytes
    """Over the file's BLAKE2b-512 hash."""
    comment: str
    global_signature: bytes
    """Over ``signature`` + ``comment``."""


def trusted_comment(version: Version | str, asset: str, blake3_hash: str) -> str:
    return f"{COMMENT_TAG} version:{version} file:{asset} blake3:{blake3_hash.lower()}"


def sign(secret: str, blake2b: bytes, comment: str) -> str:
    """The ``.minisig`` text for a file whose BLAKE2b-512 hash is ``blake2b``."""
    if "\n" in comment or "\r" in comment:
        raise ValueError("a trusted comment is one line")
    key = private_key(secret)
    public = bytes.fromhex(public_key(secret))
    signature = key.sign(blake2b)
    global_signature = key.sign(signature + comment.encode("utf-8"))
    lines = (
        UNTRUSTED_COMMENT,
        _b64(PREHASHED + key_id(public) + signature),
        TRUSTED_PREFIX + comment,
        _b64(global_signature),
    )
    return "\n".join(lines) + "\n"


def parse(text: str) -> Minisig:
    """The four lines, or ``UnreadableSignature`` naming what is wrong with them."""
    lines = text.splitlines()
    if len(lines) < 4:
        raise UnreadableSignature("the signature file has fewer than four lines")
    untrusted, first, trusted, second = (line.rstrip("\r") for line in lines[:4])
    if not untrusted.startswith(UNTRUSTED_PREFIX):
        raise UnreadableSignature("the signature file has no untrusted comment")
    if not trusted.startswith(TRUSTED_PREFIX):
        raise UnreadableSignature("the signature file has no trusted comment")
    signed = _unb64(first, "the signature")
    algorithm, signature_key_id, signature = signed[:2], signed[2 : 2 + KEY_ID_BYTES], signed[2 + KEY_ID_BYTES :]
    if algorithm == LEGACY:
        raise UnreadableSignature("the signature is in minisign's legacy mode, not the prehashed one")
    if algorithm != PREHASHED or len(signature) != SIGNATURE_BYTES:
        raise UnreadableSignature("the signature isn't a prehashed Ed25519 one")
    global_signature = _unb64(second, "the trusted comment's signature")
    if len(global_signature) != SIGNATURE_BYTES:
        raise UnreadableSignature("the trusted comment's signature isn't 64 bytes")
    return Minisig(signature_key_id, signature, trusted.removeprefix(TRUSTED_PREFIX), global_signature)


def accept(keys: tuple[str, ...], text: str, comment: str) -> tuple[str, Minisig]:
    """The trusted key whose ID matches and whose signature holds over the trusted comment, which must be
    ``comment`` character for character; ``Unreadable`` or ``NotSigned`` otherwise. An unreadable key among
    good ones hides neither a match nor a refusal."""
    minisig = parse(text)
    unreadable_key: UnreadableKey | None = None
    for key in keys:
        try:
            public = decode_hex(key, 32, "the release key")
        except UnreadableKey as ex:
            unreadable_key = unreadable_key or ex
            continue
        if key_id(public) == minisig.key_id and _holds(public, minisig.global_signature, _comment_signed(minisig)):
            if minisig.comment != comment:
                raise NotSigned(f"the signature is for {minisig.comment!r}, not {comment!r}")
            return key, minisig
    if unreadable_key is not None and not any(_readable(key) for key in keys):
        raise unreadable_key
    raise NotSigned("the signature isn't by a key Vitralis trusts")


def check_file(key: str, minisig: Minisig, blake2b: bytes) -> None:
    """Silent when the first signature, by ``key``, is over these bytes' BLAKE2b-512 hash."""
    if not _holds(decode_hex(key, 32, "the release key"), minisig.signature, blake2b):
        raise NotSigned("the signature isn't over the file that arrived")


def _comment_signed(minisig: Minisig) -> bytes:
    return minisig.signature + minisig.comment.encode("utf-8")


def _holds(public: bytes, signature: bytes, signed: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, signed)
    except InvalidSignature:
        return False
    return True


def _readable(key: str) -> bool:
    try:
        decode_hex(key, 32, "the release key")
    except UnreadableKey:
        return False
    return True


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as ex:
        raise UnreadableSignature(f"{what} isn't base64") from ex
