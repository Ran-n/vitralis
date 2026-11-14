#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:55.948032
Revised: 2026/11/14 12:01:47.159249

The app's licence from Clavren (``../clavren``): activating a key on this computer, running offline on the
saved licence for up to 30 days, and checking it online once a day.

A Python port of the Rust ``clavren-client`` crate, with the same behaviour:

- ``status()`` answers from the saved state without going online or touching the disk, fast enough for the UI.
- ``activate(key)`` binds the key to this computer's device key pair, made and saved before anything is sent.
- ``check()`` proves the device key over a one-time challenge and renews the token; a definitive refusal
  (revoked, reset, expired, withdrawn) is kept, anything else (``LicenceCheckFailed``) changes nothing.
- A clock set back by more than an hour, at once or a little at a time, needs an online check; tokens are
  judged by the server's time, measured from the signed token at the last check.

``LicenceChecks`` runs the daily check on a thread of its own and reports when the outcome's kind changes.
Keys, tokens and device keys are never logged.
"""

import datetime as dt
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from vitralis.licence.ports import (
    LicenceCrypto,
    LicenceServer,
    LicenceStore,
    LicenceStoreError,
    LicenceStoreUnreadable,
    ServerAnswer,
    ServerUnreachable,
    TokenError,
)
from vitralis.licence.rules import (
    NONCE_LENGTH,
    REFUSAL_KINDS,
    Claims,
    LicenceKind,
    LicenceState,
    LicenceStatus,
    Refusal,
    b64decode,
    b64encode,
    check_message,
    from_timestamp,
    normalize_key,
    unverified_claims,
)

logger = logging.getLogger("vitralis.licence.client")

type Clock = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


CHECK_INTERVAL = dt.timedelta(days=1)
SEEN_SAVE_STEP = dt.timedelta(minutes=10)
"""``save_time_seen`` saves the latest time seen once it moved this far: nothing next to the hour of tolerance."""
DEFAULT_RETRY_AFTER = 60
NOT_AGAIN = dt.timedelta(days=36500)
"""``time_until_due`` when no check will ever be due (no activation)."""


class LicenceCheckFailed(Exception):
    """An online check that couldn't decide anything (unreachable, rate limited, an unexpected answer, a state
    that couldn't be saved). While the saved token is valid it changes nothing; the checker retries later."""

    def __init__(
        self,
        reason: str,
        kind: LicenceKind = LicenceKind.SERVER_ERROR,
        retry_after: dt.timedelta | None = None,
        unsaved: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.kind = kind
        """What to tell the user: ``UNREACHABLE``, ``RATE_LIMITED`` or ``SERVER_ERROR``."""
        self.retry_after = retry_after
        self.unsaved = unsaved
        """Why the checked licence couldn't be saved, when that is what failed."""


@dataclass(frozen=True, slots=True)
class LicenceConfig:
    product: str
    """The product code in Clavren."""
    app_version: str
    device_name: str
    """Shown to the seller, e.g. the computer's name."""
    platform: str
    check_interval: dt.timedelta = CHECK_INTERVAL


class Licence:
    def __init__(
        self, config: LicenceConfig, store: LicenceStore, server: LicenceServer, crypto: LicenceCrypto, clock: Clock
    ) -> None:
        """Loads the saved state. State that is damaged or another Windows account's counts as none (the key is
        asked for again); state that exists but can't be read starts empty too, and is never overwritten."""
        self._config = config
        self._store = store
        self._server = server
        self._crypto = crypto
        self._clock = clock
        self._lock = threading.RLock()
        self._unreadable: str | None = None
        self._state = self._load()
        self._saved_latest, self._saved_rewound = self._state.latest_seen, self._state.rewound_seconds

    @property
    def unreadable(self) -> str | None:
        """Why the saved licence couldn't be read at start, when it exists but couldn't be; else ``None``."""
        return self._unreadable

    def _load(self) -> LicenceState:
        try:
            raw = self._store.load()
        except LicenceStoreUnreadable as ex:
            logger.error("the saved licence can't be read (%s); it won't be overwritten", ex)
            self._unreadable = str(ex)
            return LicenceState()
        except LicenceStoreError as ex:
            logger.warning("the saved licence can't be read (%s); starting over", ex)
            return LicenceState()
        if raw is None:
            return LicenceState()
        try:
            return LicenceState.from_json(raw)
        except ValueError as ex:
            logger.warning("the saved licence is damaged (%s); starting over", ex)
            return LicenceState()

    # --- offline ---------------------------------------------------------------------------------------------

    def status(self) -> LicenceStatus:
        """The licence as far as this computer knows. Every time seen counts, locked or not, so a clock set back
        while the app is locked can't be waited out; ``save_time_seen`` writes it down."""
        with self._lock:
            now = self._clock()
            outcome = self._offline(self._state, now)
            self._state.saw(now)
            return outcome

    def _offline(self, state: LicenceState, now: dt.datetime) -> LicenceStatus:
        if state.refusal is not None:
            return _refused(state)
        if state.token is None:
            kind = LicenceKind.NEEDS_CHECK if state.activation else LicenceKind.NEEDS_ACTIVATION
            return LicenceStatus(kind)
        if state.clock_set_back(now):
            logger.warning("the clock is behind the latest time seen; the licence must be checked online")
            return LicenceStatus(LicenceKind.NEEDS_CHECK)
        try:
            claims = self._usable_claims(state, state.token, state.server_now(now))
        except TokenError as ex:
            logger.info("the saved licence token can't be used: %s", ex)
            return LicenceStatus(LicenceKind.NEEDS_CHECK)
        return LicenceStatus(
            LicenceKind.LICENSED,
            licence_expires_at=None if claims.lic_exp is None else from_timestamp(claims.lic_exp),
            offline_until=from_timestamp(claims.exp),
            test=claims.test,
        )

    def _usable_claims(self, state: LicenceState, token: str, server_now: dt.datetime) -> Claims:
        claims = self._crypto.verify_token(token, self._config.product, int(server_now.timestamp()))
        public = self._public_key(state)
        if public is None or claims.dev != self._crypto.device_hash(public):
            raise TokenError("it belongs to another device")
        if claims.act != state.activation:
            raise TokenError("it belongs to another activation")
        return claims

    def server_time(self) -> dt.datetime:
        """The time by the licence server's clock, as last measured, for judging how near the token's end is."""
        with self._lock:
            return self._state.server_now(self._clock())

    def save_time_seen(self) -> None:
        """Save the latest time seen once it moved ``SEEN_SAVE_STEP`` past the saved one, and any step back, so a
        clock set back between runs is noticed too. Raises ``LicenceStoreError``."""
        with self._lock:
            latest, saved = self._state.latest_seen, self._saved_latest
            moved = latest is not None and (saved is None or latest - saved >= SEEN_SAVE_STEP)
            if moved or self._state.rewound_seconds != self._saved_rewound:
                self._save(self._state)

    def time_until_due(self) -> dt.timedelta:
        """How long until the next online check is due (zero when due now)."""
        with self._lock:
            now = self._clock()
            state = self._state
            if state.activation is None:  # none yet, or revoked for good: nothing to check
                return NOT_AGAIN
            settled = self._offline(state, now).licensed or state.refusal is not None
            if state.last_check is None or not settled:
                return dt.timedelta(0)
            # a refusal is an answer too: asked again at the usual pace, as an expiry may be extended
            return max(dt.timedelta(0), state.last_check + self._config.check_interval - now)

    def needs_check(self) -> bool:
        return self.time_until_due() == dt.timedelta(0)

    # --- online ----------------------------------------------------------------------------------------------

    def activate(self, typed_key: str) -> LicenceStatus:
        """Activate ``typed_key`` on this computer (on a worker thread: it goes to the server).

        Raises ``LicenceStoreError`` when the device key couldn't be saved (then nothing was sent) or when the
        accepted activation couldn't be saved; trying again is safe, as the server knows this device again."""
        key = normalize_key(typed_key)
        if key is None:
            return LicenceStatus(LicenceKind.INVALID_KEY)
        public = self._device_public_key()
        body = {
            "product": self._config.product,
            "key": key,
            "device_public_key": b64encode(public),
            "device_name": self._config.device_name[:200] or "computer",
            "platform": self._config.platform,
            "app_version": self._config.app_version,
        }
        try:
            answer = self._server.post("/api/v1/activations", body)
        except ServerUnreachable as ex:
            logger.warning("activation couldn't reach the licence server: %s", ex)
            return LicenceStatus(LicenceKind.UNREACHABLE)
        if answer.status in (200, 201):
            activation, token = _text(answer, "activation"), _text(answer, "token")
            if activation is None or token is None:
                logger.error("activation got HTTP %s without an activation and a token", answer.status)
                return LicenceStatus(LicenceKind.SERVER_ERROR)
            with self._lock:
                now = self._clock()
                activated = replace(
                    self._state.copy(), activation=activation, refusal=None, refusal_at=None, token=None
                )
                try:
                    self._accept_token(activated, token, now)
                except TokenError as ex:  # kept as activated: the next check asks again
                    logger.error("the activation's token can't be used: %s", ex)
                    activated.last_check = now
                self._save(activated)
                self._state = activated
            logger.info("licence activated")
            return self.status()
        return _activation_refused(answer)

    def check(self) -> LicenceStatus:
        """Ask the server whether the licence still holds and renew the token. A definitive answer is kept and
        returned; anything else raises ``LicenceCheckFailed`` and changes nothing."""
        with self._lock:
            activation, seed = self._state.activation, _seed(self._state)
        if activation is None or seed is None:
            return LicenceStatus(LicenceKind.NEEDS_ACTIVATION)
        challenge = self._post(f"/api/v1/activations/{activation}/challenges", {})
        if challenge.status != 200:
            return self._refused(activation, challenge)
        challenge_id, nonce_text = _text(challenge, "challenge"), _text(challenge, "nonce")
        nonce = None if nonce_text is None else b64decode(nonce_text)
        if challenge_id is None or nonce is None or len(nonce) != NONCE_LENGTH:
            raise LicenceCheckFailed("the challenge is malformed")
        signature = self._crypto.sign(seed, check_message(activation, challenge_id, nonce).encode())
        body = {
            "challenge": challenge_id,
            "nonce": nonce_text,
            "signature": b64encode(signature),
            "app_version": self._config.app_version,
        }
        answer = self._post(f"/api/v1/activations/{activation}/checks", body)
        if answer.status != 200:
            return self._refused(activation, answer)
        token = _text(answer, "token")
        if token is None:
            raise LicenceCheckFailed(f"HTTP {answer.status} without a token")
        with self._lock:
            if self._state.activation != activation:
                raise LicenceCheckFailed("the activation changed during the check")
            renewed = replace(self._state.copy(), refusal=None, refusal_at=None)
            try:
                self._accept_token(renewed, token, self._clock())
            except TokenError as ex:
                raise LicenceCheckFailed(f"the renewed token can't be used: {ex}") from ex
            self._save_for_check(renewed)
            self._state = renewed
        logger.info("licence checked")
        return self.status()

    def _post(self, path: str, body: dict[str, Any]) -> ServerAnswer:
        try:
            return self._server.post(path, body)
        except ServerUnreachable as ex:
            raise LicenceCheckFailed(f"the licence server couldn't be reached: {ex}", LicenceKind.UNREACHABLE) from ex

    def _refused(self, activation: str, answer: ServerAnswer) -> LicenceStatus:
        """Keep a definitive refusal; anything else is temporary."""
        code = _error_code(answer)
        if code in ("licence_revoked", "activation_revoked"):
            refusal = Refusal.REVOKED
        elif code == "licence_expired":
            refusal = Refusal.EXPIRED
        elif code == "product_unavailable":
            refusal = Refusal.PRODUCT_UNAVAILABLE
        elif code == "rate_limited":
            raise LicenceCheckFailed("the licence server asked to wait", LicenceKind.RATE_LIMITED, _retry_after(answer))
        else:
            raise LicenceCheckFailed(f"HTTP {answer.status} ({code})")
        with self._lock:
            if self._state.activation != activation:  # a new activation happened meanwhile
                raise LicenceCheckFailed("the activation changed during the check")
            refused = self._state.copy()
            if refusal is Refusal.EXPIRED:
                claims = None if refused.token is None else unverified_claims(refused.token)
                refused.refusal_at = (
                    None if claims is None or claims.lic_exp is None else from_timestamp(claims.lic_exp)
                )
            refused.token = None
            refused.refusal = refusal
            refused.last_check = self._clock()
            if refusal is Refusal.REVOKED:  # over for good; a new key (or the same one, after a reset) starts afresh
                refused.activation = None
            self._save_for_check(refused)
            self._state = refused
        logger.warning("the licence server refused the licence: %s", refusal)
        return _refused(refused)

    def _accept_token(self, state: LicenceState, token: str, now: dt.datetime) -> None:
        """Take ``token`` into ``state`` with the clock measured anew; leave ``state`` as it was when it can't
        be run on (raises ``TokenError``)."""
        claims = unverified_claims(token)
        if claims is None:
            raise TokenError("it is not a token")
        accepted = state.copy()
        accepted.accept_clock(now, claims.iat)
        self._usable_claims(accepted, token, accepted.server_now(now))
        accepted.token = token
        for name in LicenceState.__slots__:
            setattr(state, name, getattr(accepted, name))

    def _device_public_key(self) -> bytes:
        """This computer's public key, making and saving the device key first when there is none."""
        with self._lock:
            if (public := self._public_key(self._state)) is not None:
                return public
            seed = self._crypto.new_device_key()
            keyed = replace(self._state.copy(), device_key=b64encode(seed))
            self._save(keyed)
            self._state = keyed
            return self._crypto.public_key(seed)

    def _public_key(self, state: LicenceState) -> bytes | None:
        seed = _seed(state)
        return None if seed is None else self._crypto.public_key(seed)

    def _save_for_check(self, state: LicenceState) -> None:
        try:
            self._save(state)
        except LicenceStoreError as ex:
            raise LicenceCheckFailed(f"the licence couldn't be saved: {ex}", unsaved=str(ex)) from ex

    def _save(self, state: LicenceState) -> None:
        if self._unreadable is not None:
            raise LicenceStoreUnreadable(self._unreadable)
        self._store.save(state.to_json())
        self._saved_latest, self._saved_rewound = state.latest_seen, state.rewound_seconds


def _refused(state: LicenceState) -> LicenceStatus:
    kind = REFUSAL_KINDS[state.refusal]
    return LicenceStatus(kind, licence_expires_at=state.refusal_at if kind is LicenceKind.EXPIRED else None)


def _activation_refused(answer: ServerAnswer) -> LicenceStatus:
    code = _error_code(answer)
    kinds = {
        "invalid_key": LicenceKind.INVALID_KEY,
        "already_activated": LicenceKind.ALREADY_ACTIVATED_ELSEWHERE,
        "licence_revoked": LicenceKind.REVOKED,
        "licence_expired": LicenceKind.EXPIRED,
        "product_unavailable": LicenceKind.PRODUCT_UNAVAILABLE,
    }
    if code == "rate_limited":
        return LicenceStatus(LicenceKind.RATE_LIMITED, retry_after=_retry_after(answer))
    if code in kinds:
        return LicenceStatus(kinds[code])
    logger.error("activation failed: HTTP %s (%s)", answer.status, code)
    return LicenceStatus(LicenceKind.SERVER_ERROR)


def _seed(state: LicenceState) -> bytes | None:
    seed = None if state.device_key is None else b64decode(state.device_key)
    return seed if seed is not None and len(seed) == 32 else None


def _text(answer: ServerAnswer, name: str) -> str | None:
    value = (answer.body or {}).get(name)
    return value if isinstance(value, str) and value else None


def _error_code(answer: ServerAnswer) -> str | None:
    return _text(answer, "error")


def _retry_after(answer: ServerAnswer) -> dt.timedelta:
    return dt.timedelta(seconds=answer.retry_after if answer.retry_after is not None else DEFAULT_RETRY_AFTER)


# --- the daily check ---------------------------------------------------------------------------------------

BACKOFF = (
    dt.timedelta(minutes=1),
    dt.timedelta(minutes=5),
    dt.timedelta(minutes=15),
    dt.timedelta(hours=1),
)
"""Waits after failed checks, one after the other, the last one repeated."""
STOP_SECONDS = 5.0
"""How long quitting waits for a check under way."""
LONGEST_SLEEP = dt.timedelta(minutes=10)
"""The checker wakes at least this often, to save the time seen and to notice a check that came due."""


class LicenceChecks:
    """Checks the licence online whenever a check is due, on a thread of its own that never holds up the UI, and
    tells each listener (on that thread) when the outcome's kind changes; a renewed token isn't a change."""

    def __init__(self, licence: Licence, wait: Callable[[float], object] | None = None) -> None:
        """``wait`` stands in for the stop flag's ``wait`` in tests (it gets the seconds to sleep)."""
        self._licence = licence
        self._listeners: list[Callable[[LicenceStatus], None]] = []
        self._listeners_lock = threading.Lock()
        self._stop = threading.Event()
        self._wait = wait if wait is not None else self._stop.wait
        self._thread: threading.Thread | None = None
        self._reported: LicenceKind | None = None
        self._failures = 0

    def subscribe(self, listener: Callable[[LicenceStatus], None]) -> None:
        with self._listeners_lock:
            self._listeners.append(listener)

    def start(self) -> None:
        self._reported = self._licence.status().kind
        self._thread = threading.Thread(target=self._loop, name="vitralis-licence", daemon=True)
        self._thread.start()
        logger.info("licence checks started")

    @property
    def running(self) -> bool:
        """Whether the checker's thread is alive (and so may be using the server's connection)."""
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = STOP_SECONDS) -> None:
        """Wake the checker and give it ``timeout`` seconds: asleep it ends at once, and a check under way gets
        that long to finish. One that takes longer (a stalled network) is left to end with the process: quitting
        doesn't wait for it, and ``running`` says so."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.warning("a licence check is still under way after %.0f s", timeout)
                return
        logger.info("licence checks stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            wait = self.run_once()
            self._wait(min(wait, LONGEST_SLEEP).total_seconds())
        self._save_time_seen()

    def run_once(self) -> dt.timedelta:
        """One round: check when due, report a change, save the time seen; how long to wait before the next."""
        try:
            wait = self._check_if_due()
        except Exception:  # a bug must not end the checks: logged, tried again after the longest backoff
            logger.exception("licence check failed unexpectedly")
            wait = BACKOFF[-1]
        self._save_time_seen()
        return wait

    def _check_if_due(self) -> dt.timedelta:
        if not self._licence.needs_check():
            return self._licence.time_until_due()
        try:
            outcome = self._licence.check()
        except LicenceCheckFailed as ex:
            wait = BACKOFF[min(self._failures, len(BACKOFF) - 1)]
            self._failures += 1
            logger.warning("licence check failed, trying again in %s: %s", wait, ex)
            return max(wait, ex.retry_after or dt.timedelta(0))
        self._failures = 0
        self._report(outcome)
        due = self._licence.time_until_due()
        return due if due > dt.timedelta(0) else BACKOFF[0]

    def _report(self, outcome: LicenceStatus) -> None:
        if outcome.kind is self._reported:
            return
        self._reported = outcome.kind
        logger.info("licence is now %s", outcome.kind)
        with self._listeners_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(outcome)
            except Exception:
                logger.exception("a licence listener failed; checks go on")

    def _save_time_seen(self) -> None:
        try:
            self._licence.save_time_seen()
        except LicenceStoreError as ex:
            logger.error("couldn't save the time seen: %s", ex)
