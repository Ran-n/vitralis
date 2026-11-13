#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 19:56:04.131186
Revised: 2026/11/13 19:56:29.473419

The installed-apps entry follows in-app updates: against a real registry key under ``HKEY_CURRENT_USER``, made
for each test the way Inno Setup writes it and deleted afterwards (the real installer's key is never touched).
"""

import logging
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the installed-apps entry is Windows's registry")

if sys.platform == "win32":
    import winreg

    from vitralis.updates.registration import INSTALLER_GUID, UNINSTALL_KEY, sync_installed_version


@pytest.fixture
def entry(tmp_path):
    """An Inno-style entry for an install in ``tmp_path``; yields ``(key path, installed exe)``."""
    path = rf"Software\VitralisTests\{uuid.uuid4()}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(tmp_path) + "\\")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.3.0")
        for name in ("MajorVersion", "VersionMajor"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        for name in ("MinorVersion", "VersionMinor"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 3)
    yield path, tmp_path / "Vitralis.exe"
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\VitralisTests") as parent:
        try:
            winreg.EnumKey(parent, 0)
        except OSError:  # no other test's key left: remove the parent too
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\VitralisTests")


def values(path: str) -> dict[str, object]:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        names = ("DisplayVersion", "MajorVersion", "VersionMajor", "MinorVersion", "VersionMinor")
        return {name: winreg.QueryValueEx(key, name)[0] for name in names}


def test_the_installed_exe_sets_its_version(entry, caplog):
    path, exe = entry
    with caplog.at_level(logging.INFO, "vitralis.updates.registration"):
        assert sync_installed_version(exe, "2.4.1", path)
    assert values(path) == {
        "DisplayVersion": "2.4.1",
        "MajorVersion": 2,
        "VersionMajor": 2,
        "MinorVersion": 4,
        "VersionMinor": 4,
    }
    assert any("1.3.0 -> 2.4.1" in r.getMessage() for r in caplog.records)


def test_the_same_version_changes_nothing(entry):
    path, exe = entry
    assert not sync_installed_version(exe, "1.3.0", path)
    assert values(path)["DisplayVersion"] == "1.3.0"


def test_a_portable_copy_elsewhere_leaves_the_entry_alone(entry, tmp_path_factory):
    path, _ = entry
    elsewhere = tmp_path_factory.mktemp("portable") / "vitralis-1.4.0.exe"
    assert not sync_installed_version(elsewhere, "1.4.0", path)
    assert values(path)["DisplayVersion"] == "1.3.0"


def test_a_version_without_numbers_still_shows_but_keeps_the_numbers(entry):
    path, exe = entry
    assert sync_installed_version(exe, "?", path)
    assert values(path) == {
        "DisplayVersion": "?",
        "MajorVersion": 1,
        "VersionMajor": 1,
        "MinorVersion": 3,
        "VersionMinor": 3,
    }


def test_no_entry_is_a_portable_exe_and_quiet(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, "vitralis.updates.registration"):
        assert not sync_installed_version(tmp_path / "Vitralis.exe", "1.4.0", rf"Software\VitralisTests\{uuid.uuid4()}")
    assert caplog.records == []


def test_an_unreadable_entry_is_logged(entry, caplog):
    path, exe = entry
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, "DisplayVersion")
    with caplog.at_level(logging.WARNING, "vitralis.updates.registration"):
        assert not sync_installed_version(exe, "1.4.0", path)
    assert any("can't be read" in r.getMessage() for r in caplog.records)


def test_a_failed_write_is_logged(entry, monkeypatch, caplog):
    path, exe = entry

    def refuse(*args):
        raise PermissionError("access denied")

    monkeypatch.setattr(winreg, "SetValueEx", refuse)
    with caplog.at_level(logging.WARNING, "vitralis.updates.registration"):
        assert not sync_installed_version(exe, "1.4.0", path)
    assert any("couldn't set" in r.getMessage() for r in caplog.records)


def test_the_key_is_the_one_inno_setup_writes_for_the_installer():
    prefix, name = UNINSTALL_KEY.rsplit("\\", 1)
    assert prefix == r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    assert name == "{" + INSTALLER_GUID + "}_is1"
    assert str(uuid.UUID(INSTALLER_GUID)).upper() == INSTALLER_GUID
