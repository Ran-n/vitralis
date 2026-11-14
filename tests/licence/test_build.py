#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.686352
Revised: 2026/11/14 12:01:48.521473

The licence as the app builds it: product ``vitralis`` at clavren.breren.com, kept with DPAPI in the data
folder, nothing sent until a key is typed.
"""

import sys

import pytest

from vitralis.licence import LICENCE_FILE, PLATFORM, PRODUCT, build_licence
from vitralis.licence.rules import LicenceKind

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the licence store needs Windows (DPAPI)")


def test_the_built_licence_starts_unlicensed_and_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "BUILD-TEST")
    parts = build_licence(tmp_path)
    try:
        assert parts.licence.status().kind is LicenceKind.NEEDS_ACTIVATION
        assert not (tmp_path / LICENCE_FILE).exists()  # nothing saved before a key is typed
        config = parts.licence._config
        assert (config.product, config.platform, config.device_name) == (PRODUCT, PLATFORM, "BUILD-TEST")
        assert PRODUCT == "vitralis"
    finally:
        parts.close()
    assert parts.http.is_closed


def test_a_computer_without_a_name_is_still_named(tmp_path, monkeypatch):
    monkeypatch.delenv("COMPUTERNAME", raising=False)
    parts = build_licence(tmp_path)
    try:
        assert parts.licence._config.device_name == "computer"
    finally:
        parts.close()


def test_the_connection_is_left_open_under_a_request_still_running(tmp_path, caplog):
    """Regression guard: quitting on a stalled network closed the connection under the check using it."""
    import logging

    parts = build_licence(tmp_path)
    with caplog.at_level(logging.WARNING, "vitralis.licence"):
        parts.close(working=True)
    assert not parts.http.is_closed and any("still under way" in r.getMessage() for r in caplog.records)
    parts.close()
    assert parts.http.is_closed


def test_the_licence_server_is_only_ever_asked_over_https(tmp_path):
    import httpx
    import pytest

    from vitralis.net import InsecureAddress

    parts = build_licence(tmp_path)
    try:
        with pytest.raises(InsecureAddress, match="not HTTPS"):
            parts.http.post("http://clavren.breren.com/api/v1/activations", json={})
    finally:
        parts.close()
    assert isinstance(InsecureAddress("x"), httpx.RequestError) and not issubclass(
        InsecureAddress, httpx.TransportError
    )
