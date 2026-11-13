#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:04.968289
Revised: 2026/11/13 09:11:15.328081

The running Vitralis version: the one ``build`` writes into ``_version.py`` for the packaged exe, else the
installed package's metadata.
"""

import logging
from functools import cache
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger("vitralis.version")

UNKNOWN = "?"
LICENCE_NAME = "PayBack License (PBL) v2.0"
"""The software licence, as the About window names it: must match the ``Version X.Y`` line of ``LICENSE``
(``tests/test_version.py`` checks it)."""


@cache
def app_version() -> str:
    try:
        from vitralis._version import __version__

        return __version__
    except ImportError:
        pass
    try:
        return version("vitralis")
    except PackageNotFoundError:
        logger.warning("the Vitralis version is unknown: no _version.py and no package metadata")
        return UNKNOWN


USER_AGENT = f"vitralis/{app_version()}"
"""How the app introduces itself to its licence server and to GitHub (which refuses requests without one)."""
