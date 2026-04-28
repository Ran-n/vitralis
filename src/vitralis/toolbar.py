#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.341523
Revised: 2026/04/28 16:22:10.765917
"""

import ctypes

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vitralis.canvas import Canvas, DrawCapture
from vitralis.hotkeys import GlobalHotkeyThread
from vitralis.icons import media_base, svg_icon
from vitralis.models import Tool
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


class _Divider(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet("background: rgba(255,255,255,20);")


class _DragHandle(QWidget):
    def __init__(self, text: str, parent: QWidget, icon_path=None) -> None:
        super().__init__(parent)
        self._window = parent
        self._dragging = False
        self._drag_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if icon_path and icon_path.exists():
            px = QPixmap(str(icon_path)).scaled(
                14, 14, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(px)
            icon_lbl.setFixedSize(14, 14)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lbl.setStyleSheet(
            "color: rgba(255,255,255,160); font-size: 11px; font-weight: 600;"
            "letter-spacing: 1.5px; background: transparent;"
        )
        layout.addWidget(text_lbl)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False


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

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis")

        self._build_ui()
        self.resize(self.sizeHint())
        self.setFixedWidth(self.width())
        self._start_global_hotkeys()

    # ------------------------------------------------------------------
    # Hotkeys / focus
    # ------------------------------------------------------------------

    def _start_global_hotkeys(self) -> None:
        self._hotkey_thread = GlobalHotkeyThread(self)
        self._hotkey_thread.signals.toggle_focus.connect(self._toggle_focus)
        self._hotkey_thread.start()

    def _is_vitralis_focused(self) -> bool:
        fg = ctypes.windll.user32.GetForegroundWindow()
        our_hwnds = {int(self.winId())} | {int(c.winId()) for c in self.captures}
        return fg in our_hwnds

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
        root.setContentsMargins(8, 8, 8, 8)
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

        self._set_panel_style(active=False)
        self._select_tool(Tool.PEN)
        self._select_color(PALETTE[0], self._swatch_btns[0])
        self._setup_shortcuts()

    def _add_title_row(self, root: QVBoxLayout) -> None:
        base = media_base()
        handle = _DragHandle("itralis", self, icon_path=base / "media" / "logo" / "icon.png")
        handle.setCursor(Qt.CursorShape.SizeAllCursor)

        quit_btn = QPushButton(svg_icon("quit", 14), "")
        quit_btn.setToolTip("Quit  [Esc / Ctrl+Q]")
        quit_btn.setFixedSize(22, 22)
        quit_btn.setStyleSheet(danger_btn())
        quit_btn.clicked.connect(self._quit)

        spacer = QWidget()
        spacer.setFixedSize(22, 22)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        title_row.addWidget(spacer)
        title_row.addWidget(handle, stretch=1)
        title_row.addWidget(quit_btn)
        root.addLayout(title_row)

    def _add_mode_buttons(self, root: QVBoxLayout) -> None:
        self._draw_btn = QPushButton(svg_icon("draw", 16), "Draw")
        self._draw_btn.setCheckable(True)
        self._draw_btn.setToolTip("Activate drawing mode  [D]  ·  Focus: F8")
        self._draw_btn.setFixedHeight(34)
        self._draw_btn.setIconSize(self._draw_btn.sizeHint())
        self._draw_btn.setStyleSheet(accent_btn())
        self._draw_btn.clicked.connect(self._toggle_drawing)
        root.addWidget(self._draw_btn)

        self._pan_btn = QPushButton(svg_icon("pan", 14), "Pan")
        self._pan_btn.setCheckable(True)
        self._pan_btn.setToolTip("Drag to shift all drawings on the overlay  [G]")
        self._pan_btn.setFixedHeight(28)
        self._pan_btn.setStyleSheet(muted_btn())
        self._pan_btn.clicked.connect(self._toggle_pan)
        root.addWidget(self._pan_btn)

        self._del_btn = QPushButton(svg_icon("delete", 14), "Delete")
        self._del_btn.setCheckable(True)
        self._del_btn.setToolTip("Click near any stroke to remove it  [X]")
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
                btn.setToolTip(tip)
                btn.setFixedSize(36, 32)
                btn.setCheckable(True)
                btn.setStyleSheet(base_btn())
                btn.clicked.connect(lambda checked, t=tool: self._select_tool(t))
                row_layout.addWidget(btn)
                self._tool_btns[tool] = btn
            root.addLayout(row_layout)

    def _add_color_palette(self, root: QVBoxLayout) -> None:
        self._color = PALETTE[0]
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
        self._custom_btn.setToolTip("Custom color…")
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

        size_lbl = QLabel("Size")
        size_lbl.setStyleSheet("color: rgba(255,255,255,110); font-size: 10px;")
        size_row.addWidget(size_lbl)
        size_row.addStretch()

        minus_btn = QPushButton(svg_icon("minus", 12), "")
        minus_btn.setFixedSize(24, 22)
        minus_btn.setToolTip("Decrease stroke size  [[]")
        minus_btn.setStyleSheet(muted_btn())
        minus_btn.clicked.connect(self._size_down)

        self._size_lbl = QLabel(str(SIZES[self._size_index]))
        self._size_lbl.setFixedWidth(24)
        self._size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
        self._size_lbl.setToolTip("Current stroke size (px)")

        plus_btn = QPushButton(svg_icon("plus", 12), "")
        plus_btn.setFixedSize(24, 22)
        plus_btn.setToolTip("Increase stroke size  []]")
        plus_btn.setStyleSheet(muted_btn())
        plus_btn.clicked.connect(self._size_up)

        size_row.addWidget(minus_btn)
        size_row.addWidget(self._size_lbl)
        size_row.addWidget(plus_btn)
        root.addLayout(size_row)

    def _add_action_row(self, root: QVBoxLayout) -> None:
        act_row = QHBoxLayout()
        act_row.setSpacing(3)

        undo_btn = QPushButton(svg_icon("undo", 16), "")
        undo_btn.setToolTip("Undo  [Z]")
        undo_btn.setFixedSize(36, 28)
        undo_btn.setStyleSheet(muted_btn())
        undo_btn.clicked.connect(self._undo)

        self._vis_btn = QPushButton(svg_icon("hide", 16), "")
        self._vis_btn.setCheckable(True)
        self._vis_btn.setToolTip("Hide overlay  [H]")
        self._vis_btn.setFixedSize(36, 28)
        self._vis_btn.setStyleSheet(muted_btn())
        self._vis_btn.clicked.connect(self._toggle_visibility)

        clear_btn = QPushButton(svg_icon("clear", 16), "")
        clear_btn.setToolTip("Clear all  [Del]")
        clear_btn.setFixedSize(36, 28)
        clear_btn.setStyleSheet(muted_btn())
        clear_btn.clicked.connect(self._clear)

        for b in (undo_btn, self._vis_btn, clear_btn):
            act_row.addWidget(b)
        root.addLayout(act_row)

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
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self, activated=fn)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)

        sc("D", lambda: self._toggle_drawing(not self._drawing_active))
        sc("G", lambda: self._toggle_pan(not self._pan_active))
        sc("X", lambda: self._toggle_delete(not self._delete_active))
        sc("Z", self._undo)
        sc("Delete", self._clear)
        sc("H", lambda: self._toggle_visibility(not self._vis_btn.isChecked()))
        QShortcut(QKeySequence("Escape"), self, activated=self._quit)
        sc("Ctrl+Q", self._quit)
        sc("P", lambda: self._select_tool(Tool.PEN))
        sc("E", lambda: self._select_tool(Tool.ERASER))
        sc("L", lambda: self._select_tool(Tool.LINE))
        sc("A", lambda: self._select_tool(Tool.ARROW))
        sc("R", lambda: self._select_tool(Tool.RECT))
        sc("O", lambda: self._select_tool(Tool.ELLIPSE))
        sc("[", self._size_down)
        sc("]", self._size_up)

    # ------------------------------------------------------------------
    # Tool / color / size
    # ------------------------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        for t, btn in self._tool_btns.items():
            btn.setChecked(t == tool)
        for canvas in self.canvases:
            canvas.active_tool = tool

    def _select_color(self, color: str, source_btn: QPushButton) -> None:
        self._color = color
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
            self._draw_btn.setText("Drawing…")
            self._draw_btn.setStyleSheet(base_btn(bg="#e07020", hover="#f08030", checked="#e07020"))
        else:
            self._draw_btn.setText("Draw")
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
            self._pan_btn.setText("Panning…")
            self._pan_btn.setStyleSheet(base_btn(bg="#357a50", hover="#47a368", checked="#357a50"))
        else:
            self._pan_btn.setText("Pan")
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
            self._del_btn.setText("Deleting…")
            self._del_btn.setStyleSheet(base_btn(bg="#7a1a1a", hover="#b02020", checked="#7a1a1a"))
        else:
            self._del_btn.setText("Delete")
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
        self._vis_btn.setToolTip("Show overlay  [H]" if checked else "Hide overlay  [H]")
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
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_color = QColor("#e07020") if self._drawing_active else QColor(255, 255, 255, 18)
        border_w = 2 if self._drawing_active else 1
        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(QColor(18, 18, 22, 218))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()
