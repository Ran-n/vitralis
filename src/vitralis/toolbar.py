#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.341523
Revised: 2026/11/14 16:56:39.164982

The floating toolbar that drives the overlay (modes, tools, colours, size, undo, clear, hide) and opens its
windows (Settings, Snapshots, About, the colour picker). What it is left at is remembered for the next start:
the tool, colour, size and position, whether the drawings were hidden, and where each window sat beside it.
"""

import contextlib
import ctypes
import logging
from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from vitralis.about import InfoWindow
from vitralis.canvas import Canvas, DrawCapture
from vitralis.color_picker import ColorWindow
from vitralis.hotkeys import GlobalHotkeyThread, GlobalMouseWheelThread
from vitralis.icons import media_base, svg_icon
from vitralis.licence.gate import LicenceGate
from vitralis.models import Tool
from vitralis.settings import GLOBAL_ACTION, SettingsManager, SettingsWindow, display_key, key_hint
from vitralis.snapshots import SnapshotWindow
from vitralis.styles import (
    BTN_CHECKED,
    PALETTE,
    SIZES,
    TOOL_ICONS,
    accent_btn,
    base_btn,
    danger_btn,
    muted_btn,
    swatch_style,
)
from vitralis.translations import set_language, t
from vitralis.updates.checker import UpdateChecker, UpdateStatus
from vitralis.updates.messages import settings_tooltip
from vitralis.version import app_version
from vitralis.widgets import Divider

logger = logging.getLogger("vitralis.toolbar")

DEFAULT_SIZE = 5
"""The stroke width a first start draws with."""
DOT_GAP = 6
"""Between the toolbar's name and the dot that says whether Vitralis has the keyboard."""
PANEL_GAP = 8
"""How far right of the toolbar its windows open, until one is dragged elsewhere."""
DRAW, PAN, DELETE = "draw", "pan", "delete"
"""The modes: at most one is on, and while one is the captures take the mouse."""


def _on_a_screen(spot: QPoint) -> bool:
    """Whether some screen still shows ``spot`` (a monitor may be gone since it was saved)."""
    return any(screen.availableGeometry().contains(spot) for screen in QApplication.screens())


UPDATE_DOT_SIZE = 6
UPDATE_DOT_MARGIN = 2


class _DotButton(QPushButton):
    """A toolbar button that can carry a small accent dot at its top-right corner, painted over the button so its
    fixed size (and so the toolbar's locked width) never changes."""

    def __init__(self, icon, text: str = "") -> None:
        super().__init__(icon, text)
        self._dot = False

    @property
    def dot(self) -> bool:
        return self._dot

    def set_dot(self, shown: bool) -> None:
        if shown != self._dot:
            self._dot = shown
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._dot:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BTN_CHECKED))
        x = self.width() - UPDATE_DOT_SIZE - UPDATE_DOT_MARGIN
        painter.drawEllipse(x, UPDATE_DOT_MARGIN, UPDATE_DOT_SIZE, UPDATE_DOT_SIZE)
        painter.end()


class _TitleHeader(QWidget):
    """Header: top row of icon buttons, bottom row with logo+dot."""

    def __init__(self, icon_path, dot: QLabel, buttons: list, parent: QWidget = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        for w in buttons:
            btn_row.addWidget(w)
        root.addLayout(btn_row)

        root.addSpacing(6)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.setSpacing(0)
        logo_row.addStretch()
        logo_row.addSpacing(DOT_GAP + dot.width())  # as much as the dot takes on the right: the name stays centred
        self.name_parts: list[QLabel] = []
        """The logo and the name, which sit in the middle of the toolbar."""
        if icon_path and icon_path.exists():
            px = QPixmap(str(icon_path)).scaled(
                14, 14, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(px)
            icon_lbl.setFixedSize(14, 14)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            logo_row.addWidget(icon_lbl)
            self.name_parts.append(icon_lbl)
        text_lbl = QLabel("itralis")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lbl.setStyleSheet(
            "color: rgba(255,255,255,160); font-size: 11px; font-weight: 600;"
            "letter-spacing: 1.5px; background: transparent;"
        )
        logo_row.addWidget(text_lbl)
        self.name_parts.append(text_lbl)
        logo_row.addSpacing(DOT_GAP)
        logo_row.addWidget(dot)
        logo_row.addStretch()
        root.addLayout(logo_row)


class Toolbar(QWidget):
    language_changed = pyqtSignal()
    """The UI language changed in Settings, after the toolbar and its windows took it."""

    def __init__(
        self,
        canvases: list[Canvas],
        captures: list[DrawCapture],
        licence: LicenceGate | None = None,
        updates: UpdateChecker | None = None,
    ) -> None:
        super().__init__()
        self._licence = licence
        self._updates = updates
        self._update_status: UpdateStatus | None = None
        self.canvases = canvases
        self.captures = captures
        self._mode: str | None = None
        self._prev_hwnd: int | None = None
        self._quitting = False
        self._settings_manager = SettingsManager()
        saved = self._settings_manager.toolbar_state()
        self._tool = Tool[saved.get("tool", Tool.PEN.name)]
        self._color = saved.get("color", PALETTE[0])
        size = saved.get("size", DEFAULT_SIZE)
        self._size_index = SIZES.index(size if size in SIZES else DEFAULT_SIZE)
        self._saved_position: list[int] | None = saved.get("position")
        self._start_hidden: bool = saved.get("hidden", False)
        self._restoring = True
        """While the saved state is applied, nothing is written back."""
        self._panels: dict[str, QWidget] = {}
        """The toolbar's open windows by name, the one last used at the end: Esc on the toolbar closes that one."""
        self._panel_offsets: dict[str, list[int]] = dict(saved.get("panels", {}))
        """Where each window was left, from the toolbar's corner."""
        self._watched: list[Canvas] = []
        """The canvases whose changes Undo and Clear follow."""
        self._shortcut_keys: dict[str, str] = self._settings_manager.shortcuts()
        self._shortcuts: list[QShortcut] = []
        self._dragging = False
        self._drag_pos = QPoint()

        set_language(self._settings_manager.language())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis")

        self._build_ui()
        if self._start_hidden:
            self._toggle_visibility(True)  # the button shows it, so drawings left hidden don't look lost
        self._restoring = False
        self.sync_canvases()
        self.resize(self.sizeHint())
        self.setFixedWidth(self.width())
        if updates is not None:
            updates.changed.connect(self._show_update)
            self._show_update(updates.status)
        self._start_global_hotkeys()
        self._start_global_wheel_hook()
        self._focus_poll = QTimer(self)
        self._focus_poll.setInterval(150)
        self._focus_poll.timeout.connect(self._poll_focus)
        self._focus_poll.start()
        QApplication.instance().focusWindowChanged.connect(self._on_window_focused)

    @property
    def _drawing_active(self) -> bool:
        return self._mode == DRAW

    @property
    def _pan_active(self) -> bool:
        return self._mode == PAN

    @property
    def _delete_active(self) -> bool:
        return self._mode == DELETE

    @property
    def _settings_win(self) -> SettingsWindow | None:
        return self._panels.get("settings")

    @property
    def _snapshot_win(self) -> SnapshotWindow | None:
        return self._panels.get("snapshots")

    @property
    def _info_win(self) -> InfoWindow | None:
        return self._panels.get("info")

    @property
    def _color_win(self) -> ColorWindow | None:
        return self._panels.get("color")

    # ------------------------------------------------------------------
    # Hotkeys / focus
    # ------------------------------------------------------------------

    def _start_global_hotkeys(self) -> None:
        self._hotkey_thread = GlobalHotkeyThread(self, hotkey=self._shortcut_keys[GLOBAL_ACTION])
        self._hotkey_thread.signals.toggle_focus.connect(self._toggle_focus)
        self._hotkey_thread.start()

    def _start_global_wheel_hook(self) -> None:
        self._wheel_thread = GlobalMouseWheelThread(self)
        self._wheel_thread.signals.scrolled.connect(self._on_global_wheel)
        self._wheel_thread.start()

    def _on_global_wheel(self, step: int) -> None:
        """The wheel cycles the palette over the toolbar and while drawing, not over the toolbar's windows:
        there it scrolls a list or a language box, and must not change the colour behind it too."""
        if not self._foreground_is([self, *self.captures]):
            return
        base = self._color_index if self._color_index >= 0 else 0
        new_index = (base + step) % len(PALETTE)
        self._select_color(PALETTE[new_index], self._swatch_btns[new_index])

    def _restart_global_hotkey(self, shortcuts: dict) -> None:
        self._hotkey_thread.stop()
        self._hotkey_thread = GlobalHotkeyThread(self, hotkey=shortcuts.get(GLOBAL_ACTION, ""))
        self._hotkey_thread.signals.toggle_focus.connect(self._toggle_focus)
        self._hotkey_thread.start()
        self._apply_shortcuts(shortcuts)

    @staticmethod
    def _foreground_is(windows: list[QWidget]) -> bool:
        """Whether Windows's foreground window is one of ``windows``."""
        return ctypes.windll.user32.GetForegroundWindow() in {int(window.winId()) for window in windows}

    def _is_vitralis_focused(self) -> bool:
        return self._foreground_is([self, *self.captures, *(p for p in self._panels.values() if p.isVisible())])

    def _poll_focus(self) -> None:
        self._update_focus_dot(self._is_vitralis_focused())

    def _toggle_focus(self) -> None:
        if self._is_vitralis_focused():
            self.hide_toolbar()
            if self._prev_hwnd:
                ctypes.windll.user32.SetForegroundWindow(self._prev_hwnd)
                self._prev_hwnd = None
        else:
            self._prev_hwnd = ctypes.windll.user32.GetForegroundWindow()
            self.show()
            self.raise_()
            self.activateWindow()
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            fg_thread = user32.GetWindowThreadProcessId(self._prev_hwnd, None)
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(fg_thread, cur_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fg_thread, cur_thread, False)

    def hide_toolbar(self) -> None:
        """Hide the toolbar, leaving any mode first: with the toolbar gone the captures would go on taking every
        click, and it must not come back saying "Drawing…" over hidden captures."""
        self.stop_modes()
        self.hide()

    def show_toolbar(self) -> None:
        """Show the toolbar in front of everything (the tray, or another start of Vitralis, asked for it)."""
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(5)

        self._add_title_row(root)
        root.addWidget(Divider())
        self._add_mode_buttons(root)
        root.addWidget(Divider())
        self._add_tool_grid(root)
        root.addWidget(Divider())
        self._add_color_palette(root)
        root.addWidget(Divider())
        self._add_size_row(root)
        root.addWidget(Divider())
        self._add_action_row(root)
        root.addWidget(Divider())
        self._add_snapshot_row(root)

        self._select_tool(self._tool)
        swatch = self._swatch_btns[PALETTE.index(self._color)] if self._color in PALETTE else None
        self._select_color(self._color, swatch)
        self._mode_btns = {DRAW: self._draw_btn, PAN: self._pan_btn, DELETE: self._del_btn}
        self._update_size_buttons()
        self._setup_shortcuts()

    def _add_title_row(self, root: QVBoxLayout) -> None:
        base = media_base()

        self._focus_dot = QLabel()
        self._focus_dot.setFixedSize(10, 10)
        self._focus_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_focus_dot(False)

        self._settings_btn = _DotButton(svg_icon("settings", 14), "")
        self._settings_btn.setToolTip(t("Settings"))
        self._settings_btn.setFixedSize(26, 26)
        self._settings_btn.setStyleSheet(muted_btn())
        self._settings_btn.clicked.connect(self.open_settings)

        self._info_btn = QPushButton(svg_icon("info", 14), "")
        self._info_btn.setToolTip(t("About"))
        self._info_btn.setFixedSize(26, 26)
        self._info_btn.setStyleSheet(muted_btn())
        self._info_btn.clicked.connect(self._open_info)

        _spacer = QWidget()
        _spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._quit_btn = QPushButton(svg_icon("quit", 14), "")
        self._quit_btn.setFixedSize(26, 26)
        self._quit_btn.setStyleSheet(danger_btn())
        self._quit_btn.clicked.connect(self.quit)

        header = self._header = _TitleHeader(
            icon_path=base / "media" / "logo" / "icon.png",
            dot=self._focus_dot,
            buttons=[self._settings_btn, self._info_btn, _spacer, self._quit_btn],
            parent=self,
        )
        root.addWidget(header)

    def _add_mode_buttons(self, root: QVBoxLayout) -> None:
        self._draw_btn = QPushButton(svg_icon("draw", 16), t("Draw"))
        self._draw_btn.setCheckable(True)
        self._draw_btn.setFixedHeight(34)
        self._draw_btn.setIconSize(self._draw_btn.sizeHint())
        self._draw_btn.setStyleSheet(accent_btn())
        self._draw_btn.clicked.connect(self._toggle_drawing)
        root.addWidget(self._draw_btn)

        self._pan_btn = QPushButton(svg_icon("pan", 14), t("Pan"))
        self._pan_btn.setCheckable(True)
        self._pan_btn.setFixedHeight(28)
        self._pan_btn.setStyleSheet(muted_btn())
        self._pan_btn.clicked.connect(self._toggle_pan)
        root.addWidget(self._pan_btn)

        self._del_btn = QPushButton(svg_icon("delete", 14), t("Delete"))
        self._del_btn.setCheckable(True)
        self._del_btn.setFixedHeight(28)
        self._del_btn.setStyleSheet(muted_btn())
        self._del_btn.clicked.connect(self._toggle_delete)
        root.addWidget(self._del_btn)

    def _add_tool_grid(self, root: QVBoxLayout) -> None:
        self._tool_btns: dict[Tool, QPushButton] = {}
        tool_list = list(TOOL_ICONS.items())
        for row in range(3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(3)
            for col in range(2):
                tool, (icon_name, _name) = tool_list[row * 2 + col]
                btn = QPushButton(svg_icon(icon_name, 18), "")
                btn.setFixedSize(36, 32)
                btn.setCheckable(True)
                btn.setStyleSheet(base_btn())
                btn.clicked.connect(lambda checked, tool=tool: self._select_tool(tool))
                row_layout.addWidget(btn)
                self._tool_btns[tool] = btn
            root.addLayout(row_layout)

    def _add_color_palette(self, root: QVBoxLayout) -> None:
        self._color_index = -1
        self._swatch_btns: list[QPushButton] = []
        for row_start in range(0, len(PALETTE), 5):
            swatch_row = QHBoxLayout()
            swatch_row.setSpacing(3)
            for i in range(row_start, min(row_start + 5, len(PALETTE))):
                hex_color = PALETTE[i]
                btn = QPushButton()
                btn.setFixedSize(18, 18)
                btn.setToolTip(hex_color)
                btn.setCheckable(True)
                btn.setStyleSheet(swatch_style(hex_color, False))
                btn.clicked.connect(lambda _, c=hex_color, b=btn: self._select_color(c, b))
                self._swatch_btns.append(btn)
                swatch_row.addWidget(btn)
            root.addLayout(swatch_row)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(3)
        self._custom_btn = QPushButton()
        self._custom_btn.setFixedSize(18, 18)
        self._custom_btn.setToolTip(t("Custom color…"))
        self._custom_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #f00, stop:0.17 #ff0, stop:0.33 #0f0,"
            "stop:0.5 #0ff, stop:0.67 #00f, stop:0.83 #f0f, stop:1 #f00);"
            "border: none; border-radius: 3px; }"
            "QPushButton:hover { border: 1px solid white; }"
        )
        self._custom_btn.setIcon(svg_icon("plus", 10))
        self._custom_btn.clicked.connect(self._pick_custom_color)
        custom_row.addStretch()
        custom_row.addWidget(self._custom_btn)
        custom_row.addStretch()
        root.addLayout(custom_row)

    def _add_size_row(self, root: QVBoxLayout) -> None:
        size_row = QHBoxLayout()
        size_row.setSpacing(4)

        self._size_text_lbl = QLabel(t("Size"))
        self._size_text_lbl.setStyleSheet("color: rgba(255,255,255,110); font-size: 10px;")
        size_row.addWidget(self._size_text_lbl)
        size_row.addStretch()

        self._minus_btn = QPushButton(svg_icon("minus", 12), "")
        self._minus_btn.setFixedSize(24, 22)
        self._minus_btn.setStyleSheet(muted_btn())
        self._minus_btn.clicked.connect(self._size_down)

        self._size_lbl = QLabel(str(SIZES[self._size_index]))
        self._size_lbl.setFixedWidth(24)
        self._size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
        self._size_lbl.setToolTip(t("Current stroke size (px)"))

        self._plus_btn = QPushButton(svg_icon("plus", 12), "")
        self._plus_btn.setFixedSize(24, 22)
        self._plus_btn.setStyleSheet(muted_btn())
        self._plus_btn.clicked.connect(self._size_up)

        size_row.addWidget(self._minus_btn)
        size_row.addWidget(self._size_lbl)
        size_row.addWidget(self._plus_btn)
        root.addLayout(size_row)

    def _add_action_row(self, root: QVBoxLayout) -> None:
        act_row = QHBoxLayout()
        act_row.setSpacing(3)

        self._undo_btn = QPushButton(svg_icon("undo", 16), "")
        self._undo_btn.setFixedSize(36, 28)
        self._undo_btn.setStyleSheet(muted_btn())
        self._undo_btn.clicked.connect(self._undo)

        self._vis_btn = QPushButton(svg_icon("hide", 16), "")
        self._vis_btn.setCheckable(True)
        self._vis_btn.setFixedSize(36, 28)
        self._vis_btn.setStyleSheet(muted_btn())
        self._vis_btn.clicked.connect(self._toggle_visibility)

        self._clear_btn = QPushButton(svg_icon("clear", 16), "")
        self._clear_btn.setFixedSize(36, 28)
        self._clear_btn.setStyleSheet(muted_btn())
        self._clear_btn.clicked.connect(self._clear)

        for b in (self._undo_btn, self._vis_btn, self._clear_btn):
            act_row.addWidget(b)
        root.addLayout(act_row)

    def _add_snapshot_row(self, root: QVBoxLayout) -> None:
        self._snapshot_btn = QPushButton(svg_icon("snapshot", 14), t("Snapshots"))
        self._snapshot_btn.setToolTip(t("Snapshots"))
        self._snapshot_btn.setFixedHeight(28)
        self._snapshot_btn.setStyleSheet(muted_btn())
        self._snapshot_btn.clicked.connect(self._open_snapshots)
        root.addWidget(self._snapshot_btn)

    def _update_focus_dot(self, focused: bool) -> None:
        focus_key = self._shortcut_keys[GLOBAL_ACTION]
        if focused:
            color, glow = "#44dd88", "rgba(68,221,136,120)"
            tip = t("Focused")
        else:
            color, glow = "#e07020", "rgba(224,112,32,120)"
            tip = t("Unfocused  ·  {key} to focus").format(key=display_key(focus_key)) if focus_key else t("Unfocused")
        self._focus_dot.setToolTip(tip)
        self._focus_dot.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 5px; border: 1px solid {glow}; }}"
        )

    def _refresh_hints(self) -> None:
        """The tooltips, each with the shortcut its action has now (none when it has none): after a language
        change, and whenever the shortcuts change in Settings."""
        keys = self._shortcut_keys
        focus_key = keys[GLOBAL_ACTION]
        quit_keys = " / ".join(["ESC", *([display_key(keys["quit"])] if keys["quit"] else [])])
        self._quit_btn.setToolTip(f"{t('Quit')}  [{quit_keys}]")
        draw_tip = key_hint(t("Activate drawing mode"), keys["draw"])
        if focus_key:
            draw_tip += "  ·  " + t("Focus: {key}").format(key=display_key(focus_key))
        self._draw_btn.setToolTip(draw_tip)
        self._pan_btn.setToolTip(key_hint(t("Drag to shift all drawings on the overlay"), keys["pan"]))
        self._del_btn.setToolTip(key_hint(t("Click near any stroke to remove it"), keys["delete"]))
        self._minus_btn.setToolTip(key_hint(t("Decrease stroke size"), keys["size_down"]))
        self._plus_btn.setToolTip(key_hint(t("Increase stroke size"), keys["size_up"]))
        self._undo_btn.setToolTip(key_hint(t("Undo"), keys["undo"]))
        self._clear_btn.setToolTip(key_hint(t("Clear all"), keys["clear"]))
        hidden = self._vis_btn.isChecked()
        self._vis_btn.setToolTip(key_hint(t("Show overlay") if hidden else t("Hide overlay"), keys["hide"]))
        for tool, button in self._tool_btns.items():
            icon_name, name = TOOL_ICONS[tool]
            button.setToolTip(key_hint(t(name), keys[f"tool_{icon_name}"]))
        self._update_focus_dot(self._is_vitralis_focused())

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Escape"), self, activated=self._esc)
        self._apply_shortcuts(self._settings_manager.shortcuts())

    @property
    def mode_active(self) -> bool:
        return self._drawing_active or self._pan_active or self._delete_active

    def stop_modes(self) -> None:
        """Leave draw, pan and delete mode, whichever is on."""
        if self._mode is not None:
            self._mode = None
            self._show_mode()

    def _esc(self) -> None:
        """Esc closes the window last used, else leaves the active mode, and only quits when idle."""
        if self._panels:
            list(self._panels.values())[-1].close()
        elif self.mode_active:
            self.stop_modes()
        else:
            self.quit()

    def _apply_shortcuts(self, sc_map: dict) -> None:
        for s in self._shortcuts:
            s.setEnabled(False)
            s.deleteLater()
        self._shortcuts.clear()
        self._shortcut_keys = {**self._shortcut_keys, **sc_map}
        self._refresh_hints()

        def sc(key: str, fn) -> None:
            if not key:
                return
            s = QShortcut(QKeySequence(key), self, activated=fn)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._shortcuts.append(s)

        sc(sc_map.get("draw", "d"), lambda: self._toggle_drawing(not self._drawing_active))
        sc(sc_map.get("pan", "g"), lambda: self._toggle_pan(not self._pan_active))
        sc(sc_map.get("delete", "x"), lambda: self._toggle_delete(not self._delete_active))
        sc(sc_map.get("undo", "z"), self._undo)
        sc(sc_map.get("clear", "delete"), self._clear)
        sc(sc_map.get("hide", "h"), lambda: self._toggle_visibility(not self._vis_btn.isChecked()))
        sc(sc_map.get("quit", "ctrl+q"), self.quit)
        sc(sc_map.get("tool_pen", "p"), lambda: self._select_tool(Tool.PEN))
        sc(sc_map.get("tool_eraser", "e"), lambda: self._select_tool(Tool.ERASER))
        sc(sc_map.get("tool_line", "l"), lambda: self._select_tool(Tool.LINE))
        sc(sc_map.get("tool_arrow", "a"), lambda: self._select_tool(Tool.ARROW))
        sc(sc_map.get("tool_rect", "r"), lambda: self._select_tool(Tool.RECT))
        sc(sc_map.get("tool_ellipse", "o"), lambda: self._select_tool(Tool.ELLIPSE))
        sc(sc_map.get("size_down", "["), self._size_down)
        sc(sc_map.get("size_up", "]"), self._size_up)

    def _open_panel(self, name: str, make: Callable[[], QWidget]) -> QWidget:
        """Open the window ``name`` where it was left beside the toolbar, or bring the open one to the front."""
        panel = self._panels.pop(name, None)
        if panel is None:
            panel = make()
            panel.closed.connect(lambda name=name: self._on_panel_closed(name))
            panel.move(self._panel_spot(name))
            panel.show()
        else:
            panel.raise_()
            panel.activateWindow()
        self._panels[name] = panel  # the last one: Esc on the toolbar closes it first
        return panel

    def _default_offset(self) -> QPoint:
        frame = self.frameGeometry()
        return QPoint(frame.right() + PANEL_GAP - self.x(), frame.top() - self.y())

    def _panel_spot(self, name: str) -> QPoint:
        """Where the window ``name`` opens: where it was left, from the toolbar's corner, when a screen still
        shows that spot; else right of the toolbar."""
        left = self._panel_offsets.get(name)
        if left is not None and _on_a_screen(self.pos() + QPoint(*left)):
            return self.pos() + QPoint(*left)
        return self.pos() + self._default_offset()

    def _on_panel_closed(self, name: str) -> None:
        panel = self._panels.pop(name, None)
        if panel is None:
            return
        offset, default = panel.pos() - self.pos(), self._default_offset()
        left = [offset.x(), offset.y()]
        if left != self._panel_offsets.get(name, [default.x(), default.y()]):  # it was dragged: remember where to
            self._panel_offsets[name] = left
            self._remember(panels=dict(self._panel_offsets))

    def _on_window_focused(self, window) -> None:
        """Keep the open windows in the order they were last used."""
        for name, panel in self._panels.items():
            if window is not None and panel.windowHandle() == window:
                self._panels[name] = self._panels.pop(name)
                return

    def _open_info(self) -> None:
        self._open_panel("info", lambda: InfoWindow(app_version(), parent=None))

    def _show_update(self, status: UpdateStatus) -> None:
        """The accent dot and the tooltip on the Settings button while a new version is offered."""
        self._update_status = status
        self._settings_btn.set_dot(status.offered is not None)
        self._settings_btn.setToolTip(settings_tooltip(status))

    def open_settings(self) -> None:
        def make() -> SettingsWindow:
            window = SettingsWindow(
                self._settings_manager, parent=None, licence=self._licence, updates=self._updates, quit_app=self.quit
            )
            window.shortcuts_changed.connect(self._restart_global_hotkey)
            window.language_changed.connect(self._on_language_changed)
            return window

        self._open_panel("settings", make)

    def _on_language_changed(self, lang: str) -> None:
        self.retranslate()
        self.language_changed.emit()

    def _open_snapshots(self) -> None:
        self._open_panel("snapshots", lambda: SnapshotWindow(self.canvases, parent=None))

    def retranslate(self) -> None:
        self._settings_btn.setToolTip(settings_tooltip(self._update_status))
        self._info_btn.setToolTip(t("About"))
        self._snapshot_btn.setText(t("Snapshots"))
        self._snapshot_btn.setToolTip(t("Snapshots"))
        self._size_text_lbl.setText(t("Size"))
        self._size_lbl.setToolTip(t("Current stroke size (px)"))
        self._custom_btn.setToolTip(t("Custom color…"))
        self._show_mode()
        self._refresh_hints()
        for panel in self._panels.values():
            if panel is not self._settings_win:  # the Settings window relabelled itself: the change came from it
                panel.retranslate()

    # ------------------------------------------------------------------
    # Tool / color / size
    # ------------------------------------------------------------------

    def sync_canvases(self) -> None:
        """Give every canvas the toolbar's tool, colour, size and visibility, and follow its changes: at start,
        and again whenever the screens (and so the canvases) change."""
        hidden = self._vis_btn.isChecked()
        for canvas in self.canvases:
            canvas.active_tool = self._tool
            canvas.active_color = self._color
            canvas.active_width = SIZES[self._size_index]
            if hidden:
                canvas.hide()
            if canvas not in self._watched:
                canvas.changed.connect(self._update_actions)
        self._watched = list(self.canvases)
        self._update_actions()

    def _update_actions(self) -> None:
        """Undo and Clear are greyed out while there is nothing drawn on any screen."""
        drawn = any(canvas.strokes for canvas in self.canvases)
        self._undo_btn.setEnabled(drawn)
        self._clear_btn.setEnabled(drawn)

    def _remember(self, **changes) -> None:
        if not self._restoring:
            self._settings_manager.set_toolbar_state(**changes)

    def _select_tool(self, tool: Tool) -> None:
        self._tool = tool
        for key, btn in self._tool_btns.items():
            btn.setChecked(key == tool)
        for canvas in self.canvases:
            canvas.active_tool = tool
        self._remember(tool=tool.name)

    def _select_color(self, color: str, source_btn: QPushButton | None) -> None:
        """Draw in ``color``; ``source_btn`` is its palette swatch, ``None`` for a custom colour."""
        self._color = color
        self._color_index = self._swatch_btns.index(source_btn) if source_btn in self._swatch_btns else -1
        for i, btn in enumerate(self._swatch_btns):
            selected = btn is source_btn
            btn.setChecked(selected)
            btn.setFixedSize(20 if selected else 18, 20 if selected else 18)
            btn.setStyleSheet(swatch_style(PALETTE[i], selected))
        for canvas in self.canvases:
            canvas.active_color = color
        self._remember(color=color)

    def _pick_custom_color(self) -> None:
        def make() -> ColorWindow:
            window = ColorWindow(self._color, parent=None)
            window.picked.connect(lambda color: self._select_color(color, None))
            return window

        self._open_panel("color", make)

    def _size_down(self) -> None:
        if self._size_index > 0:
            self._size_index -= 1
            self._apply_size()

    def _size_up(self) -> None:
        if self._size_index < len(SIZES) - 1:
            self._size_index += 1
            self._apply_size()

    def _apply_size(self) -> None:
        size = SIZES[self._size_index]
        self._size_lbl.setText(str(size))
        for canvas in self.canvases:
            canvas.active_width = size
        self._update_size_buttons()
        self._remember(size=size)

    def _update_size_buttons(self) -> None:
        """− and + are greyed out at the smallest and the largest size."""
        self._minus_btn.setEnabled(self._size_index > 0)
        self._plus_btn.setEnabled(self._size_index < len(SIZES) - 1)

    # ------------------------------------------------------------------
    # Mode toggles
    # ------------------------------------------------------------------

    _MODE_LOOKS = {
        DRAW: (Qt.CursorShape.CrossCursor, ("#e07020", "#f08030")),
        PAN: (Qt.CursorShape.OpenHandCursor, ("#357a50", "#47a368")),
        DELETE: (Qt.CursorShape.ForbiddenCursor, ("#7a1a1a", "#b02020")),
    }
    """Each mode's cursor over the screen, and its button's colours (resting, under the mouse) while it is on."""

    def _toggle_mode(self, mode: str, checked: bool | None) -> None:
        """Turn ``mode`` on (leaving any other) or off; ``None`` takes the state of its button, just clicked."""
        if checked is None:
            checked = self._mode_btns[mode].isChecked()
        if checked:
            self._mode = mode
            if self._vis_btn.isChecked():
                self._toggle_visibility(False)  # nobody draws, pans or deletes what they can't see
        elif self._mode == mode:
            self._mode = None
        self._show_mode()

    def _show_mode(self) -> None:
        """The three buttons and the captures as the mode in force wants them."""
        labels = {
            DRAW: (t("Draw"), t("Drawing…")),
            PAN: (t("Pan"), t("Panning…")),
            DELETE: (t("Delete"), t("Deleting…")),
        }
        for mode, button in self._mode_btns.items():
            on = mode == self._mode
            button.setChecked(on)
            button.setText(labels[mode][on])
            if on:
                resting, hovered = self._MODE_LOOKS[mode][1]
                button.setStyleSheet(base_btn(bg=resting, hover=hovered, checked=resting))
            else:
                button.setStyleSheet(accent_btn() if mode == DRAW else muted_btn())
        self.update()  # the border is orange while drawing
        for capture in self.captures:
            capture.pan_mode = self._mode == PAN
            capture.delete_mode = self._mode == DELETE
            if self._mode is None:
                capture.hide()
            else:
                capture.setCursor(self._MODE_LOOKS[self._mode][0])
                capture.show()
                capture.raise_()
                capture.activateWindow()

    def _toggle_drawing(self, checked: bool | None = None) -> None:
        self._toggle_mode(DRAW, checked)

    def stop_drawing(self) -> None:
        self._toggle_mode(DRAW, False)

    def _toggle_pan(self, checked: bool | None = None) -> None:
        self._toggle_mode(PAN, checked)

    def stop_pan(self) -> None:
        self._toggle_mode(PAN, False)

    def _toggle_delete(self, checked: bool | None = None) -> None:
        self._toggle_mode(DELETE, checked)

    def stop_delete(self) -> None:
        self._toggle_mode(DELETE, False)

    # ------------------------------------------------------------------
    # Overlay actions
    # ------------------------------------------------------------------

    def _undo(self) -> None:
        """Take back the latest stroke, on whichever screen it was drawn."""
        drawn = [canvas for canvas in self.canvases if canvas.strokes]
        if drawn:
            max(drawn, key=lambda canvas: canvas.last_drawn_at()).undo()

    def _clear(self) -> None:
        for canvas in self.canvases:
            canvas.clear()

    def _toggle_visibility(self, checked: bool | None = None) -> None:
        """Hide the drawings (``checked``) or show them again; hiding leaves any mode first."""
        if checked is None:
            checked = self._vis_btn.isChecked()
        if checked:
            self.stop_modes()
        self._vis_btn.setChecked(checked)
        self._vis_btn.setIcon(svg_icon("show" if checked else "hide", 16))
        self._vis_btn.setToolTip(
            key_hint(t("Show overlay") if checked else t("Hide overlay"), self._shortcut_keys["hide"])
        )
        for canvas in self.canvases:
            if checked:
                canvas.hide()
            else:
                canvas.show()
                canvas.raise_()
        self._remember(hidden=checked)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def quit(self) -> None:
        """Quit Vitralis through the application's clean shutdown (which closes this toolbar and stops its
        hooks); a second call does nothing."""
        if self._quitting:
            return
        self._quitting = True
        logger.info("quitting")
        QApplication.instance().quit()

    def place(self, default: QPoint) -> None:
        """Move to where the toolbar was left, when a screen still shows that spot; else to ``default``."""
        if self._saved_position is not None and _on_a_screen(QPoint(*self._saved_position)):
            self.move(QPoint(*self._saved_position))
        else:
            self.move(default)

    def closeEvent(self, event) -> None:
        """Closed by the session (shutdown, or the licence locking): stop the hooks and close the panels. Closed
        from outside (Alt+F4, the taskbar, ``taskkill``): quit instead, which comes back here through the
        session; a closed toolbar must never leave Vitralis running with nothing to drive it."""
        if event.spontaneous():
            event.ignore()
            self.quit()
            return
        self._hotkey_thread.stop()
        self._wheel_thread.stop()
        if self._updates is not None:
            with contextlib.suppress(TypeError):  # already disconnected by an earlier close
                self._updates.changed.disconnect(self._show_update)
        with contextlib.suppress(TypeError):  # already disconnected by an earlier close
            QApplication.instance().focusWindowChanged.disconnect(self._on_window_focused)
        for window in list(self._panels.values()):
            window.close()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self._saved_position = [self.x(), self.y()]
            self._remember(position=self._saved_position)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_color = QColor("#e07020") if self._drawing_active else QColor(255, 255, 255, 18)
        border_w = 2 if self._drawing_active else 1
        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(QColor(18, 18, 22, 218))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()
