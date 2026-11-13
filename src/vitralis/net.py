#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:10:18.246169
Revised: 2026/11/13 09:11:13.249582

Which addresses Vitralis talks to: HTTPS, or plain HTTP to this computer only (tests and local end-to-end
checks), for the licence server, the release feed and the downloads alike.
"""

from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_secure_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS)
