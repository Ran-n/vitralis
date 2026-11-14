#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.495642
Revised: 2026/11/14 12:31:25.347038

The licence gate: the app runs only while the licence holds, locks again when it stops holding (a refusal from
the daily check, 30 days offline, a clock set back), and every activation or check runs off the UI thread.
"""

import datetime as dt

import pytest

from tests.conftest import wait_until
from tests.licence.fakes import CANONICAL, KEY, OTHER_KEY, FakeLicenceRecord, licence_config
from vitralis.licence.client import Licence
from vitralis.licence.gate import WATCH_INTERVAL_MS, LicenceGate
from vitralis.licence.messages import save_failed_message, status_message
from vitralis.licence.ports import LicenceStoreUnreadable
from vitralis.licence.rules import LicenceKind, LicenceStatus

pytestmark = pytest.mark.ui


def test_a_new_computer_stays_locked_and_asks_for_a_key(make_gate, events, checks):
    gate = make_gate()
    gate.begin()
    assert events.unlocks == 0 and not gate.unlocked
    assert [s.kind for s in events.last_prompt.statuses] == [LicenceKind.NEEDS_ACTIVATION]
    assert checks.started == 1 and len(checks.listeners) == 1


def test_a_saved_licence_unlocks_at_once_without_a_window(make_gate, events, activated):
    gate = make_gate()
    gate.begin()
    assert events.unlocks == 1 and gate.unlocked
    assert events.prompts == []


def test_a_good_key_unlocks_and_closes_the_window(qapp, make_gate, events):
    gate = make_gate()
    gate.begin()
    prompt = events.last_prompt
    gate.activate(KEY)
    assert gate.busy and prompt.busy == [True]
    wait_until(qapp, lambda: not gate.busy)
    assert events.unlocks == 1 and prompt.dismissed and prompt.busy == [True, False]


def test_an_unknown_key_keeps_the_window_and_says_why(qapp, make_gate, events):
    gate = make_gate()
    gate.begin()
    gate.activate(OTHER_KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert events.unlocks == 0
    assert events.last_prompt.statuses[-1].kind is LicenceKind.INVALID_KEY


def test_a_key_in_use_elsewhere_says_so(qapp, make_gate, events, server):
    server.licences[CANONICAL] = FakeLicenceRecord(device="someone-else")
    gate = make_gate()
    gate.begin()
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert events.last_prompt.statuses[-1].kind is LicenceKind.ALREADY_ACTIVATED_ELSEWHERE


def test_activating_while_busy_sends_nothing_more(qapp, make_gate, server):
    gate = make_gate()
    gate.begin()
    gate.activate(KEY)
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert [path for path, _ in server.calls].count("/api/v1/activations") == 1


def test_a_server_that_cant_be_reached_says_so(qapp, make_gate, events, server):
    server.down = True
    gate = make_gate()
    gate.begin()
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert events.last_prompt.statuses[-1].kind is LicenceKind.UNREACHABLE


def test_a_licence_that_cant_be_saved_says_so(qapp, make_gate, events, store):
    store.fail_saves = True
    gate = make_gate()
    errors = []
    gate.error.connect(errors.append)
    gate.begin()
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert events.unlocks == 0
    assert errors == events.last_prompt.errors and "disk full" in errors[0]


def test_a_bug_while_activating_is_said_and_never_leaves_the_window_waiting(qapp, make_gate, events, monkeypatch):
    gate = make_gate()
    gate.begin()
    monkeypatch.setattr(Licence, "activate", lambda self, key: 1 / 0)
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert "ZeroDivisionError" in events.last_prompt.errors[0]


def test_a_refusal_from_the_daily_check_locks_the_running_app(qapp, make_gate, events, checks, activated):
    gate = make_gate()
    gate.begin()
    checks.report(LicenceStatus(LicenceKind.REVOKED))  # from the checker's thread in the app
    qapp.processEvents()
    assert events.locks == 1 and not gate.unlocked
    assert events.last_prompt.statuses[-1].kind is LicenceKind.REVOKED


def test_thirty_days_offline_locks_the_running_app_at_the_next_watch(make_gate, events, activated, clock):
    gate = make_gate()
    gate.begin()
    clock.advance(days=31)
    gate.refresh()
    assert events.locks == 1
    assert events.last_prompt.statuses[-1].kind is LicenceKind.NEEDS_CHECK


def test_the_watch_runs_every_minute(make_gate):
    gate = make_gate()
    gate.begin()
    assert gate._watch.isActive() and gate._watch.interval() == WATCH_INTERVAL_MS == 60_000


def test_a_clock_set_back_locks_the_running_app(make_gate, events, activated, clock):
    gate = make_gate()
    gate.begin()
    clock.advance(hours=-2)
    gate.refresh()
    assert events.locks == 1
    assert events.last_prompt.statuses[-1].kind is LicenceKind.NEEDS_CHECK


def test_a_check_back_online_unlocks_again(qapp, make_gate, events, activated, clock):
    gate = make_gate()
    gate.begin()
    clock.advance(days=31)
    gate.refresh()
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    assert events.unlocks == 2 and gate.unlocked and events.last_prompt.dismissed


def test_check_now_offline_says_the_server_cant_be_reached(qapp, make_gate, events, activated, clock, server):
    gate = make_gate()
    gate.begin()
    clock.advance(days=31)
    gate.refresh()
    server.down = True
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    assert not gate.unlocked
    assert events.last_prompt.errors == [status_message(LicenceStatus(LicenceKind.UNREACHABLE))]


def test_check_now_while_licensed_reports_through_changed(qapp, make_gate, activated):
    gate = make_gate()
    seen = []
    gate.changed.connect(seen.append)
    gate.begin()
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    assert [s.kind for s in seen] == [LicenceKind.LICENSED, LicenceKind.LICENSED]


def test_a_saved_licence_another_program_holds_is_never_overwritten_and_said(
    qapp, checks, events, server, store, clock
):
    store.fail_load = LicenceStoreUnreadable("licence.dat: in use")
    licence = Licence(licence_config(), store, server, server.crypto(), clock)
    gate = LicenceGate(licence, checks, events.unlock, events.lock, events.prompt)
    gate.begin()
    assert "in use" in events.last_prompt.errors[0]
    gate.activate(KEY)
    wait_until(qapp, lambda: not gate.busy)
    assert store.saves == 0 and events.unlocks == 0
    gate.shutdown()


def test_shutdown_stops_the_checks_and_closes_the_window_once(make_gate, events, checks):
    gate = make_gate()
    gate.begin()
    gate.shutdown()
    gate.shutdown()
    assert checks.stopped == 1 and events.last_prompt.dismissed and not gate._watch.isActive()


def test_server_time_follows_the_licence(make_gate, activated, clock):
    gate = make_gate()
    assert abs(gate.server_time() - clock()) < dt.timedelta(seconds=1)


def test_the_watch_leaves_the_window_alone_while_nothing_changed(qapp, make_gate, events):
    """Regression guard: every minute the watch showed the status again, which wiped "That key isn't valid" and
    took the focus back."""
    gate = make_gate()
    gate.begin()
    gate.activate(OTHER_KEY)
    wait_until(qapp, lambda: not gate.busy)
    shown = list(events.last_prompt.statuses)
    assert shown[-1].kind is not LicenceKind.NEEDS_ACTIVATION  # what the attempt came to
    for _ in range(3):
        gate.refresh()
    assert events.last_prompt.statuses == shown


def test_the_watch_tells_the_window_once_when_the_saved_licence_changes(make_gate, events, activated, clock):
    gate = make_gate()
    gate.begin()
    clock.advance(days=31)
    gate.refresh()
    gate.refresh()
    assert [status.kind for status in events.last_prompt.statuses] == [LicenceKind.NEEDS_CHECK]


def locked_after_a_month(make_gate, clock):
    gate = make_gate()
    gate.begin()
    clock.advance(days=31)
    gate.refresh()
    return gate


def test_check_now_rate_limited_says_how_long_to_wait(qapp, make_gate, events, activated, clock, server):
    """Regression guard: every failed check said "check your internet connection"."""
    gate = locked_after_a_month(make_gate, clock)
    server.answers.append((429, {"error": "rate_limited"}, 90))
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    waiting = LicenceStatus(LicenceKind.RATE_LIMITED, retry_after=dt.timedelta(seconds=90))
    assert events.last_prompt.errors == [status_message(waiting)] and "90" in events.last_prompt.errors[0]


def test_check_now_with_an_answer_that_isnt_clavrens_says_so(qapp, make_gate, events, activated, clock, server):
    gate = locked_after_a_month(make_gate, clock)
    server.answers.append((502, None, None))
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    assert events.last_prompt.errors == [status_message(LicenceStatus(LicenceKind.SERVER_ERROR))]


def test_check_now_that_cant_save_the_licence_says_why(qapp, make_gate, events, activated, clock, store):
    gate = locked_after_a_month(make_gate, clock)
    store.fail_saves = True
    gate.check_now()
    wait_until(qapp, lambda: not gate.busy)
    assert events.last_prompt.errors == [save_failed_message("disk full")]


def test_the_gate_is_working_while_a_request_or_the_checker_runs(qapp, make_gate, checks, monkeypatch):
    import threading

    gate = make_gate()
    gate.begin()
    assert not gate.working
    release = threading.Event()
    monkeypatch.setattr(Licence, "activate", lambda self, key: release.wait(5) and self.status())
    gate.activate(KEY)
    assert gate.working
    release.set()
    wait_until(qapp, lambda: not gate.working)
    checks.running = True
    assert gate.working


def test_the_licence_window_is_brought_to_the_front_as_it_is(qapp, make_gate, events, activated):
    gate = make_gate()
    gate.begin()
    gate.show_window()  # unlocked: there is no window, and nothing happens
    assert events.prompts == []
    locked = make_gate()
    locked._licence._state.token = None  # as on a computer whose licence no longer holds
    locked.begin()
    shown = list(events.last_prompt.statuses)
    locked.show_window()
    assert events.last_prompt.fronted == 1 and events.last_prompt.statuses == shown  # its message untouched
