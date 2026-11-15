#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.249417
Revised: 2026/11/15 14:26:59.290192

The About window: the logo, the app with a one-line description, its version and which build it is, the
author, the company that publishes it (Breren, with its logo and site), the licence with a way to read it and
the bundled third-party code's, and the links to the source, the releases, the changelog and where to report
a problem. Its own panel beside the toolbar rather than a section of Settings, which already fills the height
of a 1080p screen.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from vitralis.icons import media_base
from vitralis.styles import danger_btn
from vitralis.translations import t
from vitralis.version import LICENCE_NAME
from vitralis.widgets import Divider, Panel

REPOSITORY = "https://github.com/Ran-n/vitralis"
COMPANY = "Breren"
COMPANY_SITE = "https://breren.com"
LICENCE_URL = f"{REPOSITORY}/blob/main/LICENSE"
THIRD_PARTY_URL = f"{REPOSITORY}/blob/main/THIRD-PARTY-NOTICES.md"
LINKS = (
    ("Source code", REPOSITORY),
    ("Releases", f"{REPOSITORY}/releases"),
    ("Changelog", f"{REPOSITORY}/blob/main/CHANGELOG.md"),
    ("Report a problem", f"{REPOSITORY}/issues"),
)
DESCRIPTION = "Draw over your screen"
BUILT_FROM_SOURCE = "built from source"

_LBL = "color: rgba(255,255,255,60); font-size: 10px; background: transparent; letter-spacing: 0.5px;"
_VAL = "color: rgba(255,255,255,200); font-size: 12px; background: transparent;"
_LINK = "color: rgba(255,255,255,200); font-size: 11px; background: transparent;"
_LINK_COLOUR = "#8ab4f8"


def build_text(version: str, target: str | None) -> str:
    """``1.4.0 · windows-x86_64``, or ``1.4.0 · built from source``."""
    return f"v{version} · {target if target else t(BUILT_FROM_SOURCE)}"


def _anchor(url: str, text: str) -> str:
    return f'<a href="{url}" style="color: {_LINK_COLOUR}; text-decoration: none;">{text}</a>'


class InfoWindow(Panel):
    def __init__(self, version: str, target: str | None = None, parent=None) -> None:
        super().__init__(f"Vitralis — {t('About')}", parent)
        self._version = version
        self._target = target
        self._field_labels: list[QLabel] = []
        self._build_ui()
        self.retranslate()

    def _logo(self, name: str, size: int) -> QLabel | None:
        path = media_base() / "media" / "logo" / name
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        label = QLabel()
        label.setPixmap(
            pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: transparent;")
        return label

    def _field(self, root: QVBoxLayout, key: str, value: QLabel | QHBoxLayout) -> None:
        col = QVBoxLayout()
        col.setSpacing(1)
        lbl = QLabel()
        lbl.setStyleSheet(_LBL)
        lbl.setProperty("i18n_key", key)
        self._field_labels.append(lbl)
        col.addWidget(lbl)
        if isinstance(value, QLabel):
            col.addWidget(value)
        else:
            col.addLayout(value)
        root.addLayout(col)
        root.addSpacing(10)

    @staticmethod
    def _value(text: str = "", style: str = _VAL) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(style)
        label.setWordWrap(True)
        return label

    def _link(self) -> QLabel:
        label = self._value(style=_LINK)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        return label

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 18)
        root.setSpacing(0)

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

        logo = self._logo("icon.png", 96)
        if logo is not None:
            logo_row = QHBoxLayout()
            logo_row.addStretch()
            logo_row.addWidget(logo)
            logo_row.addStretch()
            root.addLayout(logo_row)
            root.addSpacing(8)
        name = QLabel("Vitralis")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("color: white; font-size: 15px; font-weight: 700; background: transparent;")
        root.addWidget(name)
        self.description = self._value(style=_LINK)
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.description)

        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        self.build_label = self._value()
        self._field(root, "Version", self.build_label)
        root.addWidget(Divider())
        root.addSpacing(10)
        self._field(root, "Author", self._value("Ran#"))
        self._field(root, "Email", self._value("ran.hash@proton.me"))

        company = QHBoxLayout()
        company.setSpacing(6)
        mark = self._logo("breren.svg", 18)
        if mark is not None:
            company.addWidget(mark)
        self.company_link = self._link()
        self.company_link.setText(_anchor(COMPANY_SITE, COMPANY))
        self.company_link.setStyleSheet(_VAL)
        company.addWidget(self.company_link)
        company.addStretch()
        self._field(root, "Company", company)

        self.licence_label = self._link()
        self._field(root, "License", self.licence_label)
        root.addWidget(Divider())
        root.addSpacing(10)
        self.links_label = self._link()
        self._field(root, "Links", self.links_label)

    def retranslate(self) -> None:
        for lbl in self._field_labels:
            lbl.setText(t(lbl.property("i18n_key")).upper())
        self.setWindowTitle(f"Vitralis — {t('About')}")
        self.description.setText(t(DESCRIPTION))
        self.build_label.setText(build_text(self._version, self._target))
        self.licence_label.setText(
            f"{LICENCE_NAME}<br>{_anchor(LICENCE_URL, t('Read the license'))}"
            f"<br>{_anchor(THIRD_PARTY_URL, t('Third-party licenses'))}"
        )
        self.links_label.setText("<br>".join(_anchor(url, t(text)) for text, url in LINKS))
