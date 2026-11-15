#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:50.920423
Revised: 2026/11/15 21:45:42.806133

Release signatures: a signature checks out only over its own statement (version, file name, hash) and with its
own key; either built-in key is enough; malformed keys and signatures are named; the built-in keys are real
keys, and distinct.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.updates.fakes import OTHER_SECRET, PUBLIC, SECRET
from vitralis.updates import signature
from vitralis.updates.rules import NotSigned
from vitralis.updates.signature import (
    RELEASE_KEYS,
    UnreadableKey,
    UnreadableSignature,
    generate,
    public_key,
    release_keys,
    sign,
    statement,
    verify,
    verify_any,
)

HASH = "AF1349B9F5F9A1A6A0404DEA36DCC9499BCB25C9ADC112B7CC9A93CAE41F3262"
ASSET = "vitralis-1.4.0-windows-x86_64-portable.exe"


def test_the_statement_is_four_lines_with_the_hash_lower_case():
    assert statement("1.4.0", ASSET, HASH) == (f"vitralis-release-v1\n1.4.0\n{ASSET}\n{HASH.lower()}\n".encode())


def test_a_signature_verifies_only_its_own_statement_and_key():
    signed = statement("1.4.0", ASSET, HASH)
    text = sign(SECRET, signed)
    assert len(text) == 129 and text.endswith("\n")
    verify(PUBLIC, signed, text)
    for other in (
        statement("1.3.0", ASSET, HASH),
        statement("1.4.0", "vitralis-1.4.0-windows-x86_64-setup.exe", HASH),
        statement("1.4.0", ASSET, "0" * 64),
    ):
        with pytest.raises(NotSigned):
            verify(PUBLIC, other, text)
    with pytest.raises(NotSigned):
        verify(public_key(OTHER_SECRET), signed, text)


def test_the_hash_case_doesnt_matter_and_the_signature_may_be_upper_case():
    text = sign(SECRET, statement("1.4.0", ASSET, HASH))
    verify(PUBLIC, statement("1.4.0", ASSET, HASH.lower()), text.upper())


@pytest.mark.parametrize("text", ["", "abc", "z" * 128, "a" * 127, "é" * 128, "a" * 130])
def test_a_signature_that_isnt_one_is_named(text):
    with pytest.raises(UnreadableSignature, match="the signature"):
        verify(PUBLIC, b"x", text)
    with pytest.raises(UnreadableSignature):
        verify_any((PUBLIC,), b"x", text)


@pytest.mark.parametrize("key", ["", "abc", "z" * 64])
def test_a_key_that_isnt_one_is_named(key):
    with pytest.raises(UnreadableKey, match="the release key"):
        verify(key, b"x", sign(SECRET, b"x"))


def test_either_trusted_key_is_enough():
    text = sign(SECRET, b"x")
    verify_any((public_key(OTHER_SECRET), PUBLIC), b"x", text)
    verify_any((PUBLIC, public_key(OTHER_SECRET)), b"x", text)


def test_an_unreadable_key_among_good_ones_hides_neither_a_match_nor_a_refusal():
    text = sign(SECRET, b"x")
    verify_any(("not a key", PUBLIC), b"x", text)
    with pytest.raises(NotSigned):
        verify_any(("not a key", public_key(OTHER_SECRET)), b"x", text)
    with pytest.raises(UnreadableKey):
        verify_any(("not a key",), b"x", text)


def test_a_key_rotated_out_stops_counting():
    text = sign(OTHER_SECRET, b"x")
    with pytest.raises(NotSigned, match="trusts"):
        verify_any((PUBLIC,), b"x", text)


def test_the_built_in_keys_are_two_distinct_real_keys():
    assert len(RELEASE_KEYS) == 2 and RELEASE_KEYS[0] != RELEASE_KEYS[1]
    for key in RELEASE_KEYS:
        assert len(key) == 64 and key == key.lower() and int(key, 16) != 0
        with pytest.raises(NotSigned):  # a real point on the curve: it reads, and refuses a stranger's signature
            verify(key, b"x", sign(SECRET, b"x"))
    assert PUBLIC not in RELEASE_KEYS


def test_a_copy_run_from_source_may_trust_a_test_key(monkeypatch):
    assert release_keys() == RELEASE_KEYS
    monkeypatch.setenv("VITRALIS_UPDATE_KEY", PUBLIC)
    assert release_keys() == (PUBLIC,)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert release_keys() == RELEASE_KEYS  # the packaged exe ignores every override


def test_a_generated_key_signs_what_its_public_half_verifies():
    secret = generate()
    assert len(secret) == 64 and secret != generate()
    verify(public_key(secret), b"x", sign(secret, b"x"))


def test_a_secret_that_isnt_one_is_named():
    with pytest.raises(UnreadableKey, match="the secret key"):
        sign("nope", b"x")
    with pytest.raises(UnreadableKey):
        public_key("ab" * 31)


@pytest.mark.property
@given(st.text(max_size=12), st.text(max_size=40), st.integers(0, 3), st.characters())
def test_changing_any_part_of_the_statement_fails(version, asset, part, extra):
    parts = ["1.4.0", ASSET, HASH.lower()]
    text = sign(SECRET, statement(*parts))
    changed = list(parts)
    if part < 3:
        changed[part] = changed[part] + (extra if extra else "x")
    else:
        changed = [version or "0", asset or "a", "0" * 64]
    if changed == parts:
        return
    with pytest.raises(NotSigned):
        verify(PUBLIC, statement(*changed), text)


def test_the_statement_names_the_app():
    assert signature.STATEMENT_TAG == "vitralis-release-v1"
