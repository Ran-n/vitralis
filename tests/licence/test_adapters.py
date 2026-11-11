#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:59.311762
Revised: 2026/11/11 11:06:54.488859

The Clavren adapters: Ed25519 tokens checked against the trusted keys, the licence file protected with the
real Windows DPAPI, and the HTTPS API (through respx).
"""

import json
import sys

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from tests.licence.fakes import START, FakeClavren, FakeClock
from vitralis.licence.crypto import TRUSTED_KEYS, Ed25519Crypto
from vitralis.licence.ports import (
    LicenceStoreError,
    LicenceStoreUnreadable,
    ServerUnreachable,
    TokenError,
)
from vitralis.licence.rules import b64encode
from vitralis.licence.server import LICENCE_SERVER, USER_AGENT, HttpLicenceServer
from vitralis.licence.store import DpapiProtector, FileLicenceStore

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")

NOW = int(START.timestamp())
CLAIMS = {"aud": "vitralis", "act": "a", "dev": "d", "iat": NOW, "exp": NOW + 100, "sub": "s", "jti": "j"}


@pytest.fixture
def clavren():
    return FakeClavren(FakeClock(START))


# --- crypto ------------------------------------------------------------------------------------------------


def test_the_device_hash_matches_clavrens_vector():
    assert Ed25519Crypto().device_hash(bytes(32)) == "KtqDwYGaU3La4SOPwd7RI8gQT9qhWGKq7mlCihgg_No"


def test_the_shipped_keys_are_the_servers_v1_and_v2():
    assert set(TRUSTED_KEYS) == {"v1", "v2"}
    Ed25519Crypto()  # every one is a valid key


@pytest.mark.parametrize("text", ["short", "A" * 44 + "=", b64encode(bytes(31))])
def test_a_trusted_key_that_isnt_one_is_refused(text):
    with pytest.raises(ValueError, match="trusted key v1"):
        Ed25519Crypto({"v1": text})


def test_a_signature_made_with_the_device_key_verifies():
    crypto = Ed25519Crypto()
    seed = crypto.new_device_key()
    assert len(seed) == 32 and seed != crypto.new_device_key()
    public = crypto.public_key(seed)
    signature = crypto.sign(seed, b"message")
    Ed25519PublicKey.from_public_bytes(public).verify(signature, b"message")
    assert len(public) == 32 and len(signature) == 64


def test_a_good_token_gives_its_claims(clavren):
    claims = clavren.crypto().verify_token(clavren.sign({**CLAIMS, "test": True}), "vitralis", NOW)
    assert claims.act == "a" and claims.test is True


def _with_header(clavren, header: dict) -> str:
    _, payload, _ = clavren.sign(CLAIMS).split(".")
    part = b64encode(json.dumps(header).encode())
    signature = clavren.signing.sign(f"{part}.{payload}".encode())
    return f"{part}.{payload}.{b64encode(signature)}"


@pytest.mark.parametrize(
    ("make", "reason"),
    [
        (lambda c: "a.b", "malformed"),
        (lambda c: "!!.b.c", "malformed"),
        (lambda c: _with_header(c, {"alg": "HS256", "typ": "JWT", "kid": "test"}), "malformed"),
        (lambda c: _with_header(c, {"alg": "EdDSA", "typ": "JWS", "kid": "test"}), "malformed"),
        (lambda c: _with_header(c, {"alg": "EdDSA", "typ": "JWT", "kid": "v1"}), "doesn't trust"),
        (lambda c: c.sign(CLAIMS).rsplit(".", 1)[0] + ".AAAA", "malformed"),
        (lambda c: c.sign(CLAIMS, key=Ed25519PrivateKey.generate()), "signature is wrong"),
        (lambda c: c.sign({**CLAIMS, "aud": "avalio-lite"}), "another product"),
        (lambda c: c.sign({**CLAIMS, "exp": NOW}), "expired"),
        (lambda c: c.sign({**CLAIMS, "iat": "now"}), "malformed"),
    ],
)
def test_a_token_the_app_cant_run_on_is_refused(clavren, make, reason):
    with pytest.raises(TokenError, match=reason):
        clavren.crypto().verify_token(make(clavren), "vitralis", NOW)


# --- the licence file ----------------------------------------------------------------------------------------


def _reversing(path):
    return FileLicenceStore(path, lambda data: data[::-1], lambda data: data[::-1])


def test_nothing_saved_is_none(tmp_path):
    assert _reversing(tmp_path / "licence.dat").load() is None


def test_only_protected_bytes_reach_the_disk_and_they_read_back(tmp_path):
    path = tmp_path / "sub" / "licence.dat"
    store = _reversing(path)
    store.save(b"secret")
    assert path.read_bytes() == b"terces"
    assert store.load() == b"secret"
    store.save(b"newer")
    assert store.load() == b"newer"
    assert [p.name for p in path.parent.iterdir()] == ["licence.dat"], "no temporary file left behind"


def test_a_failed_write_leaves_no_temporary_file_and_the_old_one_whole(tmp_path, monkeypatch):
    path = tmp_path / "licence.dat"
    store = _reversing(path)
    store.save(b"old")
    monkeypatch.setattr("vitralis.licence.store.os.replace", _fail)
    with pytest.raises(LicenceStoreError, match="can't be saved"):
        store.save(b"new")
    assert [p.name for p in tmp_path.iterdir()] == ["licence.dat"]
    assert store.load() == b"old"


def _fail(*_args):
    raise PermissionError("denied")


def test_a_file_that_cant_be_read_is_unreadable_not_missing(tmp_path):
    (tmp_path / "licence.dat").mkdir()  # reading a folder fails like a file held open
    with pytest.raises(LicenceStoreUnreadable, match="licence.dat"):
        _reversing(tmp_path / "licence.dat").load()


def test_a_file_that_cant_be_unprotected_is_an_error(tmp_path):
    def refuse(_data):
        raise OSError(13, "the data is invalid")

    path = tmp_path / "licence.dat"
    path.write_bytes(b"x")
    with pytest.raises(LicenceStoreError, match="can't be unprotected"):
        FileLicenceStore(path, refuse, refuse).load()


@windows_only
def test_dpapi_protects_for_this_account_and_this_product_only(tmp_path):
    path = tmp_path / "licence.dat"
    store = FileLicenceStore.for_windows(path, "vitralis")
    store.save(b'{"device_key": "secret"}')
    assert b"secret" not in path.read_bytes()
    assert store.load() == b'{"device_key": "secret"}'
    with pytest.raises(LicenceStoreError):
        FileLicenceStore.for_windows(path, "avalio-lite").load()


@windows_only
def test_damaged_protected_data_is_refused():
    with pytest.raises(OSError):
        DpapiProtector("vitralis").unprotect(b"not dpapi")


def test_the_store_needs_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("vitralis.licence.store.sys.platform", "linux")
    with pytest.raises(RuntimeError, match="Windows"):
        FileLicenceStore.for_windows(tmp_path / "licence.dat", "vitralis")


# --- the HTTPS API ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://clavren.breren.com", "ftp://clavren.breren.com", "http://192.0.2.10:8080", "clavren"]
)
def test_a_server_not_over_https_is_refused(url):
    with pytest.raises(ValueError, match="HTTPS"):
        HttpLicenceServer(httpx.Client(), url)


@pytest.mark.parametrize("url", ["http://localhost:8080", "http://127.0.0.1:8080/", "http://[::1]:8080"])
def test_this_computer_may_be_plain_http(url):
    HttpLicenceServer(httpx.Client(), url)


@respx.mock
def test_a_post_sends_json_and_reads_the_answer():
    route = respx.post(f"{LICENCE_SERVER}/api/v1/activations").mock(
        return_value=httpx.Response(201, json={"activation": "a", "token": "t"})
    )
    with httpx.Client() as http:
        answer = HttpLicenceServer(http).post("/api/v1/activations", {"key": "K"})
    assert (answer.status, answer.body, answer.retry_after) == (201, {"activation": "a", "token": "t"}, None)
    sent = route.calls.last.request
    assert json.loads(sent.content) == {"key": "K"}
    assert sent.headers["User-Agent"] == USER_AGENT


@respx.mock
def test_retry_after_is_read_in_seconds():
    respx.post(f"{LICENCE_SERVER}/x").mock(
        return_value=httpx.Response(429, json={"error": "rate_limited"}, headers={"Retry-After": "90"})
    )
    respx.post(f"{LICENCE_SERVER}/y").mock(return_value=httpx.Response(429, headers={"Retry-After": "soon"}))
    with httpx.Client() as http:
        server = HttpLicenceServer(http)
        assert server.post("/x", {}).retry_after == 90
        assert server.post("/y", {}).retry_after is None


@respx.mock
@pytest.mark.parametrize("response", [httpx.Response(200, text="<html>proxy</html>"), httpx.Response(200, json=[1])])
def test_a_body_that_isnt_a_json_object_is_none(response):
    respx.post(f"{LICENCE_SERVER}/x").mock(return_value=response)
    with httpx.Client() as http:
        assert HttpLicenceServer(http).post("/x", {}).body is None


@respx.mock
@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_no_answer_is_unreachable(error):
    respx.post(f"{LICENCE_SERVER}/x").mock(side_effect=error)
    with httpx.Client() as http, pytest.raises(ServerUnreachable, match="clavren.breren.com"):
        HttpLicenceServer(http).post("/x", {})
