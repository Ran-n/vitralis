#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:58.341088
Revised: 2026/11/14 00:23:19.187809

The updater's rules, with no I/O and no Qt: release versions and how they compare, which release to offer,
the file names a release carries, the ``b3sum`` checksum format, and the errors an install can end in.
"""

import enum
import re
from dataclasses import dataclass

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_EXE = re.compile(r"vitralis-(\d+\.\d+\.\d+)\.exe")
_B3 = re.compile(r"([0-9a-fA-F]{64})(?:\s|$)")


@dataclass(frozen=True, slots=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(text: str) -> Version:
    """``v1.4.0`` or ``1.4.0``; anything else (``1.2``, ``v1.2.3-rc1``, ``?``) raises ``ValueError``."""
    found = _VERSION.fullmatch(text)
    if found is None:
        raise ValueError(f"not a version: {text!r}")
    return Version(*(int(part) for part in found.groups()))


def parse_version_or_none(text: str) -> Version | None:
    try:
        return parse_version(text)
    except ValueError:
        return None


def exe_name(version: Version) -> str:
    """The release's Windows exe, as ``build`` names it."""
    return f"vitralis-{version}.exe"


def checksum_name(version: Version) -> str:
    return exe_name(version) + ".b3"


def exe_version(file_name: str) -> Version | None:
    """The version in a ``vitralis-X.Y.Z.exe`` name, else ``None``."""
    found = _EXE.fullmatch(file_name)
    return None if found is None else parse_version(found.group(1))


def parse_b3(text: str) -> str:
    """The hash in a ``b3sum`` line (``"<64 hex>  <name>"``), lower case; ``ValueError`` on anything else."""
    found = _B3.match(text.strip())
    if found is None:
        raise ValueError("the checksum file isn't in b3sum format")
    return found.group(1).lower()


@dataclass(frozen=True, slots=True)
class Release:
    version: Version
    page_url: str
    exe_url: str | None
    checksum_url: str | None

    @property
    def installable(self) -> bool:
        """It carries both the exe and its checksum, which installing needs."""
        return self.exe_url is not None and self.checksum_url is not None


def is_newer(current: Version | None, latest: Release) -> bool:
    """A release counts as newer than an unknown running version, so a build without a version still hears."""
    return current is None or latest.version > current


def update_to_offer(current: Version | None, latest: Release, skipped: str) -> Release | None:
    """``latest`` when it is newer than the running version and than the skipped one (when that parses)."""
    if not is_newer(current, latest):
        return None
    skipped_version = parse_version_or_none(skipped)
    if skipped_version is not None and latest.version <= skipped_version:
        return None
    return latest


class FeedFailure(enum.Enum):
    """Why the latest release couldn't be read, as far as the user can do something about it."""

    OFFLINE = "offline"
    """GitHub couldn't be reached: no connection, a timeout, a broken one."""
    RATE_LIMITED = "rate_limited"
    """GitHub takes no more unauthenticated requests from this address for now."""
    OTHER = "other"
    """Anything else; the error's text is the reason."""


class UpdateError(Exception):
    """An install that couldn't finish; the message is a one-line reason."""


class DownloadUnreachable(UpdateError):
    """The download's server couldn't be reached, or the connection broke on the way."""


class ChecksumMismatch(UpdateError):
    """The downloaded exe isn't the one the release's checksum describes."""


class UpdateCancelled(UpdateError):
    """Vitralis quit during the download."""
