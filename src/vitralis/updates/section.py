#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:03.066760
Revised: 2026/11/15 14:27:03.443893

The Updates section of the settings window: the running version and which build it is, what the last check
found (or why it failed), **Check for updates automatically**, **Check now**, **Release notes** and **Skip
this version** / **Stop skipping {version}**, and in the packaged exe **Update and restart** with the
download's progress and **Cancel**. Buttons with nothing to do are dimmed; the update button only shows when
installing is possible. A build from source shows its version and how to update it, and no controls.
"""

from collections.abc import Callable

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vitralis.styles import accent_btn, muted_btn
from vitralis.translations import t
from vitralis.updates.checker import InstallKind, UpdateChecker, UpdateStatus
from vitralis.updates.messages import (
    CANCEL,
    CHECK_SWITCH,
    RELEASE_NOTES,
    SKIP,
    UNSKIP,
    UPDATE,
    error_line,
    install_line,
    result_line,
    version_line,
)
from vitralis.updates.rules import CheckKind

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

        self._controls = (self.switch, self.notes_button, self.skip_button, self.check_button)
        """What a build from source doesn't show: it never checks."""
        for control in self._controls:
            control.setVisible(not updates.is_source_build)

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
        if self._skipping(self._updates.status):
            self._updates.unskip()
        else:
            self._updates.skip()

    @staticmethod
    def _skipping(status: UpdateStatus) -> bool:
        return status.kind is CheckKind.SKIPPED

    def _install(self) -> None:
        if self._updates.status.install.kind is InstallKind.DOWNLOADING:
            self._updates.cancel()
        elif self._quit_app is not None:
            self._updates.install(self._quit_app)

    # --- showing --------------------------------------------------------------------------------------------

    @staticmethod
    def _set_line(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def _show(self, status: UpdateStatus) -> None:
        self.version_label.setText(version_line(status))
        self._set_line(self.result_label, result_line(status))
        self._set_line(self.error_label, error_line(status))
        install = status.install
        self._set_line(self.install_label, install_line(install))
        self.install_label.setStyleSheet(_ERROR if install.kind is InstallKind.FAILED else _VALUE)

        self.notes_button.setEnabled(status.latest is not None)
        skipping = self._skipping(status)
        version = "" if status.latest is None else str(status.latest.version)
        self.skip_button.setText(t(UNSKIP).format(version=version) if skipping else t(SKIP))
        under_way = install.kind in (InstallKind.DOWNLOADING, InstallKind.REPLACING)
        self.skip_button.setEnabled((skipping or status.offer is not None) and not under_way)

        self.install_button.setVisible(under_way or status.can_install)
        if install.kind is InstallKind.DOWNLOADING:
            self.install_button.setText(t(CANCEL))
            self.install_button.setEnabled(True)
        else:
            self.install_button.setText(t(UPDATE))
            self.install_button.setEnabled(self._quit_app is not None and install.kind is not InstallKind.REPLACING)

    def _show_busy(self, busy: bool) -> None:
        self.check_button.setText(t("Checking…") if busy else t("Check now"))
        self.check_button.setEnabled(not busy)
