#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/27 10:51:18.086867
Revised: 2026/04/28 14:22:05.485962
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyQt6>=6.6",
#   "keyboard>=0.13",
# ]
# ///
"""
Vitralis — screen overlay drawing tool.

Always-on-top transparent overlay across all monitors.
Drawing is activated via the floating toolbar; the overlay is
always click-through so normal computer use is never blocked.
"""

import contextlib
import ctypes
import json
import math
import os
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import keyboard
from PyQt6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QThread,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "Vitralis"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STROKES_FILE = DATA_DIR / "strokes.json"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


class Tool(Enum):
    PEN = auto()
    ERASER = auto()
    LINE = auto()
    ARROW = auto()
    RECT = auto()
    ELLIPSE = auto()


@dataclass
class Stroke:
    tool: str
    color: str  # "#rrggbb"
    width: int
    points: list  # list of [x, y]
    # for shapes: points[0] = start, points[1] = end
    filled: bool = False

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "color": self.color,
            "width": self.width,
            "points": self.points,
            "filled": self.filled,
        }

    @staticmethod
    def from_dict(d: dict) -> "Stroke":
        return Stroke(
            tool=d["tool"],
            color=d["color"],
            width=d["width"],
            points=d["points"],
            filled=d.get("filled", False),
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _screen_key(geo: QRect) -> str:
    return f"{geo.x()},{geo.y()}"


def load_strokes_for(geo: QRect) -> list[Stroke]:
    if not STROKES_FILE.exists():
        return []
    try:
        data = json.loads(STROKES_FILE.read_text(encoding="utf-8"))
        # legacy flat-list format → treat as primary screen (0,0 or first key)
        if isinstance(data, list):
            return [Stroke.from_dict(s) for s in data] if geo.x() == 0 and geo.y() == 0 else []
        key = _screen_key(geo)
        return [Stroke.from_dict(s) for s in data.get(key, [])]
    except Exception:
        return []


def save_strokes_for(geo: QRect, strokes: list[Stroke]) -> None:
    with contextlib.suppress(Exception):
        try:
            data = json.loads(STROKES_FILE.read_text(encoding="utf-8")) if STROKES_FILE.exists() else {}
            if isinstance(data, list):
                data = {}
        except Exception:
            data = {}
        data[_screen_key(geo)] = [s.to_dict() for s in strokes]
        STROKES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _pen(color: str, width: int, eraser: bool = False) -> QPen:
    pen = QPen()
    if eraser:
        pen.setColor(Qt.GlobalColor.transparent)
        pen.setWidth(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    else:
        pen.setColor(QColor(color))
        pen.setWidth(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_arrow(painter: QPainter, p1: QPointF, p2: QPointF, width: int) -> None:
    """Draw a line with an arrowhead at p2."""
    painter.drawLine(p1, p2)
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    arrow_len = max(12, width * 4)
    arrow_w = max(6, width * 2)
    tip = p2
    base = QPointF(tip.x() - ux * arrow_len, tip.y() - uy * arrow_len)
    perp = QPointF(-uy * arrow_w, ux * arrow_w)
    poly = QPolygonF(
        [
            tip,
            QPointF(base.x() + perp.x(), base.y() + perp.y()),
            QPointF(base.x() - perp.x(), base.y() - perp.y()),
        ]
    )
    old_brush = painter.brush()
    painter.setBrush(painter.pen().color())
    painter.drawPolygon(poly)
    painter.setBrush(old_brush)


def render_stroke(painter: QPainter, stroke: Stroke) -> None:
    tool = stroke.tool
    color = stroke.color
    width = stroke.width
    points = stroke.points

    if not points:
        return

    is_eraser = tool == Tool.ERASER.name
    pen = _pen(color, width, eraser=is_eraser)
    painter.setPen(pen)

    if is_eraser:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)

    if tool == Tool.PEN.name or tool == Tool.ERASER.name:
        path = QPainterPath()
        path.moveTo(QPointF(*points[0]))
        for pt in points[1:]:
            path.lineTo(QPointF(*pt))
        painter.drawPath(path)

    elif tool == Tool.LINE.name and len(points) >= 2:
        painter.drawLine(QPointF(*points[0]), QPointF(*points[-1]))

    elif tool == Tool.ARROW.name and len(points) >= 2:
        _draw_arrow(painter, QPointF(*points[0]), QPointF(*points[-1]), width)

    elif tool == Tool.RECT.name and len(points) >= 2:
        x0, y0 = points[0]
        x1, y1 = points[-1]
        rect = QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()
        painter.drawRect(rect)

    elif tool == Tool.ELLIPSE.name and len(points) >= 2:
        x0, y0 = points[0]
        x1, y1 = points[-1]
        rect = QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()
        painter.drawEllipse(rect)

    if is_eraser:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)


# ---------------------------------------------------------------------------
# Canvas (the transparent overlay)
# ---------------------------------------------------------------------------


class Canvas(QWidget):
    def __init__(self, geometry: QRect) -> None:
        super().__init__()
        self._geo = geometry
        self.strokes: list[Stroke] = []
        self.current: Stroke | None = None
        self.drawing: bool = False
        self.active_tool = Tool.PEN
        self.active_color = "#ff0000"
        self.active_width = 3
        self._offset = QPointF(0, 0)

        self.setGeometry(geometry)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowTitle("Vitralis Overlay")

        self._pixmap = QPixmap(geometry.size())
        self._pixmap.fill(Qt.GlobalColor.transparent)

    def load(self, strokes: list[Stroke]) -> None:
        self.strokes = strokes
        self._redraw_pixmap()
        self.update()

    def begin_stroke(self, pos: QPointF) -> None:
        self.current = Stroke(
            tool=self.active_tool.name,
            color=self.active_color,
            width=self.active_width,
            points=[[pos.x(), pos.y()]],
        )
        self.drawing = True

    def extend_stroke(self, pos: QPointF) -> None:
        if self.current and self.drawing:
            tool = self.active_tool
            if tool in (Tool.PEN, Tool.ERASER):
                self.current.points.append([pos.x(), pos.y()])
            else:
                if len(self.current.points) == 1:
                    self.current.points.append([pos.x(), pos.y()])
                else:
                    self.current.points[-1] = [pos.x(), pos.y()]
            self.update()

    def end_stroke(self) -> None:
        if self.current and self.drawing and len(self.current.points) >= 1:
            self.strokes.append(self.current)
            self._commit_stroke(self.current)
            save_strokes_for(self._geo, self.strokes)
        self.current = None
        self.drawing = False
        self.update()

    def undo(self) -> None:
        if self.strokes:
            self.strokes.pop()
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()

    def clear(self) -> None:
        self.strokes.clear()
        self._offset = QPointF(0, 0)
        self._pixmap.fill(Qt.GlobalColor.transparent)
        save_strokes_for(self._geo, self.strokes)
        self.update()

    def delete_stroke_at(self, pos: QPointF, tolerance: float = 20.0) -> None:
        adjusted = pos - self._offset
        px, py = adjusted.x(), adjusted.y()
        best_idx, best_dist = -1, float("inf")
        for i, stroke in enumerate(self.strokes):
            pts = stroke.points
            for j in range(len(pts)):
                x0, y0 = pts[j]
                # distance to vertex
                d = math.hypot(x0 - px, y0 - py)
                if d < best_dist:
                    best_dist, best_idx = d, i
                # distance to segment to the next point
                if j + 1 < len(pts):
                    x1, y1 = pts[j + 1]
                    dx, dy = x1 - x0, y1 - y0
                    seg_len_sq = dx * dx + dy * dy
                    if seg_len_sq > 0:
                        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg_len_sq))
                        cx, cy = x0 + t * dx, y0 + t * dy
                        d = math.hypot(cx - px, cy - py)
                        if d < best_dist:
                            best_dist, best_idx = d, i
        if best_idx >= 0 and best_dist <= tolerance:
            self.strokes.pop(best_idx)
            self._redraw_pixmap()
            save_strokes_for(self._geo, self.strokes)
            self.update()

    def shift_by(self, delta: QPointF) -> None:
        self._offset += delta
        self.update()

    def apply_offset(self) -> None:
        """Bake the current offset into all stroke coordinates and reset it."""
        if self._offset.isNull():
            return
        dx, dy = self._offset.x(), self._offset.y()
        for stroke in self.strokes:
            stroke.points = [[x + dx, y + dy] for x, y in stroke.points]
        self._offset = QPointF(0, 0)
        self._redraw_pixmap()
        save_strokes_for(self._geo, self.strokes)
        self.update()

    def _redraw_pixmap(self) -> None:
        self._pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for stroke in self.strokes:
            render_stroke(painter, stroke)
        painter.end()

    def _commit_stroke(self, stroke: Stroke) -> None:
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        render_stroke(painter, stroke)
        painter.end()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(self._offset.toPoint(), self._pixmap)
        if self.current:
            painter.translate(self._offset)
            render_stroke(painter, self.current)
        painter.end()


# ---------------------------------------------------------------------------
# Drawing capture widget
# ---------------------------------------------------------------------------


class DrawCapture(QWidget):
    """Invisible full-screen widget that captures mouse events while a tool is active."""

    def __init__(self, canvas: Canvas, geometry: QRect, stop_drawing, toolbar: list) -> None:
        super().__init__()
        self.canvas = canvas
        self._stop_drawing = stop_drawing
        self._toolbar_ref = toolbar
        self.pan_mode = False
        self.delete_mode = False
        self._pan_last: QPointF | None = None
        self.setGeometry(geometry)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setWindowOpacity(0.01)
        self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.pan_mode:
                self._pan_last = event.globalPosition()
            elif self.delete_mode:
                pos = event.position() + QPointF(self.geometry().topLeft())
                cp = pos - QPointF(self.canvas.geometry().topLeft())
                self.canvas.delete_stroke_at(cp)
            else:
                pos = event.position() + QPointF(self.geometry().topLeft())
                cp = pos - QPointF(self.canvas.geometry().topLeft())
                self.canvas.begin_stroke(cp)
        elif event.button() == Qt.MouseButton.RightButton:
            self._stop_drawing()

    def mouseMoveEvent(self, event) -> None:
        if self.pan_mode:
            if self._pan_last is not None:
                delta = event.globalPosition() - self._pan_last
                self._pan_last = event.globalPosition()
                self.canvas.shift_by(delta)
        elif not self.delete_mode:
            pos = event.position() + QPointF(self.geometry().topLeft())
            cp = pos - QPointF(self.canvas.geometry().topLeft())
            self.canvas.extend_stroke(cp)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.pan_mode:
                self._pan_last = None
                self.canvas.apply_offset()
            elif not self.delete_mode:
                self.canvas.end_stroke()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._stop_drawing()
        else:
            QApplication.sendEvent(self._toolbar_ref[0], event)


# ---------------------------------------------------------------------------
# Global hotkeys
# ---------------------------------------------------------------------------


class _HotkeySignals(QObject):
    toggle_focus = pyqtSignal()


class GlobalHotkeyThread(QThread):
    """Registers global hotkeys and polls until stop() is called."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.signals = _HotkeySignals()
        self._running = False

    def run(self) -> None:
        keyboard.add_hotkey("f8", self.signals.toggle_focus.emit)
        self._running = True
        while self._running:
            self.msleep(50)
        keyboard.unhook_all()

    def stop(self) -> None:
        self._running = False
        self.wait()


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

TOOL_ICONS = {
    Tool.PEN: ("pen", "Pen  [P]"),
    Tool.ERASER: ("eraser", "Eraser  [E]"),
    Tool.LINE: ("line", "Line  [L]"),
    Tool.ARROW: ("arrow", "Arrow  [A]"),
    Tool.RECT: ("rect", "Rectangle  [R]"),
    Tool.ELLIPSE: ("ellipse", "Ellipse  [O]"),
}

SIZES = list(range(2, 25))

PALETTE = [
    "#ff3b3b",  # red
    "#ff6b00",  # orange
    "#ffa726",  # amber
    "#ffd600",  # yellow
    "#aed581",  # sage
    "#00c853",  # green
    "#4db6ac",  # teal
    "#00bcd4",  # cyan
    "#2196f3",  # blue
    "#7c4dff",  # violet
    "#e040fb",  # magenta
    "#ff4081",  # hot pink
    "#ef9a9a",  # salmon
    "#795548",  # brown
    "#ffffff",  # white
    "#b0bec5",  # light grey
    "#90a4ae",  # blue-grey
    "#607d8b",  # grey
    "#263238",  # near-black
    "#000000",  # black
]

# ---------------------------------------------------------------------------
# Icon helpers
# ---------------------------------------------------------------------------

_ICONS_DIR: Path | None = None


def _init_icons_dir() -> None:
    global _ICONS_DIR
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    _ICONS_DIR = base / "media" / "icons"


def _svg_icon(name: str, size: int = 20) -> QIcon:
    path = _ICONS_DIR / f"{name}.svg"
    px = QPixmap(str(path))
    if not px.isNull():
        px = px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    icon = QIcon()
    icon.addPixmap(px)
    return icon


# ---------------------------------------------------------------------------
# Shared stylesheet constants
# ---------------------------------------------------------------------------

_PANEL_BG = "rgba(18, 18, 22, 218)"
_PANEL_BORDER = "rgba(255,255,255,18)"
_BTN_BG = "rgba(255,255,255,12)"
_BTN_HOVER = "rgba(255,255,255,26)"
_BTN_CHECKED = "#e07020"
_BTN_RADIUS = "6px"


def _base_btn(
    bg: str = _BTN_BG,
    hover: str = _BTN_HOVER,
    checked: str = _BTN_CHECKED,
    radius: str = _BTN_RADIUS,
    font_size: int = 15,
) -> str:
    return (
        f"QPushButton {{"
        f"  background: {bg}; color: #f0f0f0; border: none;"
        f"  border-radius: {radius}; font-size: {font_size}px;"
        f"  padding: 0px;"
        f"}}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:checked {{ background: {checked}; color: white; }}"
        f"QPushButton:pressed {{ background: rgba(255,255,255,40); }}"
    )


def _accent_btn() -> str:
    return _base_btn(bg="#1a5fa8", hover="#2272c3", checked="#e07020")


def _danger_btn() -> str:
    return _base_btn(bg="rgba(160,30,30,180)", hover="#c03030")


def _muted_btn() -> str:
    return _base_btn(bg="rgba(255,255,255,7)", hover=_BTN_HOVER, font_size=13)


class Toolbar(QWidget):
    def __init__(self, canvases: list[Canvas], captures: list[DrawCapture]) -> None:
        super().__init__()
        self.canvases = canvases
        self.captures = captures
        self._drawing_active = False
        self._pan_active = False
        self._delete_active = False
        self._size_index = 3  # index into SIZES → size 5
        self._prev_hwnd: int | None = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis")

        self._build_ui()
        self.resize(self.sizeHint())
        self.setFixedWidth(self.width())
        self._start_global_hotkeys()

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

        # ── drag handle + quit ────────────────────────────────────────
        _base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
        handle = _DragHandle("itralis", self, icon_path=_base / "media" / "icon.png")
        handle.setCursor(Qt.CursorShape.SizeAllCursor)

        quit_btn = QPushButton(_svg_icon("quit", 14), "")
        quit_btn.setToolTip("Quit  [Esc / Ctrl+Q]")
        quit_btn.setFixedSize(22, 22)
        quit_btn.setStyleSheet(_danger_btn())
        quit_btn.clicked.connect(self._quit)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        spacer = QWidget()
        spacer.setFixedSize(22, 22)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_row.addWidget(spacer)
        title_row.addWidget(handle, stretch=1)
        title_row.addWidget(quit_btn)
        root.addLayout(title_row)

        root.addWidget(_Divider())

        # ── draw / pan / delete ───────────────────────────────────────
        self._draw_btn = QPushButton(_svg_icon("draw", 16), "Draw")
        self._draw_btn.setCheckable(True)
        self._draw_btn.setToolTip("Activate drawing mode  [D]  ·  Focus: F8")
        self._draw_btn.setFixedHeight(34)
        self._draw_btn.setIconSize(self._draw_btn.sizeHint())
        self._draw_btn.setStyleSheet(_accent_btn())
        self._draw_btn.clicked.connect(self._toggle_drawing)
        root.addWidget(self._draw_btn)

        self._pan_btn = QPushButton(_svg_icon("pan", 14), "Pan")
        self._pan_btn.setCheckable(True)
        self._pan_btn.setToolTip("Drag to shift all drawings on the overlay")
        self._pan_btn.setFixedHeight(28)
        self._pan_btn.setStyleSheet(_muted_btn())
        self._pan_btn.clicked.connect(self._toggle_pan)
        root.addWidget(self._pan_btn)

        self._del_btn = QPushButton(_svg_icon("delete", 14), "Delete")
        self._del_btn.setCheckable(True)
        self._del_btn.setToolTip("Click near any stroke to remove it")
        self._del_btn.setFixedHeight(28)
        self._del_btn.setStyleSheet(_muted_btn())
        self._del_btn.clicked.connect(self._toggle_delete)
        root.addWidget(self._del_btn)

        root.addWidget(_Divider())

        # ── tool grid (3 × 2) ─────────────────────────────────────────
        self._tool_btns: dict[Tool, QPushButton] = {}
        tool_list = list(TOOL_ICONS.items())
        for row in range(3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(3)
            for col in range(2):
                tool, (icon_name, tip) = tool_list[row * 2 + col]
                btn = QPushButton(_svg_icon(icon_name, 18), "")
                btn.setToolTip(tip)
                btn.setFixedSize(36, 32)
                btn.setCheckable(True)
                btn.setStyleSheet(_base_btn())
                btn.clicked.connect(lambda checked, t=tool: self._select_tool(t))
                row_layout.addWidget(btn)
                self._tool_btns[tool] = btn
            root.addLayout(row_layout)

        root.addWidget(_Divider())

        # ── color swatches (4 rows × 5 + custom row) ─────────────────
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
                btn.setStyleSheet(self._swatch_style(hex_color, False))
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
        self._custom_btn.setIcon(_svg_icon("plus", 10))
        self._custom_btn.clicked.connect(self._pick_custom_color)
        custom_row.addStretch()
        custom_row.addWidget(self._custom_btn)
        custom_row.addStretch()
        root.addLayout(custom_row)

        root.addWidget(_Divider())

        # ── size control ──────────────────────────────────────────────
        size_row = QHBoxLayout()
        size_row.setSpacing(4)

        size_lbl = QLabel("Size")
        size_lbl.setStyleSheet("color: rgba(255,255,255,110); font-size: 10px;")
        size_row.addWidget(size_lbl)
        size_row.addStretch()

        minus_btn = QPushButton(_svg_icon("minus", 12), "")
        minus_btn.setFixedSize(24, 22)
        minus_btn.setToolTip("Decrease stroke size")
        minus_btn.setStyleSheet(_muted_btn())
        minus_btn.clicked.connect(self._size_down)

        self._size_lbl = QLabel(str(SIZES[self._size_index]))
        self._size_lbl.setFixedWidth(24)
        self._size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
        self._size_lbl.setToolTip("Current stroke size (px)")

        plus_btn = QPushButton(_svg_icon("plus", 12), "")
        plus_btn.setFixedSize(24, 22)
        plus_btn.setToolTip("Increase stroke size")
        plus_btn.setStyleSheet(_muted_btn())
        plus_btn.clicked.connect(self._size_up)

        size_row.addWidget(minus_btn)
        size_row.addWidget(self._size_lbl)
        size_row.addWidget(plus_btn)
        root.addLayout(size_row)

        root.addWidget(_Divider())

        # ── secondary actions ─────────────────────────────────────────
        act_row = QHBoxLayout()
        act_row.setSpacing(3)

        undo_btn = QPushButton(_svg_icon("undo", 16), "")
        undo_btn.setToolTip("Undo  [Z]")
        undo_btn.setFixedSize(36, 28)
        undo_btn.setStyleSheet(_muted_btn())
        undo_btn.clicked.connect(self._undo)

        self._vis_btn = QPushButton(_svg_icon("hide", 16), "")
        self._vis_btn.setCheckable(True)
        self._vis_btn.setToolTip("Hide overlay  [H]")
        self._vis_btn.setFixedSize(36, 28)
        self._vis_btn.setStyleSheet(_muted_btn())
        self._vis_btn.clicked.connect(self._toggle_visibility)

        clear_btn = QPushButton(_svg_icon("clear", 16), "")
        clear_btn.setToolTip("Clear all  [Del]")
        clear_btn.setFixedSize(36, 28)
        clear_btn.setStyleSheet(_muted_btn())
        clear_btn.clicked.connect(self._clear)

        for b in (undo_btn, self._vis_btn, clear_btn):
            act_row.addWidget(b)
        root.addLayout(act_row)

        # ── panel shell ───────────────────────────────────────────────
        self._set_panel_style(active=False)

        # defaults
        self._select_tool(Tool.PEN)
        self._select_color(PALETTE[0], self._swatch_btns[0])
        self._setup_shortcuts()

    def _set_panel_style(self, active: bool) -> None:
        border_color = "#e07020" if active else _PANEL_BORDER
        border_width = "2px" if active else "1px"
        self.setStyleSheet(
            f"QWidget#toolbar_panel {{"
            f"  background: {_PANEL_BG};"
            f"  border-radius: 10px;"
            f"  border: {border_width} solid {border_color};"
            f"}}"
        )
        # wrap content in a named container so QSS scoping works
        if hasattr(self, "_panel"):
            self._panel.setStyleSheet(
                f"background: {_PANEL_BG}; border-radius: 10px;border: {border_width} solid {border_color};"
            )

    def _setup_shortcuts(self) -> None:
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self, activated=fn)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)

        sc("D", lambda: self._toggle_drawing(not self._drawing_active))
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

    # ------------------------------------------------------------------
    # Swatch styling
    # ------------------------------------------------------------------

    @staticmethod
    def _swatch_style(color: str, selected: bool) -> str:
        if selected:
            return (
                f"QPushButton {{ background: {color}; border: 2px solid white;"
                f"border-radius: 3px; outline: none; }}"
                f"QPushButton:hover {{ border: 2px solid white; }}"
            )
        return (
            f"QPushButton {{ background: {color}; border: 1px solid rgba(255,255,255,40);"
            f"border-radius: 3px; }}"
            f"QPushButton:hover {{ border: 2px solid rgba(255,255,255,180); }}"
        )

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        for t, btn in self._tool_btns.items():
            btn.setChecked(t == tool)
        for canvas in self.canvases:
            canvas.active_tool = tool

    # ------------------------------------------------------------------
    # Color
    # ------------------------------------------------------------------

    def _select_color(self, color: str, source_btn: QPushButton) -> None:
        self._color = color
        for i, btn in enumerate(self._swatch_btns):
            selected = btn is source_btn
            btn.setChecked(selected)
            btn.setFixedSize(20 if selected else 18, 20 if selected else 18)
            btn.setStyleSheet(self._swatch_style(PALETTE[i], selected))
        for canvas in self.canvases:
            canvas.active_color = color

    def _pick_custom_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "Pick color")
        if color.isValid():
            self._color = color.name()
            for i, btn in enumerate(self._swatch_btns):
                btn.setChecked(False)
                btn.setFixedSize(18, 18)
                btn.setStyleSheet(self._swatch_style(PALETTE[i], False))
            for canvas in self.canvases:
                canvas.active_color = self._color

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

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
    # Drawing mode
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
            self._draw_btn.setStyleSheet(_base_btn(bg="#e07020", hover="#f08030", checked="#e07020"))
        else:
            self._draw_btn.setText("Draw")
            self._draw_btn.setStyleSheet(_accent_btn())
        self._set_panel_style(active=checked)
        for cap in self.captures:
            cap.pan_mode = False
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def _stop_drawing(self) -> None:
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
            self._pan_btn.setStyleSheet(_base_btn(bg="#357a50", hover="#47a368", checked="#357a50"))
        else:
            self._pan_btn.setText("Pan")
            self._pan_btn.setStyleSheet(_muted_btn())
        for cap in self.captures:
            cap.pan_mode = checked
            cap.setCursor(Qt.CursorShape.OpenHandCursor if checked else Qt.CursorShape.CrossCursor)
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def _stop_pan(self) -> None:
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
            self._del_btn.setStyleSheet(_base_btn(bg="#7a1a1a", hover="#b02020", checked="#7a1a1a"))
        else:
            self._del_btn.setText("Delete")
            self._del_btn.setStyleSheet(_muted_btn())
        for cap in self.captures:
            cap.delete_mode = checked
            cap.setCursor(Qt.CursorShape.ForbiddenCursor if checked else Qt.CursorShape.CrossCursor)
            if checked:
                cap.show()
                cap.raise_()
                cap.activateWindow()
            else:
                cap.hide()

    def _stop_delete(self) -> None:
        self._toggle_delete(False)

    # ------------------------------------------------------------------
    # Undo / clear / visibility
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
        self._vis_btn.setIcon(_svg_icon("show" if checked else "hide", 16))
        self._vis_btn.setToolTip("Show overlay  [H]" if checked else "Hide overlay  [H]")
        for canvas in self.canvases:
            if checked:
                canvas.hide()
            else:
                canvas.show()
                canvas.raise_()

    # ------------------------------------------------------------------
    # Panel background painting (rounded corners)
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


# ---------------------------------------------------------------------------
# Divider helper
# ---------------------------------------------------------------------------


class _Divider(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet("background: rgba(255,255,255,20);")


class _DragHandle(QWidget):
    """Widget with icon + label that delegates mouse events to the parent window for dragging."""

    def __init__(self, text: str, parent: QWidget, icon_path: Path | None = None) -> None:
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


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------


def _make_app_icon() -> QIcon:
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    icon_path = base / "media" / "icon.png"
    source = QPixmap(str(icon_path))
    icon = QIcon()
    if not source.isNull():
        for size in (16, 32, 48, 64, 128, 256):
            icon.addPixmap(
                source.scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
    else:
        px = QPixmap(256, 256)
        px.fill(QColor("#0d1420"))
        icon.addPixmap(px)
    return icon


def make_tray_icon(app: QApplication, toolbar: Toolbar) -> QSystemTrayIcon:
    icon = _make_app_icon()

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Vitralis")

    menu = QMenu()
    show_action = menu.addAction("Show toolbar")
    hide_action = menu.addAction("Hide toolbar")
    menu.addSeparator()
    quit_action = menu.addAction("Quit")

    show_action.triggered.connect(toolbar.show)
    hide_action.triggered.connect(toolbar.hide)
    quit_action.triggered.connect(toolbar._quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: toolbar.show() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
    )
    tray.show()
    return tray


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    with contextlib.suppress(Exception):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ran.vitralis")

    _init_icons_dir()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        "QToolTip { background: #1e1e26; color: #f0f0f0; border: 1px solid rgba(255,255,255,40);"
        "border-radius: 4px; padding: 4px 6px; font-size: 12px; }"
    )

    screens = app.screens()

    canvases: list[Canvas] = []
    captures: list[DrawCapture] = []
    toolbar_ref: list[Toolbar] = []

    for screen in screens:
        geo = screen.geometry()
        canvas = Canvas(geo)
        canvas.load(load_strokes_for(geo))
        canvas.show()

        def _stop_active():
            toolbar_ref[0]._stop_drawing()
            toolbar_ref[0]._stop_pan()
            toolbar_ref[0]._stop_delete()

        capture = DrawCapture(canvas, geo, stop_drawing=_stop_active, toolbar=toolbar_ref)
        capture.setWindowFlags(capture.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        canvases.append(canvas)
        captures.append(capture)

    app_icon = _make_app_icon()
    app.setWindowIcon(app_icon)

    toolbar = Toolbar(canvases, captures)
    toolbar.setWindowIcon(app_icon)
    toolbar_ref.append(toolbar)
    primary = app.primaryScreen().geometry()
    toolbar.move(primary.x() + 20, primary.y() + 20)
    toolbar.show()

    _tray = make_tray_icon(app, toolbar)  # noqa: F841 — must stay alive

    app.aboutToQuit.connect(toolbar._hotkey_thread.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
