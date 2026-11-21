#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:58.341088
Revised: 2026/11/21 18:29:11.391686

The updater's rules, with no I/O and no Qt: versions (semantic versioning, pre-releases included) and how
they compare, the release a forge describes, what a check comes to (``decide``), the ``b3sum`` checksum
format, the short reasons a request can fail for, and the errors an install can end in.
"""

import enum
import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

_VERSION = re.compile(
    r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_B3 = re.compile(r"([0-9a-fA-F]{64})(?:\s|$)")
MAX_VERSION_LENGTH = 64
"""Longer than any version Vitralis will have; a saved or served one beyond it is refused unread."""


@functools.total_ordering
@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[str, ...] = ()
    """The pre-release identifiers (``("rc", "1")`` for ``1.4.0-rc.1``); empty for a release."""

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return f"{core}-{'.'.join(self.pre)}" if self.pre else core

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def _key(self) -> tuple:
        # semver precedence: a release ranks above its pre-releases; numeric identifiers below alphanumeric ones
        pre = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in self.pre)
        return self.major, self.minor, self.patch, not self.pre, pre

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()


def parse_version(text: str) -> Version:
    """``v1.4.0``, ``1.4.0`` or ``1.4.0-rc.1`` (build metadata ignored); anything else raises ``ValueError``."""
    found = _VERSION.fullmatch(text) if isinstance(text, str) and len(text) <= MAX_VERSION_LENGTH else None
    if found is None:
        raise ValueError(f"not a version: {text!r}")
    major, minor, patch, pre = found.groups()
    return Version(int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else ())


def parse_version_or_none(text: str) -> Version | None:
    try:
        return parse_version(text)
    except ValueError:
        return None


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
    assets: Mapping[str, str] = field(default_factory=dict)
    """File name → download URL, every one on HTTPS."""
    source: str = ""
    """The forge it came from (``GitHub``, ``GitLab``)."""


@dataclass(frozen=True, slots=True)
class Offer:
    """A release this build can install: the three files it needs, all present."""

    release: Release
    asset: str
    asset_url: str
    checksum_url: str
    signature_url: str


class CheckKind(enum.Enum):
    SOURCE_BUILD = "source_build"
    """Not a release build: nothing is asked, nothing is offered."""
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    NO_BUILD = "no_build"
    """Newer, but its exe, ``.b3`` or ``.minisig`` for this system is missing: never offered."""
    SKIPPED = "skipped"
    FAILED = "failed"


def is_offered_version(current: Version, candidate: Version) -> bool:
    """Newer, and not a pre-release unless the running version is one."""
    return candidate > current and (not candidate.is_prerelease or current.is_prerelease)


def decide(current: Version | None, release: Release, skipped: str, asset: str) -> tuple[CheckKind, Offer | None]:
    """What a successful check comes to. An unknown running version counts as older than any release."""
    floor = current if current is not None else Version(0, 0, 0, ("0",))
    if not is_offered_version(floor, release.version):
        return CheckKind.UP_TO_DATE, None
    urls = [release.assets.get(name) for name in (asset, asset + ".b3", asset + ".minisig")]
    if any(url is None for url in urls):
        return CheckKind.NO_BUILD, None
    skipped_version = parse_version_or_none(skipped)
    if skipped_version is not None and release.version <= skipped_version:
        return CheckKind.SKIPPED, None
    return CheckKind.AVAILABLE, Offer(release, asset, *urls)


def newest(releases: list[Release]) -> Release | None:
    """The newest; on a tie the earlier one, so the first source's files are used."""
    best: Release | None = None
    for release in releases:
        if best is None or release.version > best.version:
            best = release
    return best


class Reason(enum.Enum):
    """Why a request failed, short and with no URL or header in it; ``status`` fills ``ANSWERED``."""

    TIMED_OUT = "the request timed out"
    NOT_FOUND = "the server couldn't be found"
    CONNECTION = "the connection failed"
    TOO_LARGE = "the answer was too large"
    NOT_HTTPS = "the server didn't use HTTPS"
    TLS = "the secure connection failed"
    ANSWERED = "the server answered {status}"
    UNREADABLE = "the answer couldn't be read"


@dataclass(frozen=True, slots=True)
class Failure:
    reason: Reason
    status: int = 0
    """The HTTP status, for ``Reason.ANSWERED``."""


@dataclass(frozen=True, slots=True)
class SourceFailure:
    source: str
    failure: Failure


FOLDER_NOT_WRITABLE = "the folder can't be written to"
"""Why the exe can't be replaced when its folder takes no new files (the all-users Program Files, say)."""


class UpdateError(Exception):
    """An install that couldn't finish."""


class DownloadFailed(UpdateError):
    """The exe, its checksum or its signature couldn't be fetched."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.reason.value.format(status=failure.status))
        self.failure = failure


class ChecksumMismatch(UpdateError):
    """The downloaded exe isn't the one the release's checksum describes."""


class NotSigned(UpdateError):
    """The release's signature isn't by a key Vitralis trusts, or isn't for this version and file."""


class SwapFailed(UpdateError):
    """The downloaded exe couldn't be put in the running one's place, or started."""


class UpdateCancelled(UpdateError):
    """Cancel was pressed, or Vitralis quit, during the download."""
