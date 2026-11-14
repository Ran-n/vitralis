#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.249417
Revised: 2026/11/14 12:31:22.249417

The About window: the logo, the app and its version, the author and the licence.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from vitralis.icons import media_base
from vitralis.styles import danger_btn
from vitralis.translations import t
from vitralis.version import LICENCE_NAME
from vitralis.widgets import Divider, Panel


class InfoWindow(Panel):
    def __init__(self, version: str, parent=None) -> None:
        super().__init__(f"Vitralis — {t('About')}", parent)
        self._build_ui(version)

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
        root.addWidget(Divider())
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
        root.addWidget(Divider())
        root.addSpacing(10)
        for key, value in [
            ("Author", "Ran#"),
            ("Email", "ran.hash@proton.me"),
            ("License", LICENCE_NAME),
        ]:
            col, lbl = _field(key, value)
            root.addLayout(col)
            root.addSpacing(10)
            self._field_labels.append(lbl)

    def retranslate(self) -> None:
        for lbl in self._field_labels:
            lbl.setText(t(lbl.property("i18n_key")).upper())
        self.setWindowTitle(f"Vitralis — {t('About')}")
