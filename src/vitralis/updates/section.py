#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:03.066760
Revised: 2026/11/13 09:11:03.461213

The Updates section of the settings window: the running version, what the last check found (or why it
failed), the **Check for new versions** switch, **Check now**, **Release notes** and **Skip this version** /
**Don't skip**, and in the packaged exe **Install {version}**, the download's progress and **Restart to
update**. Buttons with nothing to do are dimmed; the install button only shows when installing is possible.
"""

from collections.abc import Callable

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vitralis.styles import accent_btn, muted_btn
from vitralis.translations import t
from vitralis.updates.checker import InstallKind, UpdateChecker, UpdateStatus
from vitralis.updates.messages import (
    CHECK_SWITCH,
    INSTALL,
    RELEASE_NOTES,
    RESTART,
    RUNNING,
    SKIP,
    UNSKIP,
    error_line,
    install_line,
    result_line,
)

_NAME = "color: rgba(255,255,255,180); font-size: 11px; background: transparent;"
_VALUE = "color: rgba(255,255,255,220); font-size: 11px; background: transparent;"
_ERROR = "color: #ff8a65; font-size: 11px; background: transparent;"
_SWITCH = (
    "QCheckBox { color: rgba(255,255,255,180); font-size: 11px; background: transparent; }"
    "QCheckBox:disabled { color: rgba(255,255,255,80); }"
)


def _button(style: str, minimum: int) -> QPushButton:
    button = QPushButton()
    button.setFixedHeight(26)
    button.setMinimumWidth(minimum)
    button.setStyleSheet(style)
    return button


class UpdatesSection(QWidget):
    def __init__(
        self,
        updates: UpdateChecker,
        quit_app: Callable[[], None] | None = None,
        open_url: Callable[[QUrl], object] = QDesktopServices.openUrl,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._updates = updates
        self._quit_app = quit_app
        self._open_url = open_url
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.version_label = QLabel()
        self.version_label.setStyleSheet(_NAME)
        layout.addWidget(self.version_label)
        self.result_label = self._wrapped(_VALUE, layout)
        self.error_label = self._wrapped(_ERROR, layout)
        self.install_label = self._wrapped(_VALUE, layout)

        self.switch = QCheckBox()
        self.switch.setStyleSheet(_SWITCH)
        self.switch.setChecked(updates.check_enabled)
        self.switch.toggled.connect(updates.set_check_enabled)
        layout.addWidget(self.switch)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.notes_button = _button(muted_btn(), 90)
        self.notes_button.clicked.connect(self._open_notes)
        self.skip_button = _button(muted_btn(), 110)
        self.skip_button.clicked.connect(self._toggle_skip)
        self.check_button = _button(muted_btn(), 90)
        self.check_button.clicked.connect(updates.check_now)
        row.addWidget(self.notes_button)
        row.addWidget(self.skip_button)
        row.addStretch()
        row.addWidget(self.check_button)
        layout.addLayout(row)

        install_row = QHBoxLayout()
        install_row.setContentsMargins(0, 0, 0, 0)
        install_row.addStretch()
        self.install_button = _button(accent_btn(), 130)
        self.install_button.clicked.connect(self._install)
        install_row.addWidget(self.install_button)
        layout.addLayout(install_row)

        updates.changed.connect(self._show)
        updates.busy_changed.connect(self._show_busy)
        self.retranslate()

    @staticmethod
    def _wrapped(style: str, layout: QVBoxLayout) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setStyleSheet(style)
        label.hide()
        layout.addWidget(label)
        return label

    def retranslate(self) -> None:
        self.switch.setText(t(CHECK_SWITCH))
        self.notes_button.setText(t(RELEASE_NOTES))
        self._show(self._updates.status)
        self._show_busy(self._updates.busy)

    # --- actions --------------------------------------------------------------------------------------------

    def _open_notes(self) -> None:
        latest = self._updates.status.latest
        if latest is not None:
            self._open_url(QUrl(latest.page_url))

    def _toggle_skip(self) -> None:
        if self._updates.status.offered is not None:
            self._updates.skip()
        else:
            self._updates.unskip()

    def _install(self) -> None:
        if self._updates.status.install.kind is InstallKind.READY:
            if self._quit_app is not None:
                self._updates.restart_to_update(self._quit_app)
        else:
            self._updates.install()

    # --- showing --------------------------------------------------------------------------------------------

    @staticmethod
    def _set_line(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def _show(self, status: UpdateStatus) -> None:
        self.version_label.setText(t(RUNNING).format(version=status.current))
        self._set_line(self.result_label, result_line(status))
        self._set_line(self.error_label, error_line(status))
        install = status.install
        self._set_line(self.install_label, install_line(install))
        self.install_label.setStyleSheet(_ERROR if install.kind is InstallKind.FAILED else _VALUE)

        self.notes_button.setEnabled(status.latest is not None)
        self.skip_button.setText(t(SKIP) if status.offered is not None or not status.newer else t(UNSKIP))
        self.skip_button.setEnabled(status.newer and install.kind is not InstallKind.DOWNLOADING)

        ready = install.kind is InstallKind.READY
        self.install_button.setVisible(ready or status.can_install)
        if ready:
            self.install_button.setText(t(RESTART))
            self.install_button.setEnabled(self._quit_app is not None)
        elif status.offered is not None:
            self.install_button.setText(t(INSTALL).format(version=status.offered.version))
            self.install_button.setEnabled(install.kind is not InstallKind.DOWNLOADING)

    def _show_busy(self, busy: bool) -> None:
        self.check_button.setText(t("Checking…") if busy else t("Check now"))
        self.check_button.setEnabled(not busy)
