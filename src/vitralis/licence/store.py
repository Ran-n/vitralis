#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 09:18:57.247928
Revised: 2026/11/14 12:01:47.494483

The licence kept on this computer: ``licence.dat`` in the data folder, protected with Windows DPAPI for the
current user, so a copied file is useless on another computer or account. The product code is added as
entropy (``clavren:<product>``, as the Rust crate does), so one product's file can't stand in for another's.

Every write goes to a temporary file of its own and replaces the old one whole (``os.replace``), so a crash
never leaves half a file, even with two copies of Vitralis running: the last save wins.
"""

import ctypes
import logging
import os
import secrets
import sys
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Self

from vitralis.licence.ports import LicenceStoreError, LicenceStoreUnreadable

logger = logging.getLogger("vitralis.licence.store")

CRYPTPROTECT_UI_FORBIDDEN = 0x1

type Transform = Callable[[bytes], bytes]


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _call_dpapi(protect: bool, data: bytes, entropy: bytes) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    (source, _keep_source), (salt, _keep_salt) = _blob(data), _blob(entropy)
    output = _Blob()
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = call(
        ctypes.byref(source),
        None,
        ctypes.byref(salt),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise OSError(ctypes.GetLastError(), "DPAPI refused the licence data")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.memset(output.pbData, 0, output.cbData)  # it may hold the plain device key
        kernel32.LocalFree(output.pbData)


class DpapiProtector:
    """DPAPI in CurrentUser scope."""

    def __init__(self, product: str) -> None:
        self._entropy = f"clavren:{product}".encode()

    def protect(self, plain: bytes) -> bytes:
        return _call_dpapi(True, plain, self._entropy)

    def unprotect(self, protected: bytes) -> bytes:
        return _call_dpapi(False, protected, self._entropy)


class FileLicenceStore:
    def __init__(self, path: Path, protect: Transform, unprotect: Transform) -> None:
        self._path = path
        self._protect = protect
        self._unprotect = unprotect

    @classmethod
    def for_windows(cls, path: Path, product: str) -> Self:
        if sys.platform != "win32":
            raise RuntimeError("the licence store needs Windows (DPAPI)")
        dpapi = DpapiProtector(product)
        return cls(path, dpapi.protect, dpapi.unprotect)

    def load(self) -> bytes | None:
        try:
            protected = self._path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as ex:
            raise LicenceStoreUnreadable(f"{self._path}: {ex}") from ex
        try:
            return self._unprotect(protected)
        except OSError as ex:  # damaged, or another account's or computer's
            raise LicenceStoreError(f"{self._path} can't be unprotected: {ex}") from ex

    def save(self, data: bytes) -> None:
        temporary = self._path.with_name(f"{self._path.name}.{secrets.token_hex(6)}.tmp")
        try:
            protected = self._protect(data)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(protected)
            os.replace(temporary, self._path)
        except OSError as ex:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as left:  # held by another program: the save's own error is the one to tell
                logger.warning("couldn't delete %s: %s", temporary, left)
            raise LicenceStoreError(f"{self._path} can't be saved: {ex}") from ex
