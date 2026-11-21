#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:51.910651
Revised: 2026/11/21 18:28:51.910651

The ``.minisig`` format: four lines in minisign's prehashed mode; accepted only for its own trusted comment
(version, file name, hash), its own bytes and a trusted key whose ID matches; either built-in key is enough and a
rotated-out key stops counting; malformed files and keys are named; the untrusted comment and ``\\r\\n`` change
nothing; parts of two genuine files can't be mixed. An independent minisign implementation (py-minisign) accepts
what Vitralis writes, and reference vectors pin both hashes.
"""

import base64

import minisign as independent
import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.updates.fakes import OTHER_SECRET, PUBLIC, SECRET, minisig
from vitralis.updates.rules import NotSigned
from vitralis.updates.signature import UnreadableKey, UnreadableSignature, minisign_public, public_key
from vitralis.updates.signature.hashes import hash_bytes
from vitralis.updates.signature.minisign import COMMENT_TAG, accept, check_file, parse, sign, trusted_comment

DATA = b"MZ" + bytes(range(256)) * 40
ASSET = "vitralis-1.4.0-windows-x86_64-portable.exe"
COMMENT = trusted_comment("1.4.0", ASSET, hash_bytes(DATA).blake3)
TEXT = minisig(DATA, SECRET, "1.4.0", ASSET)


def replace_line(text: str, index: int, line: str) -> str:
    lines = text.splitlines()
    lines[index] = line
    return "\n".join(lines) + "\n"


def test_the_hashes_match_reference_vectors():
    hashes = hash_bytes(b"abc")
    assert hashes.blake3 == "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"
    assert hashes.blake2b.hex() == (
        "ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d1"
        "7d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923"
    )


def test_the_file_is_four_lines_whose_trusted_comment_is_the_release_statement():
    lines = TEXT.splitlines()
    assert len(lines) == 4 and TEXT.endswith("\n") and "\r" not in TEXT
    assert lines[0] == "untrusted comment: signature from vitralis-sign"
    assert lines[2] == f"trusted comment: {COMMENT}"
    assert f"vitralis-release-v2 version:1.4.0 file:{ASSET} blake3:{hash_bytes(DATA).blake3}" == COMMENT
    assert COMMENT_TAG == "vitralis-release-v2"
    assert base64.b64decode(lines[1])[:2] == b"ED"


def test_an_independent_minisign_accepts_what_vitralis_writes():
    """The contract: anyone can check a download with minisign and the key the README publishes."""
    key = independent.PublicKey.from_base64(minisign_public(PUBLIC))
    signature = independent.Signature.from_bytes(TEXT.encode())
    key.verify(DATA, signature)
    with pytest.raises(independent.VerifyError):
        key.verify(DATA + b"!", signature)


def test_it_is_accepted_for_its_own_comment_bytes_and_key():
    key, parsed = accept((PUBLIC,), TEXT, COMMENT)
    check_file(key, parsed, hash_bytes(DATA).blake2b)
    with pytest.raises(NotSigned):
        check_file(key, parsed, hash_bytes(DATA + b"!").blake2b)


@pytest.mark.parametrize(
    "comment",
    [
        trusted_comment("1.3.0", ASSET, hash_bytes(DATA).blake3),
        trusted_comment("1.4.0", "vitralis-1.4.0-windows-x86_64-setup.exe", hash_bytes(DATA).blake3),
        trusted_comment("1.4.0", ASSET, "0" * 64),
    ],
)
def test_another_version_file_or_hash_is_refused(comment):
    with pytest.raises(NotSigned):
        accept((PUBLIC,), TEXT, comment)


def test_the_hash_case_doesnt_matter():
    assert trusted_comment("1.4.0", ASSET, hash_bytes(DATA).blake3.upper()) == COMMENT


def test_either_trusted_key_is_enough_and_a_stranger_s_is_refused():
    accept((public_key(OTHER_SECRET), PUBLIC), TEXT, COMMENT)
    accept((PUBLIC, public_key(OTHER_SECRET)), TEXT, COMMENT)
    with pytest.raises(NotSigned, match="trusts"):
        accept((public_key(OTHER_SECRET),), TEXT, COMMENT)  # also a key rotated out


def test_an_unreadable_key_among_good_ones_hides_neither_a_match_nor_a_refusal():
    accept(("not a key", PUBLIC), TEXT, COMMENT)
    with pytest.raises(NotSigned):
        accept(("not a key", public_key(OTHER_SECRET)), TEXT, COMMENT)
    with pytest.raises(UnreadableKey):
        accept(("not a key",), TEXT, COMMENT)


def test_a_changed_key_id_is_refused():
    raw = base64.b64decode(TEXT.splitlines()[1])
    changed = raw[:2] + bytes(8) + raw[10:]
    with pytest.raises(NotSigned):
        accept((PUBLIC,), replace_line(TEXT, 1, base64.b64encode(changed).decode()), COMMENT)


def test_the_untrusted_comment_and_crlf_change_nothing():
    text = replace_line(TEXT, 0, "untrusted comment: anything at all").replace("\n", "\r\n")
    accept((PUBLIC,), text, COMMENT)


def test_parts_of_two_genuine_files_cant_be_mixed():
    other = minisig(b"other", SECRET, "1.4.0", ASSET)
    mixed = replace_line(TEXT, 1, other.splitlines()[1])  # the other file's first signature, this file's comment
    with pytest.raises(NotSigned):
        accept((PUBLIC,), mixed, COMMENT)


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("", "fewer than four lines"),
        ("a\nb\nc\n", "fewer than four lines"),
        (replace_line(TEXT, 0, "comment: x"), "untrusted comment"),
        (replace_line(TEXT, 2, "comment: x"), "trusted comment"),
        (replace_line(TEXT, 1, "not base64!"), "the signature isn't base64"),
        (replace_line(TEXT, 1, base64.b64encode(b"ED" + bytes(40)).decode()), "prehashed Ed25519"),
        (replace_line(TEXT, 1, base64.b64encode(b"Ed" + bytes(72)).decode()), "legacy mode"),
        (replace_line(TEXT, 3, "not base64!"), "comment's signature isn't base64"),
        (replace_line(TEXT, 3, base64.b64encode(bytes(10)).decode()), "isn't 64 bytes"),
        ("ab" * 64 + "\n", "fewer than four lines"),  # the older hex format
    ],
)
def test_a_file_that_isnt_a_prehashed_minisign_signature_is_named(text, said):
    with pytest.raises(UnreadableSignature, match=said):
        parse(text)
    with pytest.raises(UnreadableSignature):
        accept((PUBLIC,), text, COMMENT)


def test_a_trusted_comment_is_one_line():
    with pytest.raises(ValueError, match="one line"):
        sign(SECRET, hash_bytes(DATA).blake2b, COMMENT + "\nmore")


@pytest.mark.property
@given(st.integers(min_value=0), st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/x"))
def test_changing_any_signed_character_fails(position, character):
    lines = TEXT.splitlines()
    signed_part = "\n".join(lines[1:])
    index = position % len(signed_part)
    if signed_part[index] in "\n" or signed_part[index] == character:
        return
    changed = lines[0] + "\n" + signed_part[:index] + character + signed_part[index + 1 :] + "\n"
    try:
        key, parsed = accept((PUBLIC,), changed, COMMENT)
    except (NotSigned, UnreadableSignature):
        return
    with pytest.raises(NotSigned):  # only a change the base64 can't see may get this far, and the bytes then fail
        check_file(key, parsed, hash_bytes(DATA).blake2b)
        if parsed == parse(TEXT):
            raise NotSigned("the same signature, written differently")
