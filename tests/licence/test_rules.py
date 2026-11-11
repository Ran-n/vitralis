#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:58.416486
Revised: 2026/11/11 11:06:55.005813

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
    [b"", b"[]", b"null", b'{"refusal": "gone"}', b'{"latest_seen": "yesterday"}', b'{"rewound_seconds": "3"}'],
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
