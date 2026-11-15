#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:49.546756
Revised: 2026/11/15 21:45:36.791991

Which build this is, and what its release files are called.

A release build has its target (``<os>-<arch>``) written into ``vitralis/_release.py`` by ``uv run build``
when ``VITRALIS_RELEASE_TARGET`` is set; any other copy is a build from source, which never checks for
updates and never replaces itself. The one rule for every release file's name lives here: the updater looks
for these names and the release workflow asks ``vitralis-asset-name`` for them, so the two can't drift apart.

A copy run from source (not the packaged exe) also reads the test overrides in ``OVERRIDES``; the packaged exe
ignores every one of them.
"""

import logging
import os
import sys
from functools import cache

from vitralis.updates.rules import Version, parse_version
from vitralis.version import app_version

logger = logging.getLogger("vitralis.updates.target")

APP = "vitralis"
TARGETS = ("windows-x86_64",)
"""Every target Vitralis is released for: it draws over the Windows desktop, so Windows on x86-64 only."""
RELEASE_TARGET_VARIABLE = "VITRALIS_RELEASE_TARGET"
SOURCES_VARIABLE = "VITRALIS_UPDATE_SOURCES"
"""``<github-url>|<gitlab-url>``: both sources asked elsewhere, plain HTTP allowed."""
KEY_VARIABLE = "VITRALIS_UPDATE_KEY"
"""A public key to trust instead of the built-in ones."""
DIR_VARIABLE = "VITRALIS_UPDATE_DIR"
"""The download folder, so tests never write to the real one."""
OVERRIDES = (RELEASE_TARGET_VARIABLE, SOURCES_VARIABLE, KEY_VARIABLE, DIR_VARIABLE)


def is_packaged() -> bool:
    """The PyInstaller exe, which can replace itself; a copy run from source can't."""
    return bool(getattr(sys, "frozen", False))


def override(name: str) -> str | None:
    """A test override's value, only ever in a copy run from source."""
    if is_packaged():
        return None
    return os.environ.get(name) or None


def _built_target() -> str | None:
    try:
        from vitralis._release import TARGET
    except ImportError:
        return None
    return TARGET


@cache
def release_target() -> str | None:
    """This build's target, or ``None`` for a build from source. An unknown value is logged once and counts
    as a build from source."""
    target = _built_target() if is_packaged() else override(RELEASE_TARGET_VARIABLE)
    if target is None:
        return None
    if target not in TARGETS:
        logger.warning("unknown release target %r: acting as a build from source", target)
        return None
    return target


def current_version() -> Version | None:
    try:
        return parse_version(app_version())
    except ValueError:
        return None


def asset_name(version: Version | str, target: str) -> str:
    """The portable exe: ``vitralis-1.4.0-windows-x86_64-portable.exe``. Both forms carry their marker, so the
    file says what it is."""
    return f"{APP}-{version}-{target}-portable.exe"


def installer_name(version: Version | str, target: str) -> str:
    """The installer: ``vitralis-1.4.0-windows-x86_64-setup.exe``. Never taken for the portable exe."""
    return f"{APP}-{version}-{target}-setup.exe"


def checksum_name(asset: str) -> str:
    return asset + ".b3"


def signature_name(asset: str) -> str:
    return asset + ".sig"


def is_asset_of(name: str, version: Version | str) -> bool:
    """Whether ``name`` is one of version ``version``'s release files (exe, installer, wheel or sdist)."""
    return name.startswith(f"{APP}-{version}-") or name == f"{APP}-{version}.tar.gz"


def asset_name_main(argv: list[str] | None = None) -> int:
    """``vitralis-asset-name <target>``: prints the portable exe's name for this checkout's version, so the
    release workflow never spells it out."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1 or arguments[0] not in TARGETS:
        print(f"usage: vitralis-asset-name <target>; targets: {', '.join(TARGETS)}", file=sys.stderr)
        return 2
    version = current_version()
    if version is None:
        print(f"this checkout's version isn't one: {app_version()!r}", file=sys.stderr)
        return 1
    print(asset_name(version, arguments[0]))
    return 0
