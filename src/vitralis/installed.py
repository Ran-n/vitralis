#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 19:56:03.727418
Revised: 2026/11/13 20:11:33.960447

What the installer leaves in the registry, under ``HKEY_CURRENT_USER``, and what Vitralis does with it.

- Its entry in Windows's installed apps (Settings → Apps). The installer writes the version once; an in-app
  update swaps the exe without the installer, so at start the packaged exe sets the entry to the version that
  really runs, but only from the folder the installer put it in: a portable copy elsewhere leaves it alone.
- The language the installer ran in, which Vitralis starts in until one is picked in Settings.
"""

import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg

from vitralis.updates.rules import parse_version_or_none

logger = logging.getLogger("vitralis.installed")

INSTALLER_GUID = "AB080C02-6AA8-4842-973A-AA93F9C4E128"
"""The installer's ``AppId`` (``installer/vitralis.iss`` gets it from ``build``). Never change it: Windows
would take a new one for another app, and installing over an old version would leave two entries."""
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{{{INSTALLER_GUID}}}_is1"
"""Where Inno Setup registers a per-user install, under ``HKEY_CURRENT_USER``."""
MAJOR_NAMES = ("MajorVersion", "VersionMajor")
MINOR_NAMES = ("MinorVersion", "VersionMinor")
"""Inno Setup writes the version's numbers under both names, as DWORDs, beside ``DisplayVersion``."""
APP_KEY = r"Software\Vitralis"
"""The installer's own key; ``installer/vitralis.iss`` deletes it on uninstall."""
LANGUAGE_VALUE = "Language"
"""A language as Settings names it (``Galego``, ``日本語``): the one the installer ran in."""


def _same_folder(install_location: str, exe: Path) -> bool:
    try:
        return Path(install_location).resolve() == exe.parent.resolve()
    except OSError:
        return False


def sync_installed_version(exe: Path, version: str, key_path: str = UNINSTALL_KEY) -> bool:
    """Set the installed-apps entry's version to ``version`` when ``exe`` is the installed one; whether it did.
    No entry (a portable exe) is normal and quiet; a registry failure is logged and tried again next start."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return False
    except OSError as ex:
        logger.warning("couldn't open the installed-apps entry: %s", ex)
        return False
    with key:
        try:
            location, _ = winreg.QueryValueEx(key, "InstallLocation")
            shown, _ = winreg.QueryValueEx(key, "DisplayVersion")
        except OSError as ex:
            logger.warning("the installed-apps entry can't be read: %s", ex)
            return False
        if not _same_folder(str(location), exe) or shown == version:
            return False
        try:
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            parsed = parse_version_or_none(version)
            if parsed is not None:
                for name in MAJOR_NAMES:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, parsed.major)
                for name in MINOR_NAMES:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, parsed.minor)
        except OSError as ex:
            logger.warning("couldn't set the installed-apps entry to %s: %s", version, ex)
            return False
    logger.info("installed-apps entry: %s -> %s", shown, version)
    return True


def installer_language(key_path: str = APP_KEY) -> str | None:
    """The language the installer ran in, or ``None`` (a portable exe, or not on Windows). An unreadable key is
    logged; the caller checks the name is a language it has."""
    if sys.platform != "win32":
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, kind = winreg.QueryValueEx(key, LANGUAGE_VALUE)
    except FileNotFoundError:
        return None
    except OSError as ex:
        logger.warning("couldn't read the installer's language: %s", ex)
        return None
    if kind != winreg.REG_SZ or not value:
        logger.warning("the installer's language isn't a name: %r", value)
        return None
    return value
