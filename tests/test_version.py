#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:12.387204
Revised: 2026/11/13 09:11:12.771237

What the app says about itself agrees with the repository: the licence name the About window shows carries
the version in ``LICENSE``, and the running version is the one in ``pyproject.toml``.
"""

import re
import tomllib
from pathlib import Path

from vitralis.version import LICENCE_NAME, USER_AGENT, app_version

ROOT = Path(__file__).parents[1]
VERSION_LINE = re.compile(r"^Version (\d+\.\d+)$", re.MULTILINE)


def licence_text() -> str:
    return (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_LICENSE_has_a_version_line():
    assert len(VERSION_LINE.findall(licence_text())) == 1


def test_the_about_licence_names_the_version_in_LICENSE():
    version = VERSION_LINE.search(licence_text()).group(1)
    expected = f"PayBack License (PBL) v{version}"
    assert expected == LICENCE_NAME


def test_the_running_version_is_the_one_in_pyproject():
    with (ROOT / "pyproject.toml").open("rb") as file:
        assert app_version() == tomllib.load(file)["project"]["version"]


def test_the_user_agent_names_the_version():
    assert USER_AGENT.removeprefix("vitralis/") == app_version()
