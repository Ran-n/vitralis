#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:58.416486
Revised: 2026/11/14 18:00:30.154848

The licence rules, pinned by Clavren's own test vectors (``../clavren/docs/api.md``, "Test vectors").
"""

import datetime as dt
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vitralis.licence.rules import (
    CROCKFORD,
    LicenceKind,
    LicenceState,
    LicenceStatus,
    Refusal,
    b64decode,
    b64encode,
    check_message,
    format_key,
    normalize_key,
    unverified_claims,
)

AT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    "typed", ["BRN-79YN-44XQ-W025-377Z", "brn 79yn 44xq w025 377z", "BRN79YN44XQWO25377Z", " brn-79yn44xq-wO25-377z "]
)
def test_every_way_of_typing_the_vector_key_reads_the_same(typed):
    assert normalize_key(typed) == "BRN79YN44XQW025377Z"


def test_i_and_l_read_as_one():
    assert normalize_key("BRN-79YN-44XQ-W025-3I7Z") == normalize_key("BRN-79YN-44XQ-W025-3l7Z") == "BRN79YN44XQW025317Z"


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "BRN",
        "BRN-79YN-44XQ-W025-377",
        "BRN-79YN-44XQ-W025-377ZZ",
        "XYZ-79YN-44XQ-W025-377Z",
        "79YN-44XQ-W025-377Z-BRNA",
        "BRN-79YN-44XQ-W025-377U",
        "BRN-79YN-44XQ-W025-377!",
        "BRN-79YN-44XQ-W025-377Ẑ",
    ],
)
def test_malformed_keys_are_refused(typed):
    assert normalize_key(typed) is None


@pytest.mark.property
@given(st.text(alphabet=CROCKFORD, min_size=16, max_size=16))
def test_any_key_formats_and_reads_back_however_it_is_typed(body):
    canonical = "BRN" + body
    formatted = format_key(canonical)
    assert normalize_key(formatted) == canonical
    assert normalize_key(formatted.lower().replace("-", " ")) == canonical


@pytest.mark.property
@given(st.text(min_size=0, max_size=40))
def test_a_read_key_is_always_canonical(typed):
    key = normalize_key(typed)
    assert key is None or (key.startswith("BRN") and len(key) == 19 and set(key) <= set(CROCKFORD))


def test_the_check_message_matches_the_vector():
    message = check_message(
        "01900000-0000-7000-8000-000000000001", "01900000-0000-7000-8000-000000000002", bytes(range(32))
    )
    assert message == (
        "clavren-check-v1\n01900000-0000-7000-8000-000000000001\n01900000-0000-7000-8000-000000000002\n"
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
    )


def test_base64url_is_unpadded_and_refuses_padding():
    assert b64encode(bytes([0xFB, 0xFF])) == "-_8"
    assert b64decode("-_8") == bytes([0xFB, 0xFF])
    assert b64decode("-_8=") is None
    assert b64decode("A") is None
    assert b64decode("*-*-") is None


@pytest.mark.property
@given(st.binary(max_size=64))
def test_base64url_round_trips(data):
    assert b64decode(b64encode(data)) == data


def _token(claims: dict) -> str:
    return f"{b64encode(b'{}')}.{b64encode(json.dumps(claims).encode())}.sig"


CLAIMS = {"aud": "vitralis", "act": "a", "dev": "d", "iat": 10, "exp": 20}


def test_unverified_claims_reads_what_the_token_carries():
    claims = unverified_claims(_token({**CLAIMS, "lic_exp": 15, "test": True}))
    assert (claims.aud, claims.act, claims.iat, claims.exp, claims.lic_exp, claims.test) == (
        "vitralis",
        "a",
        10,
        20,
        15,
        True,
    )


def test_a_test_claim_only_counts_when_it_is_true():
    assert unverified_claims(_token({**CLAIMS, "test": "yes"})).test is False
    assert unverified_claims(_token(CLAIMS)).lic_exp is None


@pytest.mark.parametrize(
    "token",
    [
        "not a token",
        "a.b",
        "a.!!!.c",
        f"a.{b64encode(b'[1]')}.c",
        _token({**CLAIMS, "iat": "10"}),
        _token({**CLAIMS, "exp": True}),
        _token({k: v for k, v in CLAIMS.items() if k != "act"}),
        f"a.{b64encode(b'not json')}.c",
    ],
)
def test_anything_else_is_no_claims(token):
    assert unverified_claims(token) is None


def test_the_latest_time_seen_only_moves_forward():
    state = LicenceState()
    state.saw(AT)
    state.saw(AT - dt.timedelta(minutes=5))
    assert state.latest_seen == AT


def test_small_steps_back_add_up():
    state = LicenceState()

    def at(seconds: int) -> dt.datetime:
        return AT + dt.timedelta(seconds=seconds)

    state.saw(at(10_000))
    state.saw(at(9_000))
    state.saw(at(9_500))
    state.saw(at(8_800))
    assert state.rewound_seconds == 1_000 + 700
    assert state.rewound_by(at(8_000)) == 1_700 + 800
    assert state.rewound_by(at(9_000)) == 1_700, "moving forward adds nothing"


def test_a_clock_counts_as_set_back_past_an_hour_at_once_or_in_steps():
    state = LicenceState()
    state.saw(AT)
    assert not state.clock_set_back(AT - dt.timedelta(minutes=59))
    assert state.clock_set_back(AT - dt.timedelta(minutes=61))
    for _ in range(3):  # three steps of 25 minutes, each forward again in between
        state.saw(AT)
        state.saw(AT - dt.timedelta(minutes=25))
    assert state.clock_set_back(AT)


def test_server_time_adds_the_measured_offset_and_ignores_a_damaged_one():
    state = LicenceState(clock_offset_seconds=120)
    assert state.server_now(AT) == AT + dt.timedelta(minutes=2)
    state.clock_offset_seconds = 10**15
    assert state.server_now(AT) == AT


def test_accepting_the_clock_makes_now_the_baseline():
    state = LicenceState(rewound_seconds=5000, latest_seen=AT + dt.timedelta(days=3))
    state.accept_clock(AT, int(AT.timestamp()) + 30)
    assert (state.latest_seen, state.last_seen, state.last_check, state.rewound_seconds) == (AT, AT, AT, 0)
    assert state.clock_offset_seconds == 30


def test_the_state_round_trips_through_json():
    state = LicenceState(
        device_key="k",
        activation="a",
        token="t",
        latest_seen=AT,
        last_seen=AT,
        rewound_seconds=3,
        clock_offset_seconds=-4,
        last_check=AT,
        refusal=Refusal.EXPIRED,
        refusal_at=AT,
    )
    assert LicenceState.from_json(state.to_json()) == state


def test_a_state_saved_with_fewer_fields_still_loads():
    assert LicenceState.from_json(b'{"activation": "a"}') == LicenceState(activation="a")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"null",
        b'{"refusal": "gone"}',
        b'{"latest_seen": "yesterday"}',
        b'{"rewound_seconds": "3"}',
        b'{"token": 5}',  # regression guard: these four loaded, and asking the licence then raised at every start
        b'{"device_key": ["k"]}',
        b'{"activation": {"id": 1}}',
        b'{"latest_seen": "2026-01-01T00:00:00"}',
    ],
)
def test_a_damaged_state_is_an_error(raw):
    with pytest.raises(ValueError):
        LicenceState.from_json(raw)


def test_the_state_never_shows_its_secrets():
    shown = repr(LicenceState(device_key="secret-key", token="tok-hid", activation="a"))
    assert "secret-key" not in shown and "tok-hid" not in shown and "'a'" in shown


def test_a_copy_is_independent():
    state = LicenceState(activation="a")
    copied = state.copy()
    copied.activation = "b"
    assert state.activation == "a"


def test_only_licensed_runs():
    assert LicenceStatus(LicenceKind.LICENSED).licensed
    assert not any(LicenceStatus(kind).licensed for kind in LicenceKind if kind is not LicenceKind.LICENSED)


# --- what mutation testing found unchecked ------------------------------------------------------------------


def test_base64url_reads_every_whole_length_and_no_other():
    assert b64decode("QQ") == b"A" and b64decode("QUI") == b"AB" and b64decode("QUJD") == b"ABC"
    assert b64decode("QUJDRA") == b"ABCD"
    assert b64decode("QUJDR") is None  # one character past a whole group: no bytes are that long
    assert b64decode("Q") is None


def test_a_character_that_upper_cases_to_two_is_no_key_symbol():
    """The ligature ``ﬆ`` upper-cases to ``ST``, two symbols of the key's alphabet in a row."""
    assert normalize_key("BRN-ST00-0000-0000-0000") is not None
    assert normalize_key("BRN-ﬆ00-0000-0000-0000") is None
    assert normalize_key("BRN-ﬆ000-0000-0000-0000") is None


def test_nothing_is_a_test_licence_unless_it_says_so():
    from vitralis.licence.rules import Claims

    assert LicenceStatus(LicenceKind.LICENSED).test is False
    claims = Claims("vitralis", "activation", "device", 1, 2)
    assert claims.test is False and claims.lic_exp is None


def test_a_status_and_claims_cant_be_changed():
    from vitralis.licence.rules import Claims

    for value in (LicenceStatus(LicenceKind.LICENSED), Claims("vitralis", "activation", "device", 1, 2)):
        with pytest.raises(AttributeError):
            value.test = True
        assert not hasattr(value, "__dict__")  # nor given anything new


def token_of(claims: dict, parts: int = 3) -> str:
    payload = b64encode(json.dumps(claims).encode())
    return ".".join(["header", payload, "signature", "more", "again"][:parts])


def test_a_token_has_three_parts_no_fewer_and_no_more():
    claims = {"aud": "vitralis", "act": "a", "dev": "d", "iat": 1, "exp": 2}
    assert unverified_claims(token_of(claims)) is not None
    assert unverified_claims(token_of(claims, parts=2)) is None
    assert unverified_claims(token_of(claims, parts=4)) is None


def test_a_test_claim_that_is_one_and_not_true_doesnt_count():
    claims = {"aud": "vitralis", "act": "a", "dev": "d", "iat": 1, "exp": 2}
    assert unverified_claims(token_of({**claims, "test": True})).test is True
    assert unverified_claims(token_of({**claims, "test": 1})).test is False


def test_the_clock_is_behind_only_past_the_tolerance():
    from vitralis.licence.rules import ROLLBACK_TOLERANCE

    assert not LicenceState().clock_set_back(AT - dt.timedelta(days=3650))  # nothing seen yet to be behind
    state = LicenceState(latest_seen=AT)  # as loaded from a file that says no more
    assert not state.clock_set_back(AT - ROLLBACK_TOLERANCE)  # exactly the tolerance: still trusted
    assert state.clock_set_back(AT - ROLLBACK_TOLERANCE - dt.timedelta(microseconds=1))
    assert not state.clock_set_back(AT + dt.timedelta(days=1))


def test_steps_back_count_only_past_the_tolerance_in_all():
    from vitralis.licence.rules import ROLLBACK_TOLERANCE

    state = LicenceState()
    state.saw(AT)
    state.latest_seen = None  # only the steps back are left to judge by
    assert not state.clock_set_back(AT - ROLLBACK_TOLERANCE)  # exactly the tolerance
    assert state.clock_set_back(AT - ROLLBACK_TOLERANCE - dt.timedelta(seconds=1))


def test_the_state_shows_that_it_holds_secrets_without_showing_them():
    from vitralis.licence.rules import REDACTED

    empty, full = repr(LicenceState()), repr(LicenceState(device_key="c2VlZA", token="a.b.c"))
    assert "device_key=None" in empty and "token=None" in empty
    assert f"device_key={REDACTED!r}" in full and f"token={REDACTED!r}" in full
    assert "c2VlZA" not in full and "a.b.c" not in full
