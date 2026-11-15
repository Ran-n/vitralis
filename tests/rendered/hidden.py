#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 21:39:56.081969
Revised: 2026/11/15 21:40:16.348906

The rendered tests' windows, kept off the user's screen: every window the driver shows is cloaked with DWM
before Windows first shows it, so it never appears on the screen, in the taskbar or in Alt+Tab, and it is
shown without being activated, so it never takes the foreground. A cloaked window is still visible to Win32:
it is painted, PrintWindow reads it and posted messages reach it, so the tests see what they always saw.
``VITRALIS_SHOW_TEST_WINDOW=1`` shows the windows, to watch a run.
"""

import ctypes
import ctypes.wintypes
import os

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QWidget

SHOW_VARIABLE = "VITRALIS_SHOW_TEST_WINDOW"
DWMWA_CLOAK = 13
DWMWA_CLOAKED = 14

_dwmapi = ctypes.WinDLL("dwmapi")
_dwmapi.DwmSetWindowAttribute.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
_dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
_dwmapi.DwmGetWindowAttribute.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


class CloakFailed(OSError):
    pass


def shown() -> bool:
    """Whether the run asked to see the windows."""
    return os.environ.get(SHOW_VARIABLE) == "1"


def cloak(hwnd: int) -> None:
    on = ctypes.c_int(1)
    result = _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CLOAK, ctypes.byref(on), ctypes.sizeof(on))
    if result != 0:
        raise CloakFailed(f"DwmSetWindowAttribute(DWMWA_CLOAK) on {hwnd:#x} failed: {result & 0xFFFFFFFF:#x}")


def is_cloaked(hwnd: int) -> bool:
    """Whether DWM keeps ``hwnd`` off the screen, for whatever reason."""
    value = ctypes.c_int(0)
    result = _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    if result != 0:
        raise CloakFailed(f"DwmGetWindowAttribute(DWMWA_CLOAKED) on {hwnd:#x} failed: {result & 0xFFFFFFFF:#x}")
    return value.value != 0


class Cloaker(QObject):
    """An application-wide event filter: a window about to show is cloaked first. Qt sends a widget its show
    event before it asks Windows to show the native window, so the window is never on the screen."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            watched.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            cloak(int(watched.winId()))
        return False
