#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/29 07:52:06.389478
Revised: 2026/11/14 11:44:53.334414

``settings.json`` (``SettingsManager``) and the settings window: the keyboard shortcuts, the language, the
updates and the licence.
"""

import copy
import json
import logging
import re
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from vitralis.hotkeys import is_valid_hotkey
from vitralis.icons import flag_icon
from vitralis.installed import installer_language
from vitralis.licence.gate import LicenceGate
from vitralis.licence.section import LicenceSection
from vitralis.models import MAX_WIDTH, TOOL_NAMES
from vitralis.persistence import DATA_DIR, flush_writes, write_in_background
from vitralis.styles import base_btn, danger_btn, muted_btn
from vitralis.translations import set_language, t
from vitralis.updates.checker import UpdateChecker
from vitralis.updates.messages import UPDATES
from vitralis.updates.section import UpdatesSection

logger = logging.getLogger("vitralis.settings")

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")

SETTINGS_FILE = DATA_DIR / "settings.json"

# (language_code, display_name) — code maps to flags/flag_<code>.svg
LANGUAGES: list[tuple[str, str]] = [
    ("gl", "Galego"),
    ("gl-reintegrado", "Galego reintegrado"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("pt", "Português"),
    ("zh", "中文"),
    ("ja", "日本語"),
]

DEFAULT_LANGUAGE = "English"

_LANG_CODE: dict[str, str] = {label: code for code, label in LANGUAGES}
_LANG_LABELS: list[str] = [label for _, label in LANGUAGES]

DEFAULT_SHORTCUTS: dict[str, str] = {
    "focus_toggle": "f8",
    "draw": "d",
    "pan": "g",
    "delete": "x",
    "undo": "z",
    "clear": "delete",
    "hide": "h",
    "tool_pen": "p",
    "tool_eraser": "e",
    "tool_line": "l",
    "tool_arrow": "a",
    "tool_rect": "r",
    "tool_ellipse": "o",
    "size_down": "[",
    "size_up": "]",
    "quit": "ctrl+q",
}

_ACTION_KEYS: dict[str, str] = {
    "focus_toggle": "Focus / unfocus  (global)",
    "draw": "Toggle draw mode",
    "pan": "Toggle pan mode",
    "delete": "Toggle delete mode",
    "undo": "Undo",
    "clear": "Clear all",
    "hide": "Hide / show overlay",
    "tool_pen": "Tool: Pen",
    "tool_eraser": "Tool: Eraser",
    "tool_line": "Tool: Line",
    "tool_arrow": "Tool: Arrow",
    "tool_rect": "Tool: Rectangle",
    "tool_ellipse": "Tool: Ellipse",
    "size_down": "Decrease size",
    "size_up": "Increase size",
    "quit": "Quit",
}


GLOBAL_ACTION = "focus_toggle"
"""The one shortcut that works from any app: it goes through the ``keyboard`` library, not Qt."""


_saved: dict = {}
"""``settings.json`` as last read or changed: one table for every ``SettingsManager``."""


class SettingsManager:
    """``settings.json``. Several managers may be alive at once (the toolbar's, the updater's), so they all work
    on the one table in memory: one never undoes another's change. A new manager reads the file again; a
    change is written without waiting for the disk."""

    def __init__(self, language_source: Callable[[], str | None] | None = None) -> None:
        self._data = _saved
        self._installer_language = language_source or installer_language
        self._load()

    def _load(self) -> None:
        flush_writes()  # a change still on its way to the file must not be read over
        self._data.clear()
        if not SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            logger.warning("couldn't read %s, using the defaults: %s", SETTINGS_FILE, ex)
            return
        if isinstance(data, dict):
            self._data.update(data)
        else:
            logger.warning("%s isn't a JSON object, using the defaults", SETTINGS_FILE)

    def _put(self, key: str, value) -> None:
        self._data[key] = value
        write_in_background(SETTINGS_FILE, copy.deepcopy(self._data))  # a copy: the table goes on changing

    def shortcuts(self) -> dict[str, str]:
        """The saved shortcuts over the defaults; saved entries that aren't a known action with a text key are
        ignored. An empty key means the action has no shortcut."""
        saved = self._data.get("shortcuts", {})
        if not isinstance(saved, dict):
            logger.warning("the saved shortcuts aren't a table, using the defaults")
            saved = {}
        known = {a: k for a, k in saved.items() if a in DEFAULT_SHORTCUTS and isinstance(k, str)}
        return {**DEFAULT_SHORTCUTS, **known}

    def set_shortcuts(self, shortcuts: dict[str, str]) -> None:
        self._put("shortcuts", shortcuts)

    def language(self) -> str:
        """The one picked in Settings; before that, the installer's (see ``vitralis.installed``); else English."""
        saved = self._data.get("language")
        if saved in _LANG_LABELS:
            return saved
        if saved is not None:
            logger.warning("the saved language %r isn't one Vitralis has", saved)
        installed = self._installer_language()
        if installed is None:
            return DEFAULT_LANGUAGE
        if installed not in _LANG_LABELS:
            logger.warning("the installer's language %r isn't one Vitralis has; using %s", installed, DEFAULT_LANGUAGE)
            return DEFAULT_LANGUAGE
        return installed

    def set_language(self, lang: str) -> None:
        self._put("language", lang)

    def _updates(self) -> dict:
        saved = self._data.get("updates", {})
        return saved if isinstance(saved, dict) else {}

    def update_check(self) -> bool:
        """Whether Vitralis looks for new versions by itself (at start and once a day)."""
        return bool(self._updates().get("check", True))

    def set_update_check(self, enabled: bool) -> None:
        self._put("updates", {**self._updates(), "check": enabled})

    def skipped_version(self) -> str:
        """The release the user chose to skip, ``""`` for none."""
        skipped = self._updates().get("skipped", "")
        return skipped if isinstance(skipped, str) else ""

    def set_skipped_version(self, version: str) -> None:
        self._put("updates", {**self._updates(), "skipped": version})

    def toolbar_state(self) -> dict:
        """What the toolbar was left at: any of ``tool`` (a ``Tool`` name), ``color`` (``#rrggbb``), ``size``
        (a stroke width), ``position`` (``[x, y]``) and ``hidden`` (whether the drawings were hidden). Damaged
        entries are left out, so the toolbar falls back to its defaults for them."""
        saved = self._data.get("toolbar", {})
        if not isinstance(saved, dict):
            return {}
        state: dict = {}
        if saved.get("tool") in TOOL_NAMES:
            state["tool"] = saved["tool"]
        color = saved.get("color")
        if isinstance(color, str) and _HEX_COLOR.fullmatch(color):
            state["color"] = color.lower()
        size = saved.get("size")
        if isinstance(size, int) and not isinstance(size, bool) and 1 <= size <= MAX_WIDTH:
            state["size"] = size
        position = saved.get("position")
        if (
            isinstance(position, list)
            and len(position) == 2
            and all(isinstance(part, int) and not isinstance(part, bool) for part in position)
        ):
            state["position"] = position
        if isinstance(saved.get("hidden"), bool):
            state["hidden"] = saved["hidden"]
        return state

    def set_toolbar_state(self, **changes) -> None:
        """Remember the given parts of the toolbar's state; nothing is written when nothing changed."""
        saved = self._data.get("toolbar", {})
        current = saved if isinstance(saved, dict) else {}
        merged = {**current, **changes}
        if merged != current:
            self._put("toolbar", merged)


class _KeyCapture(QPushButton):
    captured = pyqtSignal(str)

    def __init__(self, current: str) -> None:
        super().__init__(self._display(current))
        self._listening = False
        self.setFixedSize(110, 26)
        self.setCheckable(True)
        self.setStyleSheet(muted_btn())
        self.clicked.connect(self._start_listen)

    @staticmethod
    def _display(key: str) -> str:
        return key.upper() if key else "—"

    def show_key(self, key: str) -> None:
        """Show ``key`` as this action's shortcut (``—`` for none)."""
        self.setText(self._display(key))

    def _start_listen(self) -> None:
        self._listening = True
        self.setText("…")
        self.setChecked(True)
        self.setStyleSheet(base_btn(bg="#1a5fa8", hover="#1a5fa8", checked="#1a5fa8"))
        self.grabKeyboard()

    def keyPressEvent(self, event) -> None:
        if not self._listening:
            return super().keyPressEvent(event)

        mods = event.modifiers()
        key = event.key()

        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")

        ks = QKeySequence(key).toString().lower()
        if ks:
            parts.append(ks)

        combo = "+".join(parts) if parts else ""
        self._stop_listen(combo)

    def _stop_listen(self, key: str) -> None:
        self._listening = False
        self.releaseKeyboard()
        self.setChecked(False)
        self.setStyleSheet(muted_btn())
        if key:
            self.setText(self._display(key))
            self.captured.emit(key)
        else:
            self.setText("—")


class SettingsWindow(QWidget):
    shortcuts_changed = pyqtSignal(dict)
    language_changed = pyqtSignal(str)
    activation_changed = pyqtSignal(bool)
    closed = pyqtSignal()

    def __init__(
        self,
        manager: SettingsManager,
        parent: QWidget | None = None,
        licence: LicenceGate | None = None,
        updates: UpdateChecker | None = None,
        quit_app: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self._manager = manager
        self._licence = licence
        self._licence_section: LicenceSection | None = None
        self._updates = updates
        self._quit_app = quit_app
        self.updates_section: UpdatesSection | None = None
        self._shortcuts = dict(manager.shortcuts())
        self._captures: dict[str, _KeyCapture] = {}
        self._dragging = False
        self._drag_pos = QPoint()
        self._action_labels: dict[str, QLabel] = {}
        self._reset_buttons: list[QPushButton] = []
        self._title: QLabel | None = None
        self._section_labels: list[tuple[QLabel, str]] = []
        self._lang_label: QLabel | None = None
        self._reset_all_btn: QPushButton | None = None

        self.setWindowTitle("Vitralis — Settings")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window
        )
        set_language(manager.language())
        self._build_ui()
        self.setFixedWidth(self.sizeHint().width())
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QWidget()
        panel.setObjectName("settings_panel")
        panel.setStyleSheet(
            "QWidget#settings_panel {"
            "  background: rgba(18,18,22,230);"
            "  border-radius: 10px;"
            "  border: 1px solid rgba(255,255,255,18);"
            "}"
        )
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(18, 14, 18, 14)
        inner.setSpacing(10)

        self._add_title_row(inner)
        self._add_section(inner, "Keyboard Shortcuts")
        self._add_shortcuts_rows(inner)
        self._add_section(inner, "Language")
        self._add_language_row(inner)
        if self._updates is not None:
            self._add_section(inner, UPDATES)
            self.updates_section = UpdatesSection(self._updates, quit_app=self._quit_app)
            inner.addWidget(self.updates_section)
        if self._licence is not None:
            self._add_section(inner, "License")
            self._licence_section = LicenceSection(self._licence)
            inner.addWidget(self._licence_section)
        self._add_footer(inner)

        root.addWidget(panel)

    def retranslate(self) -> None:
        for action, lbl in self._action_labels.items():
            lbl.setText(t(_ACTION_KEYS[action]))
        for lbl, key in self._section_labels:
            lbl.setText(t(key).upper())
        if self._lang_label:
            self._lang_label.setText(t("UI Language"))
        if self._reset_all_btn:
            self._reset_all_btn.setText(t("Reset all"))
        if self._title:
            self._title.setText(t("Settings"))
        for button in self._reset_buttons:
            button.setToolTip(t("Reset to default"))
        if self.updates_section is not None:
            self.updates_section.retranslate()
        if self._licence_section is not None:
            self._licence_section.retranslate()

    def _add_title_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        title = QLabel(t("Settings"))
        title.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        self._title = title

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(danger_btn())
        close_btn.clicked.connect(self.close)

        row.addWidget(title, stretch=1)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _add_section(self, layout: QVBoxLayout, title: str) -> None:
        layout.addSpacing(4)
        lbl = QLabel(t(title).upper())
        lbl.setStyleSheet(
            "color: rgba(255,255,255,90); font-size: 9px; font-weight: 700;"
            "letter-spacing: 1.5px; background: transparent;"
        )
        layout.addWidget(lbl)
        self._section_labels.append((lbl, title))

        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,18);")
        layout.addWidget(divider)

    def _add_shortcuts_rows(self, layout: QVBoxLayout) -> None:
        for action, key_str in _ACTION_KEYS.items():
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            lbl = QLabel(t(key_str))
            lbl.setStyleSheet("color: rgba(255,255,255,180); font-size: 11px; background: transparent;")
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._action_labels[action] = lbl

            cap = _KeyCapture(self._shortcuts.get(action, DEFAULT_SHORTCUTS[action]))
            cap.captured.connect(lambda key, a=action: self._on_captured(a, key))
            self._captures[action] = cap

            reset_btn = QPushButton("↺")
            reset_btn.setFixedSize(22, 22)
            reset_btn.setToolTip(t("Reset to default"))
            reset_btn.setStyleSheet(muted_btn())
            reset_btn.clicked.connect(lambda _, a=action: self._reset_action(a))
            self._reset_buttons.append(reset_btn)

            row.addWidget(lbl)
            row.addWidget(cap)
            row.addWidget(reset_btn)
            layout.addLayout(row)

    def _add_language_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        lbl = QLabel(t("UI Language"))
        lbl.setStyleSheet("color: rgba(255,255,255,180); font-size: 11px; background: transparent;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._lang_label = lbl

        combo = QComboBox()
        combo.setIconSize(QSize(20, 14))
        for code, label in LANGUAGES:
            combo.addItem(flag_icon(code), label)
        current = self._manager.language()
        if current in _LANG_LABELS:
            combo.setCurrentText(current)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        combo.setStyleSheet(
            "QComboBox {"
            "  background: rgba(255,255,255,7); color: #f0f0f0;"
            "  border: none; border-radius: 6px; padding: 2px 8px; font-size: 11px;"
            "}"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView {"
            "  background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,30);"
            "  selection-background-color: rgba(255,255,255,20);"
            "}"
        )
        combo.currentTextChanged.connect(self._on_language_changed)

        row.addWidget(lbl)
        row.addWidget(combo)
        layout.addLayout(row)

    def _add_footer(self, layout: QVBoxLayout) -> None:
        layout.addSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        reset_all = QPushButton(t("Reset all"))
        reset_all.setFixedHeight(26)
        reset_all.setStyleSheet(muted_btn())
        reset_all.clicked.connect(self._reset_all)
        self._reset_all_btn = reset_all

        row.addStretch()
        row.addWidget(reset_all)
        layout.addLayout(row)

    def _on_captured(self, action: str, key: str) -> None:
        self._assign(action, key)

    def _assign(self, action: str, key: str) -> None:
        """Give ``action`` the shortcut ``key``. A key the global hook can't take is refused for the focus
        shortcut (the old one stays); an action that already had ``key`` loses it, since one key for two
        actions would work for neither."""
        if action == GLOBAL_ACTION and not is_valid_hotkey(key):
            logger.warning("%r can't be a global shortcut: keeping %r", key, self._shortcuts[action])
            self._captures[action].show_key(self._shortcuts[action])
            return
        for other, other_key in self._shortcuts.items():
            if other != action and other_key == key:
                logger.info("%r moves from %s to %s", key, other, action)
                self._shortcuts[other] = ""
                self._captures[other].show_key("")
        self._shortcuts[action] = key
        self._captures[action].show_key(key)
        self._manager.set_shortcuts(self._shortcuts)
        self.shortcuts_changed.emit(dict(self._shortcuts))

    def _on_language_changed(self, lang: str) -> None:
        self._manager.set_language(lang)
        set_language(lang)
        self.retranslate()
        self.language_changed.emit(lang)

    def _reset_action(self, action: str) -> None:
        self._assign(action, DEFAULT_SHORTCUTS[action])

    def _reset_all(self) -> None:
        self._shortcuts = dict(DEFAULT_SHORTCUTS)
        for action, cap in self._captures.items():
            cap.show_key(DEFAULT_SHORTCUTS[action])
        self._manager.set_shortcuts(self._shortcuts)
        self.shortcuts_changed.emit(dict(self._shortcuts))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.ActivationChange:
            self.activation_changed.emit(self.isActiveWindow())
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self.activation_changed.emit(False)
        self.closed.emit()
        super().closeEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False

    def paintEvent(self, event) -> None:
        pass
