#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:02.303928
Revised: 2026/11/13 09:11:02.685341

What Vitralis tells the user about updates, in the current UI language: the result of a check, the install
steps and their failures, the toolbar tooltip and the tray messages. Kept apart from the widgets so every
sentence is tested in every language without a window.
"""

from vitralis.translations import t
from vitralis.updates.checker import FailureKind, InstallKind, InstallState, UpdateStatus

UPDATES = "Updates"
CHECK_SWITCH = "Check for new versions"
RUNNING = "Version {version}"
OUT = "Vitralis {version} is out"
OUT_SKIPPED = "Vitralis {version} is out (skipped)"
UP_TO_DATE = "Vitralis {version} is up to date · checked {time}"
CHECK_FAILED = "Couldn't check for updates: {reason}"
RELEASE_NOTES = "Release notes"
SKIP = "Skip this version"
UNSKIP = "Don't skip"
SETTINGS_TIP = "Settings · Vitralis {version} is out"
INSTALL = "Install {version}"
DOWNLOADING_PERCENT = "Downloading {version}… {percent}%"
DOWNLOADING_MB = "Downloading {version}… {mb} MB"
RESTART = "Restart to update"
NOT_WRITABLE = "Can't update {dir}: move Vitralis to a folder you can write to, or update by hand"
DAMAGED = "The download is damaged (checksum mismatch): try again"
INSTALL_FAILED = "Couldn't install the update: {reason}"
UPDATED = "Updated to {version}"

ALL = (
    UPDATES,
    CHECK_SWITCH,
    RUNNING,
    OUT,
    OUT_SKIPPED,
    UP_TO_DATE,
    CHECK_FAILED,
    RELEASE_NOTES,
    SKIP,
    UNSKIP,
    SETTINGS_TIP,
    INSTALL,
    DOWNLOADING_PERCENT,
    DOWNLOADING_MB,
    RESTART,
    NOT_WRITABLE,
    DAMAGED,
    INSTALL_FAILED,
    UPDATED,
)
"""Every update sentence, so a test can check each is translated into every language."""


def result_line(status: UpdateStatus) -> str:
    """What the last successful check found; empty before the first one."""
    if status.latest is None:
        return ""
    if status.newer:
        return t(OUT if status.offered is not None else OUT_SKIPPED).format(version=status.latest.version)
    checked = "—" if status.checked_at is None else status.checked_at.strftime("%H:%M")
    return t(UP_TO_DATE).format(version=status.current, time=checked)


def error_line(status: UpdateStatus) -> str:
    return t(CHECK_FAILED).format(reason=status.error) if status.error else ""


def install_line(state: InstallState) -> str:
    """The download's progress, or why installing failed; empty otherwise."""
    if state.kind is InstallKind.DOWNLOADING:
        if state.percent is not None:
            return t(DOWNLOADING_PERCENT).format(version=state.version, percent=state.percent)
        return t(DOWNLOADING_MB).format(version=state.version, mb=state.received >> 20)
    if state.kind is InstallKind.FAILED:
        if state.failure is FailureKind.DAMAGED:
            return t(DAMAGED)
        if state.failure is FailureKind.NOT_WRITABLE:
            return t(NOT_WRITABLE).format(dir=state.detail)
        return t(INSTALL_FAILED).format(reason=state.detail)
    return ""


def settings_tooltip(status: UpdateStatus | None) -> str:
    if status is not None and status.offered is not None:
        return t(SETTINGS_TIP).format(version=status.offered.version)
    return t("Settings")


def out_message(status: UpdateStatus) -> str:
    return t(OUT).format(version=status.offered.version)


def updated_message(version: str) -> str:
    return t(UPDATED).format(version=version)
