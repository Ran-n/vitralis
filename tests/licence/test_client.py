#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:58.733165
Revised: 2026/11/14 12:01:48.609493

The licence use case against an in-memory Clavren that signs real tokens: activating, running offline, the
daily check, every refusal, a clock set back, and saved state that is damaged or can't be written. Then the
background checker: when it checks, its backoff, and what it reports.
"""

import datetime as dt
import json
import logging
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.licence.fakes import (
    CANONICAL,
    KEY,
    OTHER_KEY,
    START,
    FakeClavren,
    FakeClock,
    FakeLicenceRecord,
    MemoryLicenceStore,
    licence_config,
)
from vitralis.licence.client import (
    BACKOFF,
    NOT_AGAIN,
    Licence,
    LicenceCheckFailed,
    LicenceChecks,
)
from vitralis.licence.ports import LicenceStoreError, LicenceStoreUnreadable
from vitralis.licence.rules import LicenceKind, LicenceState, b64decode


@pytest.fixture
def clock():
    return FakeClock(START)


@pytest.fixture
def server(clock):
    return FakeClavren(clock)


@pytest.fixture
def store():
    return MemoryLicenceStore()


def make(clock, server, store, **config) -> Licence:
    return Licence(licence_config(**config), store, server, server.crypto(), clock)


@pytest.fixture
def licence(clock, server, store):
    return make(clock, server, store)


def restart(clock, server, store) -> Licence:
    """The app started again: everything comes from the saved state."""
    return make(clock, server, store)


# --- activating --------------------------------------------------------------------------------------------


def test_a_new_computer_needs_a_key(licence):
    assert licence.status().kind is LicenceKind.NEEDS_ACTIVATION
    assert licence.time_until_due() == NOT_AGAIN


def test_activating_licenses_this_computer_and_survives_a_restart(licence, clock, server, store):
    status = licence.activate(KEY)
    assert status.licensed and not status.test
    assert status.offline_until == START + dt.timedelta(days=30)
    assert status.licence_expires_at is None
    assert restart(clock, server, store).status().licensed


def test_the_key_is_sent_in_its_canonical_form_with_this_device(licence, server):
    licence.activate("brn 79yn 44xq wo25 377z")
    path, body = server.calls[0]
    assert path == "/api/v1/activations"
    assert body["key"] == CANONICAL and body["product"] == "vitralis"
    assert (body["device_name"], body["platform"], body["app_version"]) == ("TEST-PC", "windows-x86_64", "0.0.0-test")


def test_a_malformed_key_is_refused_without_asking_the_server(licence, server):
    assert licence.activate("BRN-1234").kind is LicenceKind.INVALID_KEY
    assert server.calls == []


def test_an_unknown_key_is_invalid(licence):
    assert licence.activate(OTHER_KEY).kind is LicenceKind.INVALID_KEY
    assert not licence.status().licensed


def test_a_key_in_use_elsewhere_is_refused(clock, server):
    assert make(clock, server, MemoryLicenceStore()).activate(KEY).licensed
    assert make(clock, server, MemoryLicenceStore()).activate(KEY).kind is LicenceKind.ALREADY_ACTIVATED_ELSEWHERE


def test_the_same_computer_activating_again_gets_its_activation_back(licence, server):
    first = licence.activate(KEY)
    again = licence.activate(KEY)
    assert first.licensed and again.licensed
    assert len(server.activations) == 1


def test_a_test_licence_works_on_many_computers_and_says_so(clock, server):
    server.licences[CANONICAL] = FakeLicenceRecord(test=True)
    for _ in range(3):
        status = make(clock, server, MemoryLicenceStore()).activate(KEY)
        assert status.licensed and status.test


def test_a_licence_until_a_date_says_when(licence, server):
    ends = START + dt.timedelta(days=10)
    server.licences[CANONICAL] = FakeLicenceRecord(expires_at=ends)
    status = licence.activate(KEY)
    assert status.licence_expires_at == ends
    assert status.offline_until == ends, "the token never outlives the licence"


@pytest.mark.parametrize(
    ("record", "product_active", "kind"),
    [
        (FakeLicenceRecord(revoked=True), True, LicenceKind.REVOKED),
        (FakeLicenceRecord(expires_at=START - dt.timedelta(days=1)), True, LicenceKind.EXPIRED),
        (FakeLicenceRecord(), False, LicenceKind.PRODUCT_UNAVAILABLE),
    ],
)
def test_activation_refusals(licence, server, record, product_active, kind):
    server.licences[CANONICAL] = record
    server.product_active = product_active
    assert licence.activate(KEY).kind is kind
    assert licence.status().kind is LicenceKind.NEEDS_ACTIVATION, "a refused activation keeps nothing"


def test_rate_limited_says_how_long_to_wait(licence, server):
    server.answers.append((429, {"error": "rate_limited"}, 120))
    status = licence.activate(KEY)
    assert status.kind is LicenceKind.RATE_LIMITED and status.retry_after == dt.timedelta(minutes=2)
    server.answers.append((429, {"error": "rate_limited"}, None))
    assert licence.activate(KEY).retry_after == dt.timedelta(minutes=1)


def test_an_unreachable_server_is_said_so(licence, server):
    server.down = True
    assert licence.activate(KEY).kind is LicenceKind.UNREACHABLE


@pytest.mark.parametrize(
    "answer",
    [(500, {"error": "internal_error"}, None), (200, None, None), (201, {"activation": "a"}, None), (418, None, None)],
)
def test_an_answer_that_isnt_clavrens_is_a_server_error_not_the_connections(licence, server, answer, caplog):
    """Regression guard: this used to tell the user to check an internet connection that worked."""
    server.answers.append(answer)
    with caplog.at_level(logging.ERROR):
        assert licence.activate(KEY).kind is LicenceKind.SERVER_ERROR
    assert caplog.records


def test_a_failed_check_says_what_kind_of_failure_it_was(activated, server, store):
    server.down = True
    with pytest.raises(LicenceCheckFailed) as unreachable:
        activated.check()
    server.down = False
    server.answers.append((429, {"error": "rate_limited"}, 90))
    with pytest.raises(LicenceCheckFailed) as limited:
        activated.check()
    server.answers.append((502, None, None))
    with pytest.raises(LicenceCheckFailed) as broken:
        activated.check()
    store.fail_saves = True
    with pytest.raises(LicenceCheckFailed) as unsaved:
        activated.check()
    assert unreachable.value.kind is LicenceKind.UNREACHABLE and unreachable.value.unsaved is None
    assert limited.value.kind is LicenceKind.RATE_LIMITED and limited.value.retry_after == dt.timedelta(seconds=90)
    assert broken.value.kind is LicenceKind.SERVER_ERROR
    assert unsaved.value.unsaved == "disk full"


def test_an_activation_whose_token_cant_be_used_is_kept_and_checked_next(licence, server, clock):
    server.answers.append((201, {"activation": "act-1", "token": "not.jwt"}, None))
    assert licence.activate(KEY).kind is LicenceKind.NEEDS_CHECK
    assert licence.needs_check(), "asked again at once; the checker's backoff paces it"


def test_the_device_key_is_saved_before_anything_is_sent(licence, store, server):
    store.fail_saves = True
    with pytest.raises(LicenceStoreError):
        licence.activate(KEY)
    assert server.calls == []


def test_an_accepted_activation_that_cant_be_saved_is_an_error_and_can_be_retried(licence, store, server):
    licence.activate(OTHER_KEY)  # saves the device key
    store.fail_saves = True
    with pytest.raises(LicenceStoreError):
        licence.activate(KEY)
    assert not licence.status().licensed
    store.fail_saves = False
    assert licence.activate(KEY).licensed, "the server knows this device again"


def test_the_device_key_never_changes(licence, server):
    licence.activate(OTHER_KEY)
    licence.activate(KEY)
    assert server.calls[0][1]["device_public_key"] == server.calls[1][1]["device_public_key"]


# --- offline -----------------------------------------------------------------------------------------------


def test_it_runs_offline_for_thirty_days_then_needs_a_check(licence, clock, server, store):
    licence.activate(KEY)
    server.down = True
    clock.advance(days=29, hours=23)
    assert licence.status().licensed
    clock.advance(hours=2)
    assert licence.status().kind is LicenceKind.NEEDS_CHECK


def test_a_clock_set_back_needs_a_check(licence, clock):
    licence.activate(KEY)
    clock.advance(hours=5)
    assert licence.status().licensed
    clock.advance(hours=-2)
    assert licence.status().kind is LicenceKind.NEEDS_CHECK


def test_a_clock_set_back_between_runs_is_noticed(licence, clock, server, store):
    licence.activate(KEY)
    clock.advance(hours=5)
    licence.status()
    licence.save_time_seen()
    clock.advance(hours=-2)
    assert restart(clock, server, store).status().kind is LicenceKind.NEEDS_CHECK


def test_small_steps_back_add_up_to_a_check(licence, clock):
    licence.activate(KEY)
    for _ in range(3):
        clock.advance(minutes=25)
        licence.status()
        clock.advance(minutes=-25)
        licence.status()
    assert licence.status().kind is LicenceKind.NEEDS_CHECK


def test_a_clock_that_is_simply_wrong_still_works(clock, server, store):
    server.issued_offset = dt.timedelta(days=-400)  # this computer is 400 days ahead of the server
    licence = make(clock, server, store)
    assert licence.activate(KEY).licensed
    clock.advance(days=29)
    assert licence.status().licensed


def test_a_clock_set_back_before_the_check_doesnt_stretch_the_token(clock, server, store):
    licence = make(clock, server, store)
    clock.advance(days=-20)  # set back, then checked: the server's time is measured again
    licence.activate(KEY)
    clock.advance(days=30, hours=1)
    assert licence.status().kind is LicenceKind.NEEDS_CHECK


def test_time_seen_is_saved_only_when_it_moved(licence, clock, store):
    licence.activate(KEY)
    saves = store.saves
    clock.advance(minutes=5)
    licence.status()
    licence.save_time_seen()
    assert store.saves == saves
    clock.advance(minutes=6)
    licence.status()
    licence.save_time_seen()
    assert store.saves == saves + 1
    clock.advance(minutes=-1)
    licence.status()
    licence.save_time_seen()
    assert store.saves == saves + 2, "a step back is saved at once"


def test_the_first_time_seen_is_saved(licence, store):
    licence.status()
    licence.save_time_seen()
    assert store.saves == 1


def test_server_time_follows_the_measured_offset(clock, server, store):
    server.issued_offset = dt.timedelta(hours=3)
    licence = make(clock, server, store)
    licence.activate(KEY)
    assert licence.server_time() == clock() + dt.timedelta(hours=3)


# --- tokens that can't be run on -----------------------------------------------------------------------------


def _saved_with_token(licence: Licence, store: MemoryLicenceStore, token: str) -> None:
    state = LicenceState.from_json(store.data)
    state.token = token
    store.data = state.to_json()


def _claims_of(licence_state: LicenceState) -> dict:
    return json.loads(b64decode(licence_state.token.split(".")[1]))


@pytest.mark.parametrize(
    "tamper",
    [
        lambda server, claims: server.sign({**claims, "aud": "avalio-lite"}),
        lambda server, claims: server.sign({**claims, "act": "another"}),
        lambda server, claims: server.sign({**claims, "dev": "another-device"}),
        lambda server, claims: server.sign(claims, kid="v9"),
        lambda server, claims: server.sign(claims, key=Ed25519PrivateKey.generate()),
        lambda server, claims: server.sign(claims)[:-4] + "AAAA",
    ],
    ids=["other product", "other activation", "other device", "untrusted key", "foreign signature", "tampered"],
)
def test_a_token_that_isnt_this_computers_needs_a_check(licence, clock, server, store, tamper):
    licence.activate(KEY)
    claims = _claims_of(LicenceState.from_json(store.data))
    _saved_with_token(licence, store, tamper(server, claims))
    assert restart(clock, server, store).status().kind is LicenceKind.NEEDS_CHECK


# --- the daily check ---------------------------------------------------------------------------------------


def test_a_check_is_due_daily(licence, clock):
    licence.activate(KEY)
    assert licence.time_until_due() == dt.timedelta(days=1)
    clock.advance(hours=23)
    assert not licence.needs_check()
    clock.advance(hours=1)
    assert licence.needs_check()


def test_a_check_proves_the_device_and_renews_the_token(licence, clock, server):
    licence.activate(KEY)
    clock.advance(days=20)
    status = licence.check()
    assert status.licensed and status.offline_until == clock() + dt.timedelta(days=30)
    assert server.calls[-1][1]["app_version"] == "0.0.0-test"


def test_a_check_mends_a_clock_set_back(licence, clock):
    licence.activate(KEY)
    clock.advance(hours=-3)
    assert licence.status().kind is LicenceKind.NEEDS_CHECK
    assert licence.needs_check()
    assert licence.check().licensed


def test_without_an_activation_there_is_nothing_to_check(licence, server):
    assert licence.check().kind is LicenceKind.NEEDS_ACTIVATION
    assert server.calls == []


def test_a_reset_computer_is_revoked_and_can_take_a_key_again(licence, server, clock):
    licence.activate(KEY)
    server.reset()
    assert licence.check().kind is LicenceKind.REVOKED
    assert licence.status().kind is LicenceKind.REVOKED
    assert licence.time_until_due() == NOT_AGAIN, "nothing to check after a revoke"
    assert licence.activate(KEY).licensed, "the freed key works here again"


def test_a_revoked_licence_locks_and_stays_locked_after_a_restart(licence, server, clock, store):
    licence.activate(KEY)
    server.licences[CANONICAL].revoked = True
    assert licence.check().kind is LicenceKind.REVOKED
    assert restart(clock, server, store).status().kind is LicenceKind.REVOKED


def test_an_expired_licence_says_when_and_unlocks_once_extended(licence, server, clock):
    ends = START + dt.timedelta(days=3)
    server.licences[CANONICAL] = FakeLicenceRecord(expires_at=ends)
    licence.activate(KEY)
    clock.advance(days=4)
    status = licence.check()
    assert status.kind is LicenceKind.EXPIRED and status.licence_expires_at == ends
    assert licence.status().licence_expires_at == ends
    assert not licence.needs_check()
    clock.advance(days=1)
    assert licence.needs_check(), "checked again daily: an expiry may be extended"
    server.licences[CANONICAL].expires_at = None
    assert licence.check().licensed


def test_a_withdrawn_product_locks(licence, server):
    licence.activate(KEY)
    server.product_active = False
    assert licence.check().kind is LicenceKind.PRODUCT_UNAVAILABLE


@pytest.mark.parametrize(
    "answers",
    [
        [(500, {"error": "internal_error"}, None)],
        [(200, {"challenge": "c"}, None)],
        [(200, {"challenge": "c", "nonce": "AAAA"}, None)],
        [(200, {"challenge": "c", "nonce": "A" * 43}, None), (500, None, None)],
        [(200, {"challenge": "c", "nonce": "A" * 43}, None), (200, {}, None)],
        [(200, {"challenge": "c", "nonce": "A" * 43}, None), (200, {"token": "x.y.z"}, None)],
        [(401, {"error": "challenge_invalid"}, None)],
    ],
)
def test_a_check_that_decides_nothing_changes_nothing(licence, server, answers):
    licence.activate(KEY)
    server.answers.extend(answers)
    with pytest.raises(LicenceCheckFailed):
        licence.check()
    assert licence.status().licensed


def test_an_unreachable_check_changes_nothing(licence, server):
    licence.activate(KEY)
    server.down = True
    with pytest.raises(LicenceCheckFailed):
        licence.check()
    assert licence.status().licensed


def test_a_rate_limited_check_says_how_long_to_wait(licence, server):
    licence.activate(KEY)
    server.answers.append((429, {"error": "rate_limited"}, 300))
    with pytest.raises(LicenceCheckFailed) as failed:
        licence.check()
    assert failed.value.retry_after == dt.timedelta(minutes=5)


def test_a_check_that_cant_be_saved_changes_nothing(licence, server, store):
    licence.activate(KEY)
    store.fail_saves = True
    with pytest.raises(LicenceCheckFailed):
        licence.check()
    server.licences[CANONICAL].revoked = True
    with pytest.raises(LicenceCheckFailed):
        licence.check()
    assert licence.status().licensed, "a refusal that couldn't be saved changes nothing either"


def test_an_answer_about_an_old_activation_is_ignored(licence, server, clock):
    licence.activate(KEY)
    old = licence._state.activation

    def swap_then_refuse(path, body):
        licence._state.activation = "new"
        return type(server).post(server, path, body)

    server.licences[CANONICAL].revoked = True
    server.post = swap_then_refuse
    with pytest.raises(LicenceCheckFailed, match="activation changed"):
        licence.check()
    licence._state.activation = old
    server.licences[CANONICAL].revoked = False

    def swap_after_challenge(path, body):
        answer = type(server).post(server, path, body)
        if path.endswith("/checks"):
            licence._state.activation = "new"
        return answer

    server.post = swap_after_challenge
    with pytest.raises(LicenceCheckFailed, match="activation changed"):
        licence.check()


# --- saved state -------------------------------------------------------------------------------------------


def test_damaged_saved_state_starts_over(clock, server, caplog):
    with caplog.at_level(logging.WARNING):
        assert make(clock, server, MemoryLicenceStore(b"garbage")).status().kind is LicenceKind.NEEDS_ACTIVATION
    assert "damaged" in caplog.text


def test_another_accounts_state_starts_over(clock, server):
    store = MemoryLicenceStore()
    store.fail_load = LicenceStoreError("can't be unprotected")
    licence = make(clock, server, store)
    assert licence.status().kind is LicenceKind.NEEDS_ACTIVATION and licence.unreadable is None
    store.fail_load = None
    assert licence.activate(KEY).licensed


def test_unreadable_state_is_never_overwritten(clock, server, caplog):
    store = MemoryLicenceStore(b"precious")
    store.fail_load = LicenceStoreUnreadable("in use by another program")
    with caplog.at_level(logging.ERROR):
        licence = make(clock, server, store)
    assert licence.unreadable == "in use by another program"
    with pytest.raises(LicenceStoreUnreadable):
        licence.activate(KEY)
    assert store.data == b"precious"


def test_secrets_never_reach_the_log(licence, server, clock, caplog):
    with caplog.at_level(logging.DEBUG):
        licence.activate(KEY)
        state = json.loads(licence._store.data)
        licence.check()
        server.down = True
        with pytest.raises(LicenceCheckFailed):
            licence.check()
        server.down = False
        server.reset()
        licence.check()
    sent = server.calls  # every (path, body)
    assert CANONICAL not in caplog.text and KEY not in caplog.text
    assert all(body.get("device_public_key", "@") not in caplog.text for _, body in sent)
    for secret in ("token", "device_key", "activation"):
        assert state[secret] and state[secret] not in caplog.text, secret


def test_a_long_computer_name_is_cut_to_what_the_server_takes(clock, server):
    licence = make(clock, server, MemoryLicenceStore(), device_name="X" * 300)
    licence.activate(KEY)
    assert len(server.calls[0][1]["device_name"]) == 200


# --- the background checker --------------------------------------------------------------------------------


class Waits(list):
    """Stands in for the stop flag's wait: records each wait and stops after ``rounds``."""

    def __init__(self, checks: LicenceChecks | None = None, rounds: int = 1) -> None:
        super().__init__()
        self.checks, self.rounds = checks, rounds

    def __call__(self, seconds: float) -> None:
        self.append(seconds)
        if len(self) >= self.rounds and self.checks is not None:
            self.checks._stop.set()


def test_the_checker_checks_when_due_and_waits_until_the_next(licence, clock):
    licence.activate(KEY)
    clock.advance(days=1)
    checks = LicenceChecks(licence)
    assert checks.run_once() == dt.timedelta(days=1)


def test_the_checker_waits_while_nothing_is_due(licence, clock):
    licence.activate(KEY)
    clock.advance(hours=6)
    assert LicenceChecks(licence).run_once() == dt.timedelta(hours=18)


def test_the_checker_backs_off_after_failures(licence, clock, server):
    licence.activate(KEY)
    clock.advance(days=1)
    server.down = True
    checks = LicenceChecks(licence)
    assert [checks.run_once() for _ in range(6)] == [*BACKOFF, BACKOFF[-1], BACKOFF[-1]]
    server.down = False
    assert checks.run_once() == dt.timedelta(days=1)
    server.down = True
    clock.advance(days=1)
    assert checks.run_once() == BACKOFF[0], "a success starts the backoff over"


def test_the_checker_waits_as_long_as_the_server_asks(licence, clock, server):
    licence.activate(KEY)
    clock.advance(days=1)
    server.answers.append((429, {"error": "rate_limited"}, 7200))
    assert LicenceChecks(licence).run_once() == dt.timedelta(hours=2)


def test_the_checker_reports_only_a_change_of_kind(licence, clock, server):
    licence.activate(KEY)
    heard = []
    checks = LicenceChecks(licence)
    checks.subscribe(heard.append)
    checks._reported = licence.status().kind
    clock.advance(days=1)
    checks.run_once()
    assert heard == [], "a renewed token is no change"
    server.licences[CANONICAL].revoked = True
    clock.advance(days=1)
    checks.run_once()
    assert [status.kind for status in heard] == [LicenceKind.REVOKED]


def test_a_failing_listener_doesnt_stop_the_checks(licence, clock, server, caplog):
    licence.activate(KEY)
    checks = LicenceChecks(licence)

    def broken(_status):
        raise RuntimeError("listener bug")

    heard = []
    checks.subscribe(broken)
    checks.subscribe(heard.append)
    checks._reported = LicenceKind.NEEDS_CHECK
    clock.advance(days=1)
    with caplog.at_level(logging.ERROR):
        checks.run_once()
    assert "licence listener failed" in caplog.text
    assert [s.kind for s in heard] == [LicenceKind.LICENSED]


def test_a_bug_in_a_check_is_logged_and_tried_again_later(licence, clock, caplog):
    licence.activate(KEY)
    clock.advance(days=1)
    licence.check = lambda: 1 / 0
    with caplog.at_level(logging.ERROR):
        assert LicenceChecks(licence).run_once() == BACKOFF[-1]
    assert "ZeroDivisionError" in caplog.text


def test_a_time_seen_that_cant_be_saved_is_logged(licence, store, caplog):
    store.fail_saves = True
    licence.status()  # a time seen, not saved yet
    with caplog.at_level(logging.ERROR):
        LicenceChecks(licence).run_once()
    assert "couldn't save the time seen" in caplog.text


def test_the_checker_thread_starts_checks_and_stops(licence, clock):
    licence.activate(KEY)
    clock.advance(days=1)
    waits = Waits(rounds=2)
    checks = LicenceChecks(licence, wait=waits)
    waits.checks = checks
    checks.start()
    checks._thread.join(5)
    assert not checks._thread.is_alive()
    assert waits[0] == dt.timedelta(minutes=10).total_seconds(), "it wakes at least every ten minutes"
    checks.stop()


def test_stopping_a_checker_that_never_started_is_fine(licence):
    LicenceChecks(licence).stop()


def test_a_checker_that_wont_stop_is_logged(licence, caplog):
    checks = LicenceChecks(licence)
    hold = threading.Event()
    checks._thread = threading.Thread(target=hold.wait, daemon=True)
    checks._thread.start()
    with caplog.at_level(logging.WARNING):
        checks.stop(timeout=0.01)
    assert "still under way" in caplog.text and "stopped" not in caplog.text
    assert checks.running  # its connection must not be closed under it
    hold.set()
    checks._thread.join(5)
    assert not checks.running


def test_a_checker_asleep_stops_at_once(licence):
    checks = LicenceChecks(licence)
    assert not checks.running
    checks.start()
    assert checks.running
    checks.stop()
    assert not checks.running
