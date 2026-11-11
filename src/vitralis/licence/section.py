#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.311334
Revised: 2026/11/11 11:06:53.776094

The License section of the settings window: whether this is a test licence, whether it is permanent or until
when, and until when it works offline (highlighted when that is under 5 days away), with **Check now**, which
checks online off the UI thread.
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from vitralis.licence.gate import LicenceGate
from vitralis.licence.messages import format_date, offline_running_low, status_message
from vitralis.licence.rules import LicenceStatus
from vitralis.styles import muted_btn
from vitralis.translations import t

_NAME = "color: rgba(255,255,255,180); font-size: 11px; background: transparent;"
_VALUE = "color: rgba(255,255,255,220); font-size: 11px; background: transparent;"
_LOW = "color: #ffa726; font-size: 11px; font-weight: 700; background: transparent;"
_ERROR = "color: #ff8a65; font-size: 11px; background: transparent;"
_ROWS = ("Status", "Valid until", "Works offline until")


class LicenceSection(QWidget):
    def __init__(self, gate: LicenceGate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gate = gate
        self._names: dict[str, QLabel] = {}
        self.values: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for key in _ROWS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            name = QLabel(t(key))
            name.setStyleSheet(_NAME)
            name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value = QLabel()
            value.setStyleSheet(_VALUE)
            row.addWidget(name)
            row.addWidget(value)
            layout.addLayout(row)
            self._names[key], self.values[key] = name, value

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(_ERROR)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch()
        self.check_button = QPushButton()
        self.check_button.setFixedHeight(26)
        self.check_button.setMinimumWidth(110)
        self.check_button.setStyleSheet(muted_btn())
        self.check_button.clicked.connect(self._check)
        button_row.addWidget(self.check_button)
        layout.addLayout(button_row)

        gate.changed.connect(self._show)
        gate.busy_changed.connect(self._show_busy)
        gate.error.connect(self._show_error)
        self._show(gate.status())
        self._show_busy(gate.busy)

    def retranslate(self) -> None:
        for key, label in self._names.items():
            label.setText(t(key))
        self._show(self._gate.status())
        self._show_busy(self._gate.busy)

    def _check(self) -> None:
        self.error_label.hide()
        self._gate.check_now()

    def _show(self, status: LicenceStatus) -> None:
        if not status.licensed:  # the app is locking; the licence window says why
            self.values["Status"].setText(status_message(status))
            return
        self.values["Status"].setText(t("Test license") if status.test else t("Licensed"))
        expires = status.licence_expires_at
        self.values["Valid until"].setText(t("Permanent") if expires is None else format_date(expires))
        offline = self.values["Works offline until"]
        offline.setText("—" if status.offline_until is None else format_date(status.offline_until))
        offline.setStyleSheet(_LOW if offline_running_low(status, self._gate.server_time()) else _VALUE)

    def _show_busy(self, busy: bool) -> None:
        self.check_button.setText(t("Checking…") if busy else t("Check now"))
        self.check_button.setEnabled(not busy)

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()
