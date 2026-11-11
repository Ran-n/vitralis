#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:58.118340
Revised: 2026/11/11 11:06:54.413147

A Clavren server in memory, signing real Ed25519 tokens, and a licence wired to it: what the use case, the UI
and the window tests run against.
"""

import datetime as dt
import json
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vitralis.licence.client import Licence, LicenceConfig
from vitralis.licence.crypto import Ed25519Crypto
from vitralis.licence.ports import LicenceStoreError, ServerAnswer, ServerUnreachable
from vitralis.licence.rules import b64decode, b64encode, check_message

START = dt.datetime(2026, 10, 4, 10, 0, tzinfo=dt.UTC)
"""Where every test clock starts."""


class FakeClock:
    def __init__(self, start: dt.datetime) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += dt.timedelta(**kwargs)


PRODUCT = "vitralis"
KEY = "BRN-79YN-44XQ-W025-377Z"
CANONICAL = "BRN79YN44XQW025377Z"
OTHER_KEY = "BRN-H1J5-S2M3-Q26T-T90E"
TOKEN_DAYS = 30


@dataclass
class FakeLicenceRecord:
    test: bool = False
    expires_at: dt.datetime | None = None
    revoked: bool = False
    device: str | None = None
    """The device public key (base64url) it is bound to; a test licence binds none."""


class FakeClavren:
    """``/api/v1/activations``, challenges and checks, as Clavren answers them. ``down`` makes every call fail
    to connect; ``answer`` (status, body) overrides the next answer."""

    def __init__(self, clock, kid: str = "test") -> None:
        self.clock = clock
        self.kid = kid
        self.signing = Ed25519PrivateKey.generate()
        self.licences: dict[str, FakeLicenceRecord] = {CANONICAL: FakeLicenceRecord()}
        self.activations: dict[str, tuple[str, str]] = {}
        """Activation ID → (licence key, device public key)."""
        self.challenges: dict[str, tuple[str, str]] = {}
        """Challenge ID → (activation, nonce)."""
        self.product_active = True
        self.down = False
        self.answers: list[tuple[int, Any, int | None]] = []
        self.calls: list[tuple[str, dict]] = []
        self.issued_offset = dt.timedelta(0)
        """How far the server's clock is ahead of the computer's."""

    @property
    def public_key(self) -> str:
        return b64encode(self.signing.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    def crypto(self) -> Ed25519Crypto:
        return Ed25519Crypto({self.kid: self.public_key})

    def post(self, path: str, body: dict[str, Any]) -> ServerAnswer:
        self.calls.append((path, body))
        if self.down:
            raise ServerUnreachable("connection refused")
        if self.answers:
            status, answer, retry = self.answers.pop(0)
            return ServerAnswer(status, answer, retry)
        parts = path.strip("/").split("/")
        if parts == ["api", "v1", "activations"]:
            return self._activate(body)
        if len(parts) == 5 and parts[4] == "challenges":
            return self._challenge(parts[3])
        if len(parts) == 5 and parts[4] == "checks":
            return self._check(parts[3], body)
        return ServerAnswer(404, None)

    def now(self) -> dt.datetime:
        return self.clock() + self.issued_offset

    def _error(self, status: int, code: str) -> ServerAnswer:
        return ServerAnswer(status, {"error": code, "message": code, "server_time": self.now().isoformat()})

    def _refusal(self, record: FakeLicenceRecord) -> ServerAnswer | None:
        if not self.product_active:
            return self._error(403, "product_unavailable")
        if record.revoked:
            return self._error(403, "licence_revoked")
        if record.expires_at is not None and record.expires_at <= self.now():
            return self._error(403, "licence_expired")
        return None

    def _activate(self, body: dict) -> ServerAnswer:
        record = self.licences.get(body["key"]) if body.get("product") == PRODUCT else None
        if record is None:
            return self._error(404, "invalid_key")
        if (refused := self._refusal(record)) is not None:
            return refused
        device = body["device_public_key"]
        if not record.test:
            if record.device not in (None, device):
                return self._error(409, "already_activated")
            record.device = device
        existing = next((a for a, (k, d) in self.activations.items() if k == body["key"] and d == device), None)
        activation = existing or _uuid()
        self.activations[activation] = (body["key"], device)
        return ServerAnswer(201 if existing is None else 200, self._token_answer(activation))

    def _challenge(self, activation: str) -> ServerAnswer:
        if activation not in self.activations:
            return self._error(403, "activation_revoked")
        challenge, nonce = _uuid(), b64encode(secrets.token_bytes(32))
        self.challenges[challenge] = (activation, nonce)
        return ServerAnswer(200, {"challenge": challenge, "nonce": nonce, "expires_at": "", "server_time": ""})

    def _check(self, activation: str, body: dict) -> ServerAnswer:
        expected = self.challenges.pop(body.get("challenge", ""), None)
        if activation not in self.activations or expected != (activation, body.get("nonce")):
            return self._error(401, "challenge_invalid")
        key, device = self.activations[activation]
        message = check_message(activation, body["challenge"], b64decode(body["nonce"])).encode()
        try:
            Ed25519PublicKey.from_public_bytes(b64decode(device)).verify(b64decode(body["signature"]), message)
        except (InvalidSignature, ValueError):
            return self._error(401, "challenge_invalid")
        if (refused := self._refusal(self.licences[key])) is not None:
            return refused
        return ServerAnswer(200, self._token_answer(activation))

    def reset(self, key: str = CANONICAL) -> None:
        """The seller frees the key: its activations end."""
        self.licences[key].device = None
        for activation in [a for a, (k, _) in self.activations.items() if k == key]:
            del self.activations[activation]

    def _token_answer(self, activation: str) -> dict:
        key, device = self.activations[activation]
        record = self.licences[key]
        issued = int(self.now().timestamp())
        expires = issued + TOKEN_DAYS * 86400
        if record.expires_at is not None:
            expires = min(expires, int(record.expires_at.timestamp()))
        claims = {
            "iss": "https://clavren.test",
            "aud": PRODUCT,
            "sub": _uuid(),
            "act": activation,
            "dev": self.crypto().device_hash(b64decode(device)),
            "iat": issued,
            "exp": expires,
            "jti": _uuid(),
        }
        if record.expires_at is not None:
            claims["lic_exp"] = int(record.expires_at.timestamp())
        if record.test:
            claims["test"] = True
        return {
            "activation": activation,
            "token": self.sign(claims),
            "token_expires_at": "",
            "licence_expires_at": None,
            "server_time": self.now().isoformat(),
        }

    def sign(self, claims: dict, kid: str | None = None, key: Ed25519PrivateKey | None = None) -> str:
        header = b64encode(json.dumps({"alg": "EdDSA", "typ": "JWT", "kid": kid or self.kid}).encode())
        payload = b64encode(json.dumps(claims).encode())
        signature = (key or self.signing).sign(f"{header}.{payload}".encode())
        return f"{header}.{payload}.{b64encode(signature)}"


class MemoryLicenceStore:
    """The saved state in memory; ``fail_saves``/``fail_load`` raise the store's errors."""

    def __init__(self, data: bytes | None = None) -> None:
        self.data = data
        self.saves = 0
        self.fail_saves = False
        self.fail_load: Exception | None = None

    def load(self) -> bytes | None:
        if self.fail_load is not None:
            raise self.fail_load
        return self.data

    def save(self, data: bytes) -> None:
        if self.fail_saves:
            raise LicenceStoreError("disk full")
        self.data = data
        self.saves += 1


def licence_config(**changes) -> LicenceConfig:
    values = {"product": PRODUCT, "app_version": "0.0.0-test", "device_name": "TEST-PC", "platform": "windows-x86_64"}
    return LicenceConfig(**{**values, **changes})


def make_licence(clock, server: FakeClavren | None = None, store: MemoryLicenceStore | None = None) -> Licence:
    server = server or FakeClavren(clock)
    return Licence(licence_config(), store or MemoryLicenceStore(), server, server.crypto(), clock)


def licensed(clock) -> Licence:
    """A licence already activated on this computer, as on every start after the first."""
    licence = make_licence(clock)
    assert licence.activate(KEY).licensed
    return licence


def _uuid() -> str:
    return str(uuid.uuid4())
