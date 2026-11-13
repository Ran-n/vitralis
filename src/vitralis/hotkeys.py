#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.930185
Revised: 2026/11/14 00:23:15.779930

The two system-wide hooks, each on a thread of its own: the focus hotkey (F8 by default), which works from any
app, and the mouse wheel, which cycles the palette while Vitralis has the focus. Both stop cleanly whenever
``stop`` is called, even before the thread got to install anything.
"""

import logging
import sys
import threading

import keyboard
from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger("vitralis.hotkeys")

STOP_POLL_MS = 50
"""How often a stopping thread is asked again to end (its message queue may not exist yet the first time)."""


def is_valid_hotkey(hotkey: str) -> bool:
    """Whether the ``keyboard`` library knows every key in ``hotkey`` (Qt names some keys differently)."""
    if not hotkey:
        return False
    try:
        keyboard.parse_hotkey(hotkey)
    except ValueError:
        return False
    return True


class _HotkeySignals(QObject):
    toggle_focus = pyqtSignal()


class GlobalHotkeyThread(QThread):
    def __init__(self, parent: QObject | None = None, hotkey: str = "f8") -> None:
        super().__init__(parent)
        self.signals = _HotkeySignals()
        self._stopping = threading.Event()
        self._hotkey = hotkey

    def run(self) -> None:
        handle = None
        if self._hotkey:  # empty: the focus shortcut was given to another action
            try:
                handle = keyboard.add_hotkey(self._hotkey, self.signals.toggle_focus.emit)
            except Exception:  # an unknown key name, or the hook refused: the app must still run and quit
                logger.exception("couldn't register the global hotkey %r", self._hotkey)
        self._stopping.wait()
        if handle is not None:
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError) as ex:
                logger.warning("couldn't remove the global hotkey %r: %s", self._hotkey, ex)

    def stop(self) -> None:
        self._stopping.set()
        self.wait()


class _WheelSignals(QObject):
    scrolled = pyqtSignal(int)  # +1 or -1


if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    WH_MOUSE_LL = 14
    WM_MOUSEWHEEL = 0x020A
    WM_QUIT = 0x0012

    class _MouseHookInfo(ctypes.Structure):
        """MSLLHOOKSTRUCT."""

        _fields_ = [
            ("pt", ctypes.wintypes.POINT),
            ("mouseData", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    # LRESULT CALLBACK LowLevelMouseProc(int nCode, WPARAM wParam, LPARAM lParam); both results are pointer-sized
    _HookProc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

    # A library object of its own: declaring the prototypes on the shared ``ctypes.windll.user32`` would change
    # them for every other caller in the process. Every handle and pointer is declared, since ctypes passes an
    # undeclared one as a 32-bit int, which cuts a 64-bit handle short.
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int,
        _HookProc,
        ctypes.wintypes.HINSTANCE,
        ctypes.wintypes.DWORD,
    ]
    _user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
    _user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    _user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HHOOK,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    _user32.GetMessageW.argtypes = [
        ctypes.POINTER(ctypes.wintypes.MSG),
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.UINT,
    ]
    _user32.GetMessageW.restype = ctypes.c_int  # BOOL, but -1 on error
    _user32.PostThreadMessageW.argtypes = [
        ctypes.wintypes.DWORD,
        ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    _user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL

    class GlobalMouseWheelThread(QThread):
        """Low-level WH_MOUSE_LL hook that emits scrolled(step) for every wheel tick."""

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.signals = _WheelSignals()
            self._hook: int | None = None
            self._thread_id: int = 0
            self._stopping = threading.Event()
            self._callback = _HookProc(self._on_mouse)
            """Kept for as long as the thread object lives: Windows may still call it while the thread ends."""

        def _on_mouse(self, code: int, w_param: int, l_param: int) -> int:
            if code >= 0 and w_param == WM_MOUSEWHEEL:
                info = ctypes.cast(l_param, ctypes.POINTER(_MouseHookInfo)).contents
                delta = ctypes.c_short(info.mouseData >> 16).value
                self.signals.scrolled.emit(-1 if delta > 0 else 1)
            return _user32.CallNextHookEx(self._hook, code, w_param, l_param)

        def run(self) -> None:
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            # WH_MOUSE_LL is a global hook; hMod must be NULL (not GetModuleHandleW)
            self._hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, self._callback, None, 0)
            if not self._hook:
                logger.error("couldn't install the mouse wheel hook (error %d)", ctypes.get_last_error())

            msg = ctypes.wintypes.MSG()
            # the hook is called from inside GetMessageW; no window lives on this thread, so nothing to dispatch
            while not self._stopping.is_set() and _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass

            if self._hook:
                if not _user32.UnhookWindowsHookEx(self._hook):
                    logger.warning("couldn't remove the mouse wheel hook (error %d)", ctypes.get_last_error())
                self._hook = None

        def stop(self) -> None:
            """Ask the message loop to end until it has: the first WM_QUIT is lost when it is posted before the
            thread has a message queue."""
            self._stopping.set()
            while self.isRunning():
                if self._thread_id:
                    _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
                if self.wait(STOP_POLL_MS):
                    break

else:

    class GlobalMouseWheelThread(QThread):  # type: ignore[no-redef]
        """No-op stub on non-Windows platforms."""

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.signals = _WheelSignals()

        def run(self) -> None:
            pass

        def stop(self) -> None:
            self.wait()
