#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/21 18:28:52.241517
Revised: 2026/11/21 18:28:52.241517

Release keys: the built-in keys are two distinct real keys, published in the README in minisign's form; a key's ID
is the first 8 bytes of its BLAKE3 hash; a generated key's public half is what signs; a secret that isn't one is
named; and only a copy run from source may trust a test key.
"""

import base64
import re
from pathlib import Path

import pytest
from blake3 import blake3

from tests.updates.fakes import PUBLIC, SECRET, minisig
from vitralis.sign import main as sign_main
from vitralis.updates.rules import NotSigned
from vitralis.updates.signature import (
    RELEASE_KEYS,
    UnreadableKey,
    generate,
    key_id,
    minisign_public,
    public_key,
    release_keys,
)
from vitralis.updates.signature.minisign import accept, trusted_comment

README = Path(__file__).parents[2] / "README.md"


def test_a_key_id_is_the_start_of_the_key_s_blake3_hash():
    public = bytes.fromhex(PUBLIC)
    assert key_id(public) == blake3(public).digest()[:8]


def test_a_public_key_in_minisign_s_form_is_ed_the_id_and_the_key():
    text = minisign_public(PUBLIC)
    raw = base64.b64decode(text)
    assert len(text) == 56 and text.startswith("RW")
    assert raw == b"Ed" + key_id(bytes.fromhex(PUBLIC)) + bytes.fromhex(PUBLIC)


def test_the_built_in_keys_are_two_distinct_real_keys():
    assert len(RELEASE_KEYS) == 2 and RELEASE_KEYS[0] != RELEASE_KEYS[1]
    text = minisig(b"x", SECRET, "1.4.0", "a.exe")
    for key in RELEASE_KEYS:
        assert len(key) == 64 and key == key.lower() and int(key, 16) != 0
        with pytest.raises(NotSigned):  # a real point on the curve: it reads, and refuses a stranger's signature
            accept((key,), text, trusted_comment("1.4.0", "a.exe", blake3(b"x").hexdigest()))
    assert PUBLIC not in RELEASE_KEYS


def test_the_readme_publishes_the_built_in_keys_signing_key_first(capsys):
    """Anyone checking a download by hand takes the keys from the README: they can't drift from the app's."""
    assert sign_main(["keys"]) == 0
    printed = capsys.readouterr().out.split()
    published = list(dict.fromkeys(re.findall(r"RW[A-Za-z0-9+/]{54}", README.read_text(encoding="utf-8"))))
    assert printed == [minisign_public(key) for key in RELEASE_KEYS]
    assert published == printed  # every key the README shows is a built-in one, in order


def test_a_copy_run_from_source_may_trust_a_test_key(monkeypatch):
    assert release_keys() == RELEASE_KEYS
    monkeypatch.setenv("VITRALIS_UPDATE_KEY", PUBLIC)
    assert release_keys() == (PUBLIC,)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert release_keys() == RELEASE_KEYS  # the packaged exe ignores every override


def test_a_generated_key_is_new_each_time_and_its_public_half_signs():
    secret = generate()
    assert len(secret) == 64 and secret != generate()
    text = minisig(b"x", secret, "1.4.0", "a.exe")
    key, _ = accept((public_key(secret),), text, trusted_comment("1.4.0", "a.exe", blake3(b"x").hexdigest()))
    assert key == public_key(secret)


def test_a_secret_that_isnt_one_is_named():
    with pytest.raises(UnreadableKey, match="the secret key"):
        public_key("nope")
    with pytest.raises(UnreadableKey):
        public_key("ab" * 31)
    with pytest.raises(UnreadableKey, match="the release key"):
        minisign_public("z" * 64)
