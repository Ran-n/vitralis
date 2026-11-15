#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:02.303928
Revised: 2026/11/15 14:27:02.891755

What Vitralis tells the user about updates, in the current UI language: the result of a check, the install
steps and their failures, the toolbar tooltip and the tray messages. Kept apart from the widgets so every
sentence is tested in every language without a window. The wording is the same in every app of the family.
"""

from vitralis.translations import t
from vitralis.updates.checker import FailureKind, InstallKind, InstallState, UpdateStatus
from vitralis.updates.rules import FOLDER_NOT_WRITABLE, CheckKind, Failure, Reason

UPDATES = "Updates"
CHECK_SWITCH = "Check for updates automatically"
RUNNING = "Version {version} · {target}"
RUNNING_SOURCE = "Version {version} · built from source"
SOURCE_BUILD = "This copy was built from source. Update it with git pull and a new build."
UP_TO_DATE = "Vitralis is up to date (checked {time})."
AVAILABLE = "Vitralis {version} is available (checked {time})."
NO_BUILD = "Vitralis {version} is out, but has no build for this system yet."
SKIPPED = "Vitralis {version} is available; you chose to skip it (checked {time})."
CHECK_FAILED = "Couldn't check for updates: {reasons}."
RELEASE_NOTES = "Release notes"
SKIP = "Skip this version"
UNSKIP = "Stop skipping {version}"
SETTINGS_TIP = "Settings · Vitralis {version} is available"
UPDATE = "Update and restart"
CANCEL = "Cancel"
DOWNLOADING_PERCENT = "Downloading Vitralis {version}… {percent} %"
DOWNLOADING_MIB = "Downloading Vitralis {version}… {mib} MiB"
REPLACING = "Installing Vitralis {version}…"
DAMAGED = "The download of Vitralis {version} didn't match its checksum, so it wasn't installed."
NOT_SIGNED = "The download of Vitralis {version} isn't signed with Vitralis's release key, so it wasn't installed."
NOT_REPLACED = "Vitralis couldn't replace itself at {path}: {reason}. Download it from the release page instead: {page}"
NOT_DOWNLOADED = "Vitralis {version} couldn't be downloaded: {reason}. Try again, or download it from {page}"
OUT = "Vitralis {version} is available."
UPDATED = "Updated to {version}"

REASONS = tuple(reason.value for reason in Reason)
"""The network reasons, each a sentence to translate."""

ALL = (
    UPDATES,
    CHECK_SWITCH,
    RUNNING,
    RUNNING_SOURCE,
    SOURCE_BUILD,
    UP_TO_DATE,
    AVAILABLE,
    NO_BUILD,
    SKIPPED,
    CHECK_FAILED,
    RELEASE_NOTES,
    SKIP,
    UNSKIP,
    SETTINGS_TIP,
    UPDATE,
    CANCEL,
    DOWNLOADING_PERCENT,
    DOWNLOADING_MIB,
    REPLACING,
    DAMAGED,
    NOT_SIGNED,
    NOT_REPLACED,
    NOT_DOWNLOADED,
    FOLDER_NOT_WRITABLE,
    OUT,
    UPDATED,
    *REASONS,
)
"""Every update sentence, so a test can check each is translated into every language."""


def reason_text(failure: Failure) -> str:
    return t(failure.reason.value).format(status=failure.status)


def version_line(status: UpdateStatus) -> str:
    if status.target is None:
        return t(RUNNING_SOURCE).format(version=status.current)
    return t(RUNNING).format(version=status.current, target=status.target)


def _time(status: UpdateStatus) -> str:
    return "—" if status.checked_at is None else status.checked_at.strftime("%H:%M")


def result_line(status: UpdateStatus) -> str:
    """What the last check came to; empty before the first one."""
    version = "" if status.latest is None else str(status.latest.version)
    match status.kind:
        case CheckKind.SOURCE_BUILD:
            return t(SOURCE_BUILD)
        case CheckKind.UP_TO_DATE:
            return t(UP_TO_DATE).format(time=_time(status))
        case CheckKind.AVAILABLE:
            return t(AVAILABLE).format(version=version, time=_time(status))
        case CheckKind.NO_BUILD:
            return t(NO_BUILD).format(version=version)
        case CheckKind.SKIPPED:
            return t(SKIPPED).format(version=version, time=_time(status))
    return ""


def error_line(status: UpdateStatus) -> str:
    """Why the last check failed, each source's reason in order; empty when it worked."""
    if not status.failures:
        return ""
    reasons = "; ".join(f"{failure.source}: {reason_text(failure.failure)}" for failure in status.failures)
    return t(CHECK_FAILED).format(reasons=reasons)


def install_line(state: InstallState) -> str:
    """The download's progress, or why installing failed; empty otherwise."""
    if state.kind is InstallKind.DOWNLOADING:
        if state.percent is not None:
            return t(DOWNLOADING_PERCENT).format(version=state.version, percent=state.percent)
        return t(DOWNLOADING_MIB).format(version=state.version, mib=f"{state.received / (1 << 20):.1f}")
    if state.kind is InstallKind.REPLACING:
        return t(REPLACING).format(version=state.version)
    if state.kind is InstallKind.FAILED:
        if state.failure is FailureKind.DAMAGED:
            return t(DAMAGED).format(version=state.version)
        if state.failure is FailureKind.NOT_SIGNED:
            return t(NOT_SIGNED).format(version=state.version)
        if state.failure is FailureKind.NOT_REPLACED:
            reason = t(FOLDER_NOT_WRITABLE) if state.detail == FOLDER_NOT_WRITABLE else state.detail
            return t(NOT_REPLACED).format(path=state.path, reason=reason, page=state.page_url)
        reason = reason_text(state.reason) if state.reason is not None else state.detail
        return t(NOT_DOWNLOADED).format(version=state.version, reason=reason, page=state.page_url)
    return ""


def settings_tooltip(status: UpdateStatus | None) -> str:
    if status is not None and status.offer is not None:
        return t(SETTINGS_TIP).format(version=status.offer.release.version)
    return t("Settings")


def out_message(status: UpdateStatus) -> str:
    return t(OUT).format(version=status.offer.release.version)


def updated_message(version: str) -> str:
    return t(UPDATED).format(version=version)
