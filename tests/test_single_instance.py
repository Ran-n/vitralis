#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.047917
Revised: 2026/11/14 00:23:22.615078

One Vitralis per account, over a real local socket with a name of the test's own: the first start listens, a
second finds it and asks it to show itself, and once the first is gone the next start is the first again.
"""

import logging
import secrets

import pytest

from tests.conftest import wait_until
from vitralis import single_instance
from vitralis.single_instance import SingleInstance, default_name


@pytest.fixture
def name():
    return f"vitralis-test-{secrets.token_hex(6)}"


@pytest.fixture
def first(qapp, name):
    instance = SingleInstance(name)
    yield instance
    instance.close()


def test_the_first_start_finds_nobody_and_listens(first):
    assert first.notify_running() is False
    assert first.listen() is True


def test_a_second_start_finds_the_first_which_is_asked_to_show_itself(qapp, first, name):
    asked = []
    first.activated.connect(lambda: asked.append(1))
    first.listen()
    assert SingleInstance(name).notify_running() is True
    wait_until(qapp, lambda: asked == [1])


def test_once_the_first_is_gone_the_next_start_is_the_first(qapp, first, name):
    first.listen()
    first.close()
    first.close()  # twice is fine
    later = SingleInstance(name)
    assert later.notify_running() is False and later.listen() is True
    later.close()


def test_a_name_that_cant_be_listened_on_is_logged_and_not_fatal(qapp, first, name, monkeypatch, caplog):
    monkeypatch.setattr(single_instance.QLocalServer, "listen", lambda self, name: False)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert first.listen() is False
    assert any(name in r.getMessage() for r in caplog.records)
    first.close()  # nothing to close: still fine


def test_the_default_name_is_per_account(monkeypatch):
    monkeypatch.setattr(single_instance.getpass, "getuser", lambda: "ana")
    assert default_name() == "vitralis-ana"
    assert SingleInstance()._name == "vitralis-ana"


def test_an_unknown_account_still_gets_a_name(monkeypatch, caplog):
    def unknown():
        raise OSError("no user")

    monkeypatch.setattr(single_instance.getpass, "getuser", unknown)
    with caplog.at_level(logging.WARNING, "vitralis.single_instance"):
        assert default_name() == "vitralis-user"
    assert caplog.records
