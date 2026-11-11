#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.686352
Revised: 2026/11/11 11:06:54.559548

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
