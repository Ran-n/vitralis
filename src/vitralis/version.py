#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:04.968289
Revised: 2026/11/11 11:06:54.065947

The running Vitralis version: the one ``build`` writes into ``_version.py`` for the packaged exe, else the
installed package's metadata.
"""

import logging
from functools import cache
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger("vitralis.version")

UNKNOWN = "?"


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
