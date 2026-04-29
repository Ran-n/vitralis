#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:03.930185
Revised: 2026/04/29 07:54:21.432959
"""

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
