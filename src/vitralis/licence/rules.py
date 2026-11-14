#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:55.657748
Revised: 2026/11/14 12:01:47.357225

The rules of a Clavren licence, without any I/O: how a typed key is read, what the device signs on each
check, what the app knows about its licence (``LicenceState``) and what it may do with it (``LicenceStatus``).

The same protocol as the Rust ``clavren-client`` crate (``../clavren/crates/clavren-client``); its test vectors
(``../clavren/docs/api.md``, "Test vectors") pin this implementation too.
"""

import base64
import binascii
import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Self

KEY_PREFIX = "BRN"
KEY_BODY_LENGTH = 16
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford's base 32: no I, L, O or U, so a key read aloud or copied by hand can't be misread."""
CHECK_MESSAGE_VERSION = "clavren-check-v1"
NONCE_LENGTH = 32
ROLLBACK_TOLERANCE = dt.timedelta(hours=1)
"""A clock more than this behind the latest time seen, or set back more than this in all since the last check
(many small steps count together), counts as set back: the saved licence isn't trusted until an online check."""
REDACTED = "<redacted>"
"""What stands for a secret wherever a state is shown."""


def normalize_key(typed: str) -> str | None:
    """The canonical form of a typed key (``BRN`` and 16 symbols), or ``None`` when it can't be one.

    Case, spaces, tabs and dashes don't matter; ``I``/``L`` read as ``1`` and ``O`` as ``0``."""
    symbols = []
    for character in typed:
        if character in " -\t":
            continue
        upper = character.upper()
        if upper in "IL":
            upper = "1"
        elif upper == "O":
            upper = "0"
        if len(upper) != 1 or upper not in CROCKFORD:
            return None
        symbols.append(upper)
    key = "".join(symbols)
    if not key.startswith(KEY_PREFIX) or len(key) - len(KEY_PREFIX) != KEY_BODY_LENGTH:
        return None
    return key


def format_key(canonical: str) -> str:
    """``BRN79YN44XQW025377Z`` → ``BRN-79YN-44XQ-W025-377Z``."""
    body = canonical[len(KEY_PREFIX) :]
    return "-".join([KEY_PREFIX, *(body[at : at + 4] for at in range(0, len(body), 4))])


def b64encode(data: bytes) -> str:
    """Unpadded base64url, as every binary value in the protocol."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64decode(text: str) -> bytes | None:
    """The bytes of unpadded base64url ``text``; ``None`` when it isn't (padding included)."""
    if "=" in text or len(text) % 4 == 1:
        return None
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None


def check_message(activation: str, challenge: str, nonce: bytes) -> str:
    """What the device signs to prove it holds its key: four lines, no trailing newline."""
    return f"{CHECK_MESSAGE_VERSION}\n{activation}\n{challenge}\n{b64encode(nonce)}"


class LicenceKind(StrEnum):
    LICENSED = "licensed"
    NEEDS_ACTIVATION = "needs_activation"
    """No licence on this computer yet: ask for a key."""
    INVALID_KEY = "invalid_key"
    """Malformed, unknown, or another product's key: ask again."""
    ALREADY_ACTIVATED_ELSEWHERE = "already_activated_elsewhere"
    """In use on another computer: say how to ask for a reset."""
    REVOKED = "revoked"
    """Revoked, or this computer was reset: locked; a new key can be entered."""
    EXPIRED = "expired"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    NEEDS_CHECK = "needs_check"
    """30 days offline, or the clock was set back: ask to connect."""
    RATE_LIMITED = "rate_limited"
    UNREACHABLE = "unreachable"
    """Activating needs the licence server, which can't be reached."""
    SERVER_ERROR = "server_error"
    """The server answered, but nothing the app can use (an error of its own, a proxy's page)."""


@dataclass(frozen=True, slots=True)
class LicenceStatus:
    """What the app may do with its licence. Only ``LICENSED`` lets it run."""

    kind: LicenceKind
    licence_expires_at: dt.datetime | None = None
    """When a licence that isn't permanent ends (``LICENSED``), or ended (``EXPIRED``, when known)."""
    offline_until: dt.datetime | None = None
    """When the saved licence runs out without an online check (``LICENSED``)."""
    test: bool = False
    """A test licence (``LICENSED``): for trying the app on any number of computers, not a sale."""
    retry_after: dt.timedelta | None = None
    """How long to wait (``RATE_LIMITED``)."""

    @property
    def licensed(self) -> bool:
        return self.kind is LicenceKind.LICENSED


class Refusal(StrEnum):
    """A definitive answer from the server, kept until a new activation succeeds."""

    REVOKED = "revoked"
    EXPIRED = "expired"
    PRODUCT_UNAVAILABLE = "product_unavailable"


REFUSAL_KINDS = {
    Refusal.REVOKED: LicenceKind.REVOKED,
    Refusal.EXPIRED: LicenceKind.EXPIRED,
    Refusal.PRODUCT_UNAVAILABLE: LicenceKind.PRODUCT_UNAVAILABLE,
}


@dataclass(frozen=True, slots=True)
class Claims:
    """A licence token's claims (``../clavren/docs/api.md``, "Tokens")."""

    aud: str
    """The product code."""
    act: str
    """The activation ID."""
    dev: str
    """base64url of the BLAKE3 hash of the device public key."""
    iat: int
    exp: int
    lic_exp: int | None = None
    test: bool = False


def unverified_claims(token: str) -> Claims | None:
    """The claims a token carries, without checking its signature; ``None`` when it isn't a token.

    Only for what a trusted check doesn't need: the server's time (``iat``) before verifying, and the expiry
    of a licence the server just said has expired."""
    parts = token.split(".")
    if len(parts) != 3 or (raw := b64decode(parts[1])) is None:
        return None
    try:
        data = json.loads(raw)
        return Claims(
            aud=str(data["aud"]),
            act=str(data["act"]),
            dev=str(data["dev"]),
            iat=_integer(data["iat"]),
            exp=_integer(data["exp"]),
            lic_exp=None if data.get("lic_exp") is None else _integer(data["lic_exp"]),
            test=data.get("test", False) is True,
        )
    except (ValueError, TypeError, KeyError):
        return None


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"not an integer: {value!r}")
    return value


def from_timestamp(seconds: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(seconds, dt.UTC)


@dataclass(slots=True)
class LicenceState:
    """Everything the app keeps about its licence, saved protected for this Windows account.

    Times are the system clock's, so a computer whose clock is simply wrong still works; tokens are judged by
    the server's time (``server_now``)."""

    device_key: str | None = None
    """The Ed25519 private key's 32-byte seed, base64url."""
    activation: str | None = None
    token: str | None = None
    latest_seen: dt.datetime | None = None
    """The latest time the system clock showed."""
    last_seen: dt.datetime | None = None
    """The previous time it showed, to add up how far it is set back."""
    rewound_seconds: int = 0
    """How far the clock was set back in all since the last successful check: many small steps back count like
    one big one."""
    clock_offset_seconds: int = 0
    """Server time minus system-clock time at the last successful answer."""
    last_check: dt.datetime | None = None
    refusal: Refusal | None = None
    refusal_at: dt.datetime | None = field(default=None)
    """When an expired licence ended, when the last token said so."""

    def __repr__(self) -> str:
        """Never shows the device key or the token."""
        hidden = {
            "device_key": REDACTED if self.device_key else None,
            "token": REDACTED if self.token else None,
        }
        shown = {name: value for name, value in asdict(self).items() if name not in hidden}
        return f"LicenceState({', '.join(f'{k}={v!r}' for k, v in {**hidden, **shown}.items())})"

    def copy(self) -> Self:
        return type(self)(**{name: getattr(self, name) for name in self.__slots__})

    def saw(self, time: dt.datetime) -> None:
        """Record a time the clock showed: a step back adds to ``rewound_seconds``; the latest only moves forward."""
        self.rewound_seconds += self._step_back(time)
        self.last_seen = time
        self.latest_seen = time if self.latest_seen is None else max(self.latest_seen, time)

    def rewound_by(self, now: dt.datetime) -> int:
        """How far, in seconds, the clock was set back in all, counting ``now``."""
        return self.rewound_seconds + self._step_back(now)

    def _step_back(self, time: dt.datetime) -> int:
        if self.last_seen is None:
            return 0
        return max(0, int(self.last_seen.timestamp()) - int(time.timestamp()))

    def clock_set_back(self, now: dt.datetime) -> bool:
        """Whether ``now`` is too far behind what was seen before to trust the saved licence."""
        behind = self.latest_seen is not None and now < self.latest_seen - ROLLBACK_TOLERANCE
        return behind or self.rewound_by(now) > ROLLBACK_TOLERANCE.total_seconds()

    def server_now(self, now: dt.datetime) -> dt.datetime:
        """The time by the server's clock, from the system clock and the difference last measured."""
        try:
            return now + dt.timedelta(seconds=self.clock_offset_seconds)
        except OverflowError:  # a damaged offset counts as none
            return now

    def accept_clock(self, now: dt.datetime, issued_at: int) -> None:
        """After the server vouched for the licence, ``now`` is the baseline again and its distance from the
        server's clock is measured anew, from the token's signed issue time (never the answer's unsigned
        ``server_time``, which anything in between could change)."""
        self.last_check = self.latest_seen = self.last_seen = now
        self.rewound_seconds = 0
        self.clock_offset_seconds = issued_at - int(now.timestamp())

    def to_json(self) -> bytes:
        data = asdict(self)
        for name in ("latest_seen", "last_seen", "last_check", "refusal_at"):
            if data[name] is not None:
                data[name] = data[name].isoformat()
        return json.dumps(data, separators=(",", ":")).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> Self:
        """Raises ``ValueError`` when ``raw`` isn't a saved state."""
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError("not an object")
            known = {name: data[name] for name in cls.__slots__ if name in data}
            for name in ("device_key", "activation", "token"):
                if known.get(name) is not None and not isinstance(known[name], str):
                    raise TypeError(f"{name} is not text")
            for name in ("latest_seen", "last_seen", "last_check", "refusal_at"):
                if known.get(name) is not None:
                    known[name] = dt.datetime.fromisoformat(known[name])
                    if known[name].tzinfo is None:  # every saved time is UTC; one without a zone can't be compared
                        raise TypeError(f"{name} has no time zone")
            if known.get("refusal") is not None:
                known["refusal"] = Refusal(known["refusal"])
            for name in ("rewound_seconds", "clock_offset_seconds"):
                known[name] = _integer(known.get(name, 0))
            return cls(**known)
        except (TypeError, KeyError) as ex:
            raise ValueError(f"not a saved licence state: {ex}") from ex
