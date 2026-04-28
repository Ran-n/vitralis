#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 15:57:04.270010
Revised: 2026/04/28 15:57:04.270010
"""

from vitralis.models import Tool

PANEL_BG = "rgba(18, 18, 22, 218)"
PANEL_BORDER = "rgba(255,255,255,18)"
BTN_BG = "rgba(255,255,255,12)"
BTN_HOVER = "rgba(255,255,255,26)"
BTN_CHECKED = "#e07020"
BTN_RADIUS = "6px"

TOOL_ICONS: dict[Tool, tuple[str, str]] = {
    Tool.PEN: ("pen", "Pen  [P]"),
    Tool.ERASER: ("eraser", "Eraser  [E]"),
    Tool.LINE: ("line", "Line  [L]"),
    Tool.ARROW: ("arrow", "Arrow  [A]"),
    Tool.RECT: ("rect", "Rectangle  [R]"),
    Tool.ELLIPSE: ("ellipse", "Ellipse  [O]"),
}

SIZES = list(range(2, 25))

PALETTE = [
    "#ff3b3b",
    "#ff6b00",
    "#ffa726",
    "#ffd600",
    "#aed581",
    "#00c853",
    "#4db6ac",
    "#00bcd4",
    "#2196f3",
    "#7c4dff",
    "#e040fb",
    "#ff4081",
    "#ef9a9a",
    "#795548",
    "#ffffff",
    "#b0bec5",
    "#90a4ae",
    "#607d8b",
    "#263238",
    "#000000",
]


def base_btn(
    bg: str = BTN_BG,
    hover: str = BTN_HOVER,
    checked: str = BTN_CHECKED,
    radius: str = BTN_RADIUS,
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


def accent_btn() -> str:
    return base_btn(bg="#1a5fa8", hover="#2272c3", checked="#e07020")


def danger_btn() -> str:
    return base_btn(bg="rgba(160,30,30,180)", hover="#c03030")


def muted_btn() -> str:
    return base_btn(bg="rgba(255,255,255,7)", hover=BTN_HOVER, font_size=13)


def swatch_style(color: str, selected: bool) -> str:
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
