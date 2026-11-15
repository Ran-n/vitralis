#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 22:44:53.727349
Revised: 2026/11/15 22:44:53.727349

The licence for the tests: a clock, an in-memory Clavren and store, a licence on them (activated or not),
and a gate wired to them with a fake daily checker and a fake prompt that record what they were told.
"""

import pytest

from tests.licence.fakes import KEY, START, FakeClavren, FakeClock, MemoryLicenceStore, licence_config
from vitralis.licence.client import Licence
from vitralis.licence.gate import LicenceGate
from vitralis.licence.rules import LicenceStatus


@pytest.fixture
def clock():
    return FakeClock(START)


@pytest.fixture
def server(clock):
    return FakeClavren(clock)


@pytest.fixture
def store():
    return MemoryLicenceStore()


@pytest.fixture
def licence(clock, server, store):
    return Licence(licence_config(), store, server, server.crypto(), clock)


class FakeChecks:
    """Stands in for ``LicenceChecks``: no thread; ``report`` plays the checker telling of a change."""

    def __init__(self) -> None:
        self.listeners = []
        self.started = 0
        self.stopped = 0
        self.running = False

    def subscribe(self, listener) -> None:
        self.listeners.append(listener)

    def start(self) -> None:
        self.started += 1

    def stop(self, timeout: float = 20.0) -> None:
        self.stopped += 1

    def report(self, status: LicenceStatus) -> None:
        for listener in self.listeners:
            listener(status)


class FakePrompt:
    """Stands in for ``LicenceWindow``: records what the gate asked it to show."""

    def __init__(self, gate) -> None:
        self.gate = gate
        self.statuses: list[LicenceStatus] = []
        self.errors: list[str] = []
        self.busy: list[bool] = []
        self.dismissed = False
        self.fronted = 0

    def show_status(self, status: LicenceStatus) -> None:
        self.statuses.append(status)

    def show_error(self, text: str) -> None:
        self.errors.append(text)

    def set_busy(self, busy: bool) -> None:
        self.busy.append(busy)

    def bring_to_front(self) -> None:
        self.fronted += 1

    def dismiss(self) -> None:
        self.dismissed = True


class Events:
    """What the gate did: unlocks, locks and the prompts it made."""

    def __init__(self) -> None:
        self.unlocks = 0
        self.locks = 0
        self.prompts: list[FakePrompt] = []

    def unlock(self) -> None:
        self.unlocks += 1

    def lock(self) -> None:
        self.locks += 1

    def prompt(self, gate) -> FakePrompt:
        self.prompts.append(FakePrompt(gate))
        return self.prompts[-1]

    @property
    def last_prompt(self) -> FakePrompt:
        return self.prompts[-1]


@pytest.fixture
def checks():
    return FakeChecks()


@pytest.fixture
def events():
    return Events()


@pytest.fixture
def make_gate(qapp, licence, checks, events):
    made: list[LicenceGate] = []

    def make(prompt=None) -> LicenceGate:
        gate = LicenceGate(licence, checks, events.unlock, events.lock, prompt or events.prompt)
        made.append(gate)
        return gate

    yield make
    for gate in made:
        gate.shutdown()


@pytest.fixture
def activated(licence):
    """The licence already activated on this computer, as on every start after the first."""
    assert licence.activate(KEY).licensed
    return licence
