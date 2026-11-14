#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.125637
Revised: 2026/11/14 12:01:47.288926

What Vitralis tells the user about its licence, in the current UI language: one message for each outcome, and
the dates the settings show. Kept apart from the widgets so every outcome's text is tested without a window.
"""

import datetime as dt

from vitralis.licence.rules import LicenceKind, LicenceStatus
from vitralis.translations import t

CONTACT = "ran.hash@proton.me"
"""Who to ask for a key, a reset or an extension."""
LOW_OFFLINE = dt.timedelta(days=5)
"""Under this long left offline, the settings highlight the date: time to connect."""

_MESSAGES: dict[LicenceKind, str] = {
    LicenceKind.LICENSED: "Vitralis is licensed on this computer.",
    LicenceKind.NEEDS_ACTIVATION: "Enter your license key to start Vitralis. No key yet? Ask {contact} for one.",
    LicenceKind.INVALID_KEY: "That key isn't valid for Vitralis. Check it and try again.",
    LicenceKind.ALREADY_ACTIVATED_ELSEWHERE: (
        "This key is already in use on another computer. To move it here, ask {contact} to reset it."
    ),
    LicenceKind.REVOKED: (
        "This license was revoked or moved to another computer. Enter a new key, or contact {contact}."
    ),
    LicenceKind.EXPIRED: "This license has expired. Contact {contact} to extend it.",
    LicenceKind.PRODUCT_UNAVAILABLE: "Vitralis licenses are unavailable at the moment. Contact {contact}.",
    LicenceKind.NEEDS_CHECK: "Vitralis needs to check its license online. Connect to the internet and check again.",
    LicenceKind.RATE_LIMITED: "Too many attempts. Wait {seconds} seconds and try again.",
    LicenceKind.UNREACHABLE: "The license server can't be reached. Check your internet connection and try again.",
    LicenceKind.SERVER_ERROR: (
        "The license server gave an answer Vitralis couldn't use. Try again later, or contact {contact}."
    ),
}
EXPIRED_ON = "This license expired on {date}. Contact {contact} to extend it."
SAVE_FAILED = "Vitralis couldn't save its license: {reason}"
PRIVACY = (
    "Your key is checked at clavren.breren.com. Once a day Vitralis confirms it there, "
    "sending this computer's name and the app version."
)
CHECKABLE = frozenset({LicenceKind.NEEDS_CHECK, LicenceKind.EXPIRED, LicenceKind.PRODUCT_UNAVAILABLE})
"""Outcomes an online check can change by itself, so the licence window offers one."""


def status_message(status: LicenceStatus) -> str:
    """The sentence for ``status`` in the current language."""
    if status.kind is LicenceKind.EXPIRED and status.licence_expires_at is not None:
        return t(EXPIRED_ON).format(date=format_date(status.licence_expires_at), contact=CONTACT)
    seconds = 0 if status.retry_after is None else max(1, round(status.retry_after.total_seconds()))
    return t(_MESSAGES[status.kind]).format(contact=CONTACT, seconds=seconds)


def save_failed_message(reason: str) -> str:
    return t(SAVE_FAILED).format(reason=reason)


def format_date(moment: dt.datetime) -> str:
    """``moment`` as a local calendar date, ``YYYY-MM-DD``: the same in every language."""
    return moment.astimezone().strftime("%Y-%m-%d")


def offline_running_low(status: LicenceStatus, server_now: dt.datetime) -> bool:
    """Whether the saved licence runs out offline within ``LOW_OFFLINE``, judged by the server's time."""
    return status.offline_until is not None and status.offline_until - server_now < LOW_OFFLINE
