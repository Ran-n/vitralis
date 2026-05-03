#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.930185
Revised: 2026/05/03 12:23:17.573326
"""

import sys

import keyboard
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class _HotkeySignals(QObject):
    toggle_focus = pyqtSignal()


class GlobalHotkeyThread(QThread):
    def __init__(self, parent: QObject | None = None, hotkey: str = "f8") -> None:
        super().__init__(parent)
        self.signals = _HotkeySignals()
        self._running = False
        self._hotkey = hotkey

    def run(self) -> None:
        keyboard.add_hotkey(self._hotkey, self.signals.toggle_focus.emit)
        self._running = True
        while self._running:
            self.msleep(50)
        keyboard.unhook_all()

    def stop(self) -> None:
        self._running = False
        self.wait()


class _WheelSignals(QObject):
    scrolled = pyqtSignal(int)  # +1 or -1


if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    class GlobalMouseWheelThread(QThread):
        """Low-level WH_MOUSE_LL hook that emits scrolled(step) for every wheel tick."""

        WH_MOUSE_LL = 14
        WM_MOUSEWHEEL = 0x020A

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.signals = _WheelSignals()
            self._hook: ctypes.wintypes.HHOOK | None = None
            self._thread_id: int = 0

        def run(self) -> None:
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            user32 = ctypes.windll.user32

            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("pt", ctypes.wintypes.POINT),
                    ("mouseData", ctypes.wintypes.DWORD),
                    ("flags", ctypes.wintypes.DWORD),
                    ("time", ctypes.wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                ]

            # LRESULT-returning callback; lParam is a pointer (c_longlong on 64-bit)
            HOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_longlong,
                ctypes.c_int,
                ctypes.wintypes.WPARAM,
                ctypes.c_longlong,
            )

            # Must declare argtypes so ctypes passes lParam as 64-bit, not c_long
            user32.CallNextHookEx.argtypes = [
                ctypes.wintypes.HHOOK,
                ctypes.c_int,
                ctypes.wintypes.WPARAM,
                ctypes.c_longlong,
            ]
            user32.CallNextHookEx.restype = ctypes.c_longlong

            def _hook_proc(nCode, wParam, lParam):
                if nCode >= 0 and wParam == self.WM_MOUSEWHEEL:
                    info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    delta = ctypes.c_short(info.mouseData >> 16).value
                    self.signals.scrolled.emit(-1 if delta > 0 else 1)
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            cb = HOOKPROC(_hook_proc)
            # WH_MOUSE_LL is a global hook; hMod must be NULL (not GetModuleHandleW)
            self._hook = user32.SetWindowsHookExW(self.WH_MOUSE_LL, cb, None, 0)

            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None

        def stop(self) -> None:
            if self._thread_id:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            self.wait()

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
