#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.341523
Revised: 2026/05/03 12:04:19.919407
"""

import ctypes

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from vitralis.canvas import Canvas, DrawCapture
from vitralis.hotkeys import GlobalHotkeyThread
from vitralis.icons import media_base, svg_icon
from vitralis.models import Tool
from vitralis.persistence import (
    _screen_key,
    delete_snapshot,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    save_strokes_for,
)
from vitralis.settings import SettingsManager, SettingsWindow
from vitralis.styles import (
    PALETTE,
    PANEL_BORDER,
    SIZES,
    TOOL_ICONS,
    accent_btn,
    base_btn,
    danger_btn,
    muted_btn,
    swatch_style,
)
from vitralis.translations import set_language, t


class _Divider(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet("background: rgba(255,255,255,20);")


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
        if icon_path and icon_path.exists():
            px = QPixmap(str(icon_path)).scaled(
                14, 14, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(px)
            icon_lbl.setFixedSize(14, 14)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            logo_row.addWidget(icon_lbl)
        text_lbl = QLabel("itralis")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lbl.setStyleSheet(
            "color: rgba(255,255,255,160); font-size: 11px; font-weight: 600;"
            "letter-spacing: 1.5px; background: transparent;"
        )
        logo_row.addWidget(text_lbl)
        logo_row.addSpacing(6)
        logo_row.addWidget(dot)
        logo_row.addStretch()
        root.addLayout(logo_row)


class InfoWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, version: str, parent=None) -> None:
        super().__init__(
            parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis — Info")
        self._dragging = False
        self._drag_pos = QPoint()
        self._build_ui(version)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_ui(self, version: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 18)
        root.setSpacing(0)

        _LBL = "color: rgba(255,255,255,60); font-size: 10px; background: transparent; letter-spacing: 0.5px;"
        _VAL = "color: rgba(255,255,255,200); font-size: 12px; background: transparent;"

        def _field(key: str, value: str) -> tuple[QVBoxLayout, QLabel]:
            col = QVBoxLayout()
            col.setSpacing(1)
            lbl = QLabel(t(key).upper())
            lbl.setStyleSheet(_LBL)
            lbl.setProperty("i18n_key", key)
            val = QLabel(value)
            val.setStyleSheet(_VAL)
            col.addWidget(lbl)
            col.addWidget(val)
            return col, lbl

        # close button row
        close_row = QHBoxLayout()
        close_row.setContentsMargins(0, 0, 0, 0)
        close_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(danger_btn())
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        root.addSpacing(6)

        # centered logo
        icon_path = media_base() / "media" / "logo" / "icon.png"
        if icon_path.exists():
            px = QPixmap(str(icon_path)).scaled(
                128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl = QLabel()
            logo_lbl.setPixmap(px)
            logo_lbl.setFixedSize(128, 128)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet("background: transparent;")
            logo_row = QHBoxLayout()
            logo_row.addStretch()
            logo_row.addWidget(logo_lbl)
            logo_row.addStretch()
            root.addLayout(logo_row)

        root.addSpacing(14)
        root.addWidget(_Divider())
        root.addSpacing(12)

        self._field_labels: list[QLabel] = []
        for key, value in [
            ("App", "Vitralis"),
            ("Version", f"v{version}"),
        ]:
            col, lbl = _field(key, value)
            root.addLayout(col)
            root.addSpacing(10)
            self._field_labels.append(lbl)
        root.addWidget(_Divider())
        root.addSpacing(10)
        for key, value in [
            ("Author", "Ran#"),
            ("Email", "ran.hash@proton.me"),
            ("License", "PayBack License (PBL)"),
        ]:
            col, lbl = _field(key, value)
            root.addLayout(col)
            root.addSpacing(10)
            self._field_labels.append(lbl)

    def retranslate(self) -> None:
        for lbl in self._field_labels:
            lbl.setText(t(lbl.property("i18n_key")).upper())

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.setBrush(QColor(18, 18, 22, 218))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        event.accept()


class SnapshotWindow(QWidget):
    closed = pyqtSignal()

    _LIST_STYLE = (
        "QListWidget { background: rgba(255,255,255,8); border: 1px solid rgba(255,255,255,18);"
        "border-radius: 6px; color: #f0f0f0; font-size: 12px; padding: 2px; }"
        "QListWidget::item { padding: 5px 8px; border-radius: 4px; }"
        "QListWidget::item:selected { background: #e07020; color: white; }"
        "QListWidget::item:hover { background: rgba(255,255,255,15); }"
    )
    _INPUT_STYLE = (
        "QLineEdit { background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,25);"
        "border-radius: 6px; color: #f0f0f0; font-size: 12px; padding: 5px 8px; }"
        "QLineEdit:focus { border-color: rgba(255,255,255,60); }"
    )

    def __init__(self, canvases: list, parent=None) -> None:
        super().__init__(
            parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self.canvases = canvases
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis Snapshots")
        self._dragging = False
        self._drag_pos = QPoint()
        self._all_names: list[str] = []
        self._build_ui()
        self._refresh_list()
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(8)

        # title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_lbl = QLabel(t("Snapshots"))
        title_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(danger_btn())
        close_btn.clicked.connect(self.close)
        title_row.addWidget(title_lbl, stretch=1)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # search / name input
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(t("Snapshot name…"))
        self._name_edit.setClearButtonEnabled(True)
        self._name_edit.setStyleSheet(self._INPUT_STYLE)
        self._name_edit.textChanged.connect(self._on_filter)
        self._name_edit.returnPressed.connect(self._save)
        root.addWidget(self._name_edit)

        # list
        self._list = QListWidget()
        self._list.setMinimumHeight(130)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setStyleSheet(self._LIST_STYLE)
        QShortcut(QKeySequence("Ctrl+A"), self._list, activated=self._list.selectAll)
        QShortcut(QKeySequence("Return"), self._list, activated=self._load)
        QShortcut(QKeySequence("Delete"), self._list, activated=self._delete)
        root.addWidget(self._list)

        # action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._save_btn = QPushButton(svg_icon("save", 15), "  " + t("Save"))
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(muted_btn())
        self._save_btn.clicked.connect(self._save)

        self._load_btn = QPushButton(svg_icon("load", 15), "  " + t("Load"))
        self._load_btn.setFixedHeight(30)
        self._load_btn.setStyleSheet(muted_btn())
        self._load_btn.clicked.connect(self._load)

        self._del_btn = QPushButton(svg_icon("trash", 15), "  " + t("Delete"))
        self._del_btn.setFixedHeight(30)
        self._del_btn.setStyleSheet(muted_btn())
        self._del_btn.clicked.connect(self._delete)

        for b in (self._save_btn, self._load_btn, self._del_btn):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        self._list.itemSelectionChanged.connect(self._update_buttons)
        self._name_edit.textChanged.connect(self._update_buttons)
        self._update_buttons()

    def _update_buttons(self) -> None:
        n = len(self._list.selectedItems())
        has_name = bool(self._name_edit.text().strip())
        self._save_btn.setEnabled((has_name or n == 1) and n <= 1)
        self._load_btn.setEnabled(n == 1)
        self._del_btn.setEnabled(n >= 1)

    def _refresh_list(self, keep_filter: bool = False) -> None:
        self._all_names = list_snapshots()
        query = self._name_edit.text().strip().lower() if keep_filter else ""
        self._apply_filter(query)

    def _on_filter(self, text: str) -> None:
        self._apply_filter(text.strip().lower())

    def _apply_filter(self, query: str) -> None:
        selected = {item.text() for item in self._list.selectedItems()}
        self._list.clear()
        for name in self._all_names:
            if not query or query in name.lower():
                self._list.addItem(name)
        for i in range(self._list.count()):
            if self._list.item(i).text() in selected:
                self._list.item(i).setSelected(True)

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            items = self._list.selectedItems()
            if len(items) == 1:
                name = items[0].text()
        if not name:
            return
        screens = {_screen_key(c._geo): c.strokes for c in self.canvases}
        save_snapshot(name, screens)
        self._name_edit.clear()
        self._refresh_list()

    def _load(self) -> None:
        items = self._list.selectedItems()
        if len(items) != 1:
            return
        data = load_snapshot(items[0].text())
        if not data:
            return
        for canvas in self.canvases:
            key = _screen_key(canvas._geo)
            if key in data:
                canvas.load(data[key])
                save_strokes_for(canvas._geo, canvas.strokes)

    def _delete(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        for item in items:
            delete_snapshot(item.text())
        self._refresh_list(keep_filter=True)

    def retranslate(self) -> None:
        self._name_edit.setPlaceholderText(t("Snapshot name…"))
        self._save_btn.setText("  " + t("Save"))
        self._load_btn.setText("  " + t("Load"))
        self._del_btn.setText("  " + t("Delete"))

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.setBrush(QColor(18, 18, 22, 218))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        event.accept()


class Toolbar(QWidget):
    def __init__(self, canvases: list[Canvas], captures: list[DrawCapture]) -> None:
        super().__init__()
        self.canvases = canvases
        self.captures = captures
        self._drawing_active = False
        self._pan_active = False
        self._delete_active = False
        self._size_index = 3
        self._prev_hwnd: int | None = None
        self._settings_manager = SettingsManager()
        self._settings_win: SettingsWindow | None = None
        self._snapshot_win: SnapshotWindow | None = None
        self._info_win: InfoWindow | None = None
        self._shortcuts: list[QShortcut] = []
        self._dragging = False
        self._drag_pos = QPoint()

        set_language(self._settings_manager.language())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis")

        self._build_ui()
        self.resize(self.sizeHint())
        self.setFixedWidth(self.width())
        self._install_wheel_filter(self)
        self._start_global_hotkeys()
        self._focus_poll = QTimer(self)
        self._focus_poll.setInterval(150)
        self._focus_poll.timeout.connect(self._poll_focus)
        self._focus_poll.start()

    # ------------------------------------------------------------------
    # Hotkeys / focus
    # ------------------------------------------------------------------

    def _start_global_hotkeys(self) -> None:
        sc = self._settings_manager.shortcuts()
        self._hotkey_thread = GlobalHotkeyThread(self, hotkey=sc.get("focus_toggle", "f8"))
        self._hotkey_thread.signals.toggle_focus.connect(self._toggle_focus)
        self._hotkey_thread.start()

    def _restart_global_hotkey(self, shortcuts: dict) -> None:
        self._hotkey_thread.stop()
        self._hotkey_thread = GlobalHotkeyThread(self, hotkey=shortcuts.get("focus_toggle", "f8"))
        self._hotkey_thread.signals.toggle_focus.connect(self._toggle_focus)
        self._hotkey_thread.start()
        self._apply_shortcuts(shortcuts)

    def _is_vitralis_focused(self) -> bool:
        fg = ctypes.windll.user32.GetForegroundWindow()
        our_hwnds = {int(self.winId())} | {int(c.winId()) for c in self.captures}
        if self._settings_win and self._settings_win.isVisible():
            our_hwnds.add(int(self._settings_win.winId()))
        if self._snapshot_win and self._snapshot_win.isVisible():
            our_hwnds.add(int(self._snapshot_win.winId()))
        if self._info_win and self._info_win.isVisible():
            our_hwnds.add(int(self._info_win.winId()))
        return fg in our_hwnds

    def _poll_focus(self) -> None:
        self._update_focus_dot(self._is_vitralis_focused())

    def _toggle_focus(self) -> None:
        if self._is_vitralis_focused():
            self.hide()
            for cap in self.captures:
                cap.hide()
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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(5)

        self._add_title_row(root)
        root.addWidget(_Divider())
        self._add_mode_buttons(root)
        root.addWidget(_Divider())
        self._add_tool_grid(root)
        root.addWidget(_Divider())
        self._add_color_palette(root)
        root.addWidget(_Divider())
        self._add_size_row(root)
        root.addWidget(_Divider())
        self._add_action_row(root)
        root.addWidget(_Divider())
        self._add_snapshot_row(root)

        self._set_panel_style(active=False)
        self._select_tool(Tool.PEN)
        self._select_color(PALETTE[0], self._swatch_btns[0])
        self._setup_shortcuts()

    def _add_title_row(self, root: QVBoxLayout) -> None:
        base = media_base()

        self._focus_dot = QLabel()
        self._focus_dot.setFixedSize(10, 10)
        self._focus_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_focus_dot(False)

        self._settings_btn = QPushButton(svg_icon("settings", 14), "")
        self._settings_btn.setToolTip(t("Settings"))
        self._settings_btn.setFixedSize(26, 26)
        self._settings_btn.setStyleSheet(muted_btn())
        self._settings_btn.clicked.connect(self._open_settings)

        self._info_btn = QPushButton(svg_icon("info", 14), "")
        self._info_btn.setToolTip(t("About"))
        self._info_btn.setFixedSize(26, 26)
        self._info_btn.setStyleSheet(muted_btn())
        self._info_btn.clicked.connect(self._open_info)

        _spacer = QWidget()
        _spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._quit_btn = QPushButton(svg_icon("quit", 14), "")
        self._quit_btn.setToolTip(t("Quit  [Esc / Ctrl+Q]"))
        self._quit_btn.setFixedSize(26, 26)
        self._quit_btn.setStyleSheet(danger_btn())
        self._quit_btn.clicked.connect(self._quit)

        header = _TitleHeader(
            icon_path=base / "media" / "logo" / "icon.png",
            dot=self._focus_dot,
            buttons=[self._settings_btn, self._info_btn, _spacer, self._quit_btn],
            parent=self,
        )
        root.addWidget(header)

    def _add_mode_buttons(self, root: QVBoxLayout) -> None:
        self._draw_btn = QPushButton(svg_icon("draw", 16), t("Draw"))
        self._draw_btn.setCheckable(True)
        self._draw_btn.setToolTip(t("Activate drawing mode  [D]  ·  Focus: F8"))
        self._draw_btn.setFixedHeight(34)
        self._draw_btn.setIconSize(self._draw_btn.sizeHint())
        self._draw_btn.setStyleSheet(accent_btn())
        self._draw_btn.clicked.connect(self._toggle_drawing)
        root.addWidget(self._draw_btn)

        self._pan_btn = QPushButton(svg_icon("pan", 14), t("Pan"))
        self._pan_btn.setCheckable(True)
        self._pan_btn.setToolTip(t("Drag to shift all drawings on the overlay  [G]"))
        self._pan_btn.setFixedHeight(28)
        self._pan_btn.setStyleSheet(muted_btn())
        self._pan_btn.clicked.connect(self._toggle_pan)
        root.addWidget(self._pan_btn)

        self._del_btn = QPushButton(svg_icon("delete", 14), t("Delete"))
        self._del_btn.setCheckable(True)
        self._del_btn.setToolTip(t("Click near any stroke to remove it  [X]"))
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
                tool, (icon_name, tip) = tool_list[row * 2 + col]
                btn = QPushButton(svg_icon(icon_name, 18), "")
                btn.setToolTip(t(tip))
                btn.setFixedSize(36, 32)
                btn.setCheckable(True)
                btn.setStyleSheet(base_btn())
                btn.clicked.connect(lambda checked, tool=tool: self._select_tool(tool))
                row_layout.addWidget(btn)
                self._tool_btns[tool] = btn
            root.addLayout(row_layout)

    def _add_color_palette(self, root: QVBoxLayout) -> None:
        self._color = PALETTE[0]
        self._color_index = 0
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
        self._minus_btn.setToolTip(t("Decrease stroke size  [[]"))
        self._minus_btn.setStyleSheet(muted_btn())
        self._minus_btn.clicked.connect(self._size_down)

        self._size_lbl = QLabel(str(SIZES[self._size_index]))
        self._size_lbl.setFixedWidth(24)
        self._size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
        self._size_lbl.setToolTip(t("Current stroke size (px)"))

        self._plus_btn = QPushButton(svg_icon("plus", 12), "")
        self._plus_btn.setFixedSize(24, 22)
        self._plus_btn.setToolTip(t("Increase stroke size  []]"))
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
        self._undo_btn.setToolTip(t("Undo  [Z]"))
        self._undo_btn.setFixedSize(36, 28)
        self._undo_btn.setStyleSheet(muted_btn())
        self._undo_btn.clicked.connect(self._undo)

        self._vis_btn = QPushButton(svg_icon("hide", 16), "")
        self._vis_btn.setCheckable(True)
        self._vis_btn.setToolTip(t("Hide overlay  [H]"))
        self._vis_btn.setFixedSize(36, 28)
        self._vis_btn.setStyleSheet(muted_btn())
        self._vis_btn.clicked.connect(self._toggle_visibility)

        self._clear_btn = QPushButton(svg_icon("clear", 16), "")
        self._clear_btn.setToolTip(t("Clear all  [Del]"))
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
        if focused:
            color, glow = "#44dd88", "rgba(68,221,136,120)"
            tip_key = "Focused"
        else:
            color, glow = "#e07020", "rgba(224,112,32,120)"
            tip_key = "Unfocused  ·  F8 to focus"
        self._focus_dot.setToolTip(t(tip_key))
        self._focus_dot.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 5px; border: 1px solid {glow}; }}"
        )

    def _set_panel_style(self, active: bool) -> None:
        border_color = "#e07020" if active else PANEL_BORDER
        border_width = "2px" if active else "1px"
        self.setStyleSheet(
            f"QWidget#toolbar_panel {{"
            f"  background: rgba(18,18,22,218);"
            f"  border-radius: 10px;"
            f"  border: {border_width} solid {border_color};"
            f"}}"
        )

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Escape"), self, activated=self._esc)
        self._apply_shortcuts(self._settings_manager.shortcuts())

    def _esc(self) -> None:
        if self._info_win and self._info_win.isVisible():
            self._info_win.close()
        elif self._snapshot_win and self._snapshot_win.isVisible():
            self._snapshot_win.close()
        elif self._settings_win and self._settings_win.isVisible():
            self._settings_win.close()
        else:
            self._quit()

    def _apply_shortcuts(self, sc_map: dict) -> None:
        for s in self._shortcuts:
            s.setEnabled(False)
            s.deleteLater()
        self._shortcuts.clear()

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
        sc(sc_map.get("quit", "ctrl+q"), self._quit)
        sc(sc_map.get("tool_pen", "p"), lambda: self._select_tool(Tool.PEN))
        sc(sc_map.get("tool_eraser", "e"), lambda: self._select_tool(Tool.ERASER))
        sc(sc_map.get("tool_line", "l"), lambda: self._select_tool(Tool.LINE))
        sc(sc_map.get("tool_arrow", "a"), lambda: self._select_tool(Tool.ARROW))
        sc(sc_map.get("tool_rect", "r"), lambda: self._select_tool(Tool.RECT))
        sc(sc_map.get("tool_ellipse", "o"), lambda: self._select_tool(Tool.ELLIPSE))
        sc(sc_map.get("size_down", "["), self._size_down)
        sc(sc_map.get("size_up", "]"), self._size_up)

    def _open_info(self) -> None:
        if self._info_win is None or not self._info_win.isVisible():
            from importlib.metadata import version as pkg_version

            try:
                ver = pkg_version("vitralis")
            except Exception:
                ver = "?"
            self._info_win = InfoWindow(ver, parent=None)
            self._info_win.closed.connect(self._on_info_closed)
            geo = self.frameGeometry()
            self._info_win.move(geo.right() + 8, geo.top())
            self._info_win.show()
        else:
            self._info_win.raise_()
            self._info_win.activateWindow()

    def _on_info_closed(self) -> None:
        self._info_win = None

    def _open_settings(self) -> None:
        if self._settings_win is None or not self._settings_win.isVisible():
            self._settings_win = SettingsWindow(self._settings_manager, parent=None)
            self._settings_win.shortcuts_changed.connect(self._restart_global_hotkey)
            self._settings_win.language_changed.connect(self._on_language_changed)
            self._settings_win.closed.connect(self._on_settings_closed)
            geo = self.frameGeometry()
            self._settings_win.move(geo.right() + 8, geo.top())
            self._settings_win.show()
        else:
            self._settings_win.raise_()
            self._settings_win.activateWindow()

    def _on_language_changed(self, lang: str) -> None:
        self.retranslate()
        if self._snapshot_win and self._snapshot_win.isVisible():
            self._snapshot_win.retranslate()
        if self._info_win and self._info_win.isVisible():
            self._info_win.retranslate()

    def _on_settings_closed(self) -> None:
        self._settings_win = None

    def _open_snapshots(self) -> None:
        if self._snapshot_win is None or not self._snapshot_win.isVisible():
            self._snapshot_win = SnapshotWindow(self.canvases, parent=None)
            self._snapshot_win.closed.connect(self._on_snapshot_closed)
            geo = self.frameGeometry()
            self._snapshot_win.move(geo.right() + 8, geo.top())
            self._snapshot_win.show()
        else:
            self._snapshot_win.raise_()
            self._snapshot_win.activateWindow()

    def _on_snapshot_closed(self) -> None:
        self._snapshot_win = None

    def retranslate(self) -> None:
        self._settings_btn.setToolTip(t("Settings"))
        self._info_btn.setToolTip(t("About"))
        self._snapshot_btn.setText(t("Snapshots"))
        self._snapshot_btn.setToolTip(t("Snapshots"))
        self._quit_btn.setToolTip(t("Quit  [Esc / Ctrl+Q]"))
        self._draw_btn.setToolTip(t("Activate drawing mode  [D]  ·  Focus: F8"))
        self._pan_btn.setToolTip(t("Drag to shift all drawings on the overlay  [G]"))
        self._del_btn.setToolTip(t("Click near any stroke to remove it  [X]"))
        self._size_text_lbl.setText(t("Size"))
        self._minus_btn.setToolTip(t("Decrease stroke size  [[]"))
        self._size_lbl.setToolTip(t("Current stroke size (px)"))
        self._plus_btn.setToolTip(t("Increase stroke size  []]"))
        self._undo_btn.setToolTip(t("Undo  [Z]"))
        self._clear_btn.setToolTip(t("Clear all  [Del]"))
        self._custom_btn.setToolTip(t("Custom color…"))
        for tool, btn in self._tool_btns.items():
            _, tip = TOOL_ICONS[tool]
            btn.setToolTip(t(tip))
        # mode button labels: only update if not in active state
        if not self._drawing_active:
            self._draw_btn.setText(t("Draw"))
        if not self._pan_active:
            self._pan_btn.setText(t("Pan"))
        if not self._delete_active:
            self._del_btn.setText(t("Delete"))

    # ------------------------------------------------------------------
    # Tool / color / size
    # ------------------------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        for key, btn in self._tool_btns.items():
            btn.setChecked(key == tool)
        for canvas in self.canvases:
            canvas.active_tool = tool

    def _select_color(self, color: str, source_btn: QPushButton | None) -> None:
        self._color = color
        self._color_index = self._swatch_btns.index(source_btn) if source_btn in self._swatch_btns else -1
        for i, btn in enumerate(self._swatch_btns):
            selected = btn is source_btn
            btn.setChecked(selected)
            btn.setFixedSize(20 if selected else 18, 20 if selected else 18)
            btn.setStyleSheet(swatch_style(PALETTE[i], selected))
        for canvas in self.canvases:
            canvas.active_color = color

    def _pick_custom_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "Pick color")
        if color.isValid():
            self._color = color.name()
            self._color_index = -1
            for i, btn in enumerate(self._swatch_btns):
                btn.setChecked(False)
                btn.setFixedSize(18, 18)
                btn.setStyleSheet(swatch_style(PALETTE[i], False))
            for canvas in self.canvases:
                canvas.active_color = self._color

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

    # ------------------------------------------------------------------
    # Mode toggles
    # ------------------------------------------------------------------

    def _toggle_drawing(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = self._draw_btn.isChecked()
        if checked:
            self._toggle_pan(False)
            self._toggle_delete(False)
        self._drawing_active = checked
        self._draw_btn.setChecked(checked)
        if checked:
            self._draw_btn.setText(t("Drawing…"))
            self._draw_btn.setStyleSheet(base_btn(bg="#e07020", hover="#f08030", checked="#e07020"))
        else:
            self._draw_btn.setText(t("Draw"))
            self._draw_btn.setStyleSheet(accent_btn())
        self._set_panel_style(active=checked)
        for cap in self.captures:
            cap.pan_mode = False
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def stop_drawing(self) -> None:
        self._toggle_drawing(False)

    def _toggle_pan(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = self._pan_btn.isChecked()
        if checked:
            self._toggle_drawing(False)
            self._toggle_delete(False)
        self._pan_active = checked
        self._pan_btn.setChecked(checked)
        if checked:
            self._pan_btn.setText(t("Panning…"))
            self._pan_btn.setStyleSheet(base_btn(bg="#357a50", hover="#47a368", checked="#357a50"))
        else:
            self._pan_btn.setText(t("Pan"))
            self._pan_btn.setStyleSheet(muted_btn())
        for cap in self.captures:
            cap.pan_mode = checked
            cap.setCursor(Qt.CursorShape.OpenHandCursor if checked else Qt.CursorShape.CrossCursor)
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def stop_pan(self) -> None:
        self._toggle_pan(False)

    def _toggle_delete(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = self._del_btn.isChecked()
        if checked:
            self._toggle_drawing(False)
            self._toggle_pan(False)
        self._delete_active = checked
        self._del_btn.setChecked(checked)
        if checked:
            self._del_btn.setText(t("Deleting…"))
            self._del_btn.setStyleSheet(base_btn(bg="#7a1a1a", hover="#b02020", checked="#7a1a1a"))
        else:
            self._del_btn.setText(t("Delete"))
            self._del_btn.setStyleSheet(muted_btn())
        for cap in self.captures:
            cap.delete_mode = checked
            cap.setCursor(Qt.CursorShape.ForbiddenCursor if checked else Qt.CursorShape.CrossCursor)
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def stop_delete(self) -> None:
        self._toggle_delete(False)

    # ------------------------------------------------------------------
    # Overlay actions
    # ------------------------------------------------------------------

    def _undo(self) -> None:
        for canvas in self.canvases:
            canvas.undo()

    def _clear(self) -> None:
        for canvas in self.canvases:
            canvas.clear()

    def _toggle_visibility(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = self._vis_btn.isChecked()
        self._vis_btn.setChecked(checked)
        self._vis_btn.setIcon(svg_icon("show" if checked else "hide", 16))
        self._vis_btn.setToolTip(t("Show overlay  [H]") if checked else t("Hide overlay  [H]"))
        for canvas in self.canvases:
            if checked:
                canvas.hide()
            else:
                canvas.show()
                canvas.raise_()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _quit(self) -> None:
        if not self._hotkey_thread.isRunning():
            return
        self._hotkey_thread.stop()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        self._hotkey_thread.stop()
        if self._snapshot_win:
            self._snapshot_win.close()
        if self._info_win:
            self._info_win.close()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False

    def _install_wheel_filter(self, widget) -> None:
        widget.installEventFilter(self)
        for child in widget.children():
            if isinstance(child, QWidget):
                self._install_wheel_filter(child)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel and obj is not self:
            self.wheelEvent(event)
            return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = -1 if delta > 0 else 1
        base = self._color_index if self._color_index >= 0 else 0
        new_index = (base + step) % len(PALETTE)
        self._select_color(PALETTE[new_index], self._swatch_btns[new_index])

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_color = QColor("#e07020") if self._drawing_active else QColor(255, 255, 255, 18)
        border_w = 2 if self._drawing_active else 1
        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(QColor(18, 18, 22, 218))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()
