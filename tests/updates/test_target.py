#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:51.497372
Revised: 2026/11/15 21:45:44.237661

Which build this is and what its files are called: the packaged exe takes its target from ``_release.py`` and
ignores every override; a copy run from source is a build from source unless a test gives it a target; an
unknown target is a build from source; and ``vitralis-asset-name`` prints the name the updater looks for.
"""

import logging
import sys
import types

import pytest

from vitralis.updates import target
from vitralis.updates.rules import parse_version


@pytest.fixture
def packaged(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    def built_with(value):
        monkeypatch.setitem(sys.modules, "vitralis._release", types.SimpleNamespace(TARGET=value))
        target.release_target.cache_clear()

    return built_with


def test_a_copy_run_from_source_is_a_build_from_source():
    assert target.release_target() is None


def test_a_test_can_make_a_copy_run_from_source_a_release_build(monkeypatch):
    monkeypatch.setenv("VITRALIS_RELEASE_TARGET", "windows-x86_64")
    assert target.release_target() == "windows-x86_64"


def test_an_unknown_target_is_logged_and_is_a_build_from_source(monkeypatch, caplog):
    monkeypatch.setenv("VITRALIS_RELEASE_TARGET", "amiga-68k")
    with caplog.at_level(logging.WARNING, "vitralis.updates.target"):
        assert target.release_target() is None
    assert "amiga-68k" in caplog.text


def test_the_packaged_exe_takes_its_target_from_the_build_and_ignores_overrides(packaged, monkeypatch):
    monkeypatch.setenv("VITRALIS_RELEASE_TARGET", "windows-x86_64")
    packaged(None)
    assert target.release_target() is None  # built without one: a build from source, whatever the shell says
    packaged("windows-x86_64")
    assert target.release_target() == "windows-x86_64"
    for name in target.OVERRIDES:
        monkeypatch.setenv(name, "x")
        assert target.override(name) is None


def test_a_packaged_exe_built_before_release_targets_is_a_build_from_source(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setitem(sys.modules, "vitralis._release", None)  # import fails
    target.release_target.cache_clear()
    assert target.release_target() is None


def test_asset_names_carry_the_version_and_the_target():
    v = parse_version("1.4.0-rc.1")
    assert target.asset_name(v, "windows-x86_64") == "vitralis-1.4.0-rc.1-windows-x86_64-portable.exe"
    assert target.installer_name(v, "windows-x86_64") == "vitralis-1.4.0-rc.1-windows-x86_64-setup.exe"
    assert target.checksum_name("a.exe") == "a.exe.b3" and target.signature_name("a.exe") == "a.exe.sig"


@pytest.mark.parametrize(
    ("name", "mine"),
    [
        ("vitralis-1.4.0-windows-x86_64-portable.exe", True),
        ("vitralis-1.4.0-windows-x86_64-setup.exe", True),
        ("vitralis-1.4.0-py3-none-any.whl", True),
        ("vitralis-1.4.0.tar.gz", True),
        ("vitralis-1.4.1-windows-x86_64-portable.exe", False),
        ("vitralis-1.4.0.exe", False),
        ("other-1.4.0-windows-x86_64-portable.exe", False),
    ],
)
def test_a_file_is_one_of_a_versions_only_by_its_name(name, mine):
    assert target.is_asset_of(name, "1.4.0") is mine


def test_the_asset_name_helper_prints_the_exe_this_checkout_builds(capsys, monkeypatch):
    monkeypatch.setattr(target, "app_version", lambda: "1.4.0")
    assert target.asset_name_main(["windows-x86_64"]) == 0
    assert capsys.readouterr().out == "vitralis-1.4.0-windows-x86_64-portable.exe\n"


@pytest.mark.parametrize("arguments", [[], ["linux-x86_64"], ["windows-x86_64", "more"]])
def test_the_asset_name_helper_refuses_anything_but_one_target(capsys, arguments):
    assert target.asset_name_main(arguments) == 2
    assert "usage" in capsys.readouterr().err


def test_the_asset_name_helper_says_when_the_version_isnt_one(capsys, monkeypatch):
    monkeypatch.setattr(target, "app_version", lambda: "?")
    assert target.asset_name_main(["windows-x86_64"]) == 1
    assert "isn't one" in capsys.readouterr().err


def test_the_helper_and_the_updater_agree_on_the_name(monkeypatch):
    """The release workflow asks the helper; the updater looks for ``asset_name``: one rule for both."""
    import subprocess

    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from vitralis.updates.target import asset_name_main; asset_name_main(['windows-x86_64'])",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == target.asset_name(target.current_version(), "windows-x86_64")
