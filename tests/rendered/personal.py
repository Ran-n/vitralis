#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 21:39:56.375498
Revised: 2026/11/15 21:40:17.196400

Nothing personal on the rendered tests' screens. Their pictures become committed baselines and README
pictures, and no scanner reads pixels, so the user's name must never reach the app under test: its scratch
folder sits under the shared profile (``%PUBLIC%``), not the user's Temp folder (whose path names them), and
every state the driver answers is searched for the account name and the profile folder's name.
"""

import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

SCRATCH_PARENT = "vitralis-tests"


class PersonalData(AssertionError):
    pass


def personal_names() -> tuple[str, ...]:
    """The account name and the profile folder's name (they can differ), the words that must not show."""
    names = {os.environ.get("USERNAME", ""), Path(os.environ.get("USERPROFILE", "")).name}
    return tuple(sorted(name for name in names if name))


def _pattern(names: tuple[str, ...]) -> re.Pattern[str] | None:
    """A name as a whole word or path component, ignoring case: ``C:\\Users\\ana`` matches ``ana``, ``banana``
    doesn't."""
    if not names:
        return None
    words = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?<![\w.-])(?:{words})(?![\w-])", re.IGNORECASE)


def find_personal(value: object, names: tuple[str, ...] | None = None) -> list[str]:
    """Where ``value`` (any JSON-like data, at any depth, keys and values) names the user."""
    pattern = _pattern(personal_names() if names is None else names)
    if pattern is None:
        return []
    found: list[str] = []
    for where, text in _texts(value, "state"):
        if pattern.search(text):
            found.append(f"{where}: {text!r}")
    return found


def _texts(value: object, where: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield f"{where} key", str(key)
            yield from _texts(item, f"{where}.{key}")
    elif isinstance(value, list | tuple | set):
        for index, item in enumerate(value):
            yield from _texts(item, f"{where}[{index}]")
    elif value is not None:
        yield where, str(value)


def refuse_personal(value: object) -> None:
    """Fail before anything can be captured when ``value`` names the user."""
    found = find_personal(value)
    if found:
        raise PersonalData("the app under test shows personal data: " + "; ".join(found))


def scratch_folder() -> Path:
    """A new, empty folder under ``%PUBLIC%\\vitralis-tests``, which every account can write to and whose path
    names nobody; it fails if its own path would name the user."""
    public = os.environ.get("PUBLIC")
    if not public:
        raise PersonalData("%PUBLIC% isn't set, so there is no scratch folder outside the user's profile")
    parent = Path(public) / SCRATCH_PARENT
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    try:
        refuse_personal(str(folder))
    except PersonalData:
        shutil.rmtree(folder)
        raise
    return folder


def remove_scratch(folder: Path) -> None:
    """Delete a scratch folder, and its parent once it is empty; what can't be deleted is raised."""
    shutil.rmtree(folder)
    parent = folder.parent
    if parent.name == SCRATCH_PARENT and not any(parent.iterdir()):
        parent.rmdir()
