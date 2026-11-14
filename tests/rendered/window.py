#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 16:56:37.473064
Revised: 2026/11/14 16:56:37.473064

The rendered tests' hands and eyes on a real window: clicks and drags sent as posted window messages (the real
mouse and keyboard are never touched, so the user can go on working), and the window's pixels read with
PrintWindow, which works while the window is covered.
"""

import ctypes
import ctypes.wintypes
import time

from PyQt6.QtGui import QImage

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0200, 0x0201, 0x0202, 0x0204, 0x0205
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
KEY_UP = 0xC0000001
"""A key message's flags when the key is let go: it was down, and now goes up."""
MK_LBUTTON, MK_RBUTTON = 0x0001, 0x0002
PW_RENDERFULLCONTENT = 0x0002
"""Without it PrintWindow gives black for a window Windows composes (as Qt's translucent ones are)."""
SETTLE_SECONDS = 0.05

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32.PostMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
_user32.VkKeyScanW.restype = ctypes.c_short
_user32.GetClientRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
_user32.GetDC.argtypes = [ctypes.wintypes.HWND]
_user32.GetDC.restype = ctypes.wintypes.HDC
_user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]
_user32.PrintWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC, ctypes.c_uint]
_gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = ctypes.wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.GetDIBits.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.wintypes.HBITMAP,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
]


class _BitmapHeader(ctypes.Structure):
    """BITMAPINFOHEADER."""

    _fields_ = [
        ("size", ctypes.c_uint32),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("planes", ctypes.c_uint16),
        ("bits", ctypes.c_uint16),
        ("compression", ctypes.c_uint32),
        ("image_size", ctypes.c_uint32),
        ("x_per_metre", ctypes.c_int32),
        ("y_per_metre", ctypes.c_int32),
        ("colours", ctypes.c_uint32),
        ("important", ctypes.c_uint32),
    ]


def _post(hwnd: int, message: int, held: int, x: int, y: int) -> None:
    if not _user32.PostMessageW(hwnd, message, held, (y << 16) | (x & 0xFFFF)):
        raise OSError(f"couldn't post message {message:#x} to window {hwnd:#x} (error {ctypes.get_last_error()})")


def click(hwnd: int, x: int, y: int, right: bool = False) -> None:
    """A click at ``(x, y)`` of the window's client area, in its own pixels."""
    down, up, held = (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON) if right else (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON)
    _post(hwnd, WM_MOUSEMOVE, 0, x, y)
    _post(hwnd, down, held, x, y)
    _post(hwnd, up, 0, x, y)
    time.sleep(SETTLE_SECONDS)


def drag(hwnd: int, *points: tuple[int, int]) -> None:
    """Press at the first point, move through the others, let go at the last."""
    _post(hwnd, WM_MOUSEMOVE, 0, *points[0])
    _post(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, *points[0])
    for point in points[1:]:
        _post(hwnd, WM_MOUSEMOVE, MK_LBUTTON, *point)
    _post(hwnd, WM_LBUTTONUP, 0, *points[-1])
    time.sleep(SETTLE_SECONDS)


def type_text(hwnd: int, text: str) -> None:
    """Type ``text`` into whatever has the focus in the window, a posted key press per character (Qt works the
    character out from the key itself, so no WM_CHAR is sent: it would be typed twice)."""
    for character in text:
        key = _user32.VkKeyScanW(character) & 0xFF
        for message, flags in ((WM_KEYDOWN, 1), (WM_KEYUP, KEY_UP)):
            if not _user32.PostMessageW(hwnd, message, key, flags):
                raise OSError(f"couldn't post a key to window {hwnd:#x} (error {ctypes.get_last_error()})")
    time.sleep(SETTLE_SECONDS)


def capture(hwnd: int) -> QImage:
    """The window's client area as Windows draws it; where the window is clear the picture is black."""
    area = ctypes.wintypes.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(area)):
        raise OSError(f"window {hwnd:#x} is gone (error {ctypes.get_last_error()})")
    width, height = area.right, area.bottom
    screen = _user32.GetDC(hwnd)
    memory = _gdi32.CreateCompatibleDC(screen)
    bitmap = _gdi32.CreateCompatibleBitmap(screen, width, height)
    before = _gdi32.SelectObject(memory, bitmap)
    try:
        if not _user32.PrintWindow(hwnd, memory, PW_RENDERFULLCONTENT):
            raise OSError(f"couldn't capture window {hwnd:#x}")
        header = _BitmapHeader(ctypes.sizeof(_BitmapHeader), width, -height, 1, 32, 0)  # top row first
        pixels = ctypes.create_string_buffer(width * height * 4)
        _gdi32.SelectObject(memory, before)
        if _gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0) != height:
            raise OSError(f"couldn't read the pixels of window {hwnd:#x}")
    finally:
        _gdi32.SelectObject(memory, before)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(memory)
        _user32.ReleaseDC(hwnd, screen)
    return QImage(pixels.raw, width, height, width * 4, QImage.Format.Format_RGB32).copy()
