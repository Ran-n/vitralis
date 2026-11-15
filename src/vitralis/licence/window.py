#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.249623
Revised: 2026/11/15 21:40:09.524443

The licence window: what Vitralis shows instead of its overlay until a key is activated on this computer, and
again whenever the licence stops holding. It says why (one message per outcome), takes a key, and offers an
online check when one can unlock it by itself. Closing it quits Vitralis, since nothing else runs while locked.
"""

import logging
from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from vitralis.licence import look
from vitralis.licence.gate import LicenceGate
from vitralis.licence.messages import CHECKABLE, PRIVACY, status_message
from vitralis.licence.rules import LicenceStatus, normalize_key
from vitralis.styles import accent_btn, muted_btn
from vitralis.translations import t

logger = logging.getLogger("vitralis.licence.window")


class LicenceWindow(QWidget):
    def __init__(self, gate: LicenceGate, quit_app: Callable[[], None] | None = None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self._gate = gate
        self._quit_app = quit_app if quit_app is not None else QApplication.quit
        self._status: LicenceStatus | None = None
        self._busy = False
        self._dismissed = False
        self._dragging = False
        self._drag_pos = QPoint()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Vitralis — " + t("License"))
        self.setFixedWidth(look.WIDTH)
        self._build_ui()
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 18)
        root.setSpacing(10)
        self.close_button = QPushButton()
        self.close_button.setToolTip(t("Quit"))
        self.close_button.clicked.connect(self.close)
        root.addLayout(look.close_row(self.close_button))
        picture = look.logo()
        if picture is not None:
            root.addWidget(picture)
        root.addWidget(look.text_label(look.TITLE, "Vitralis"))
        self.message = look.text_label(look.MESSAGE)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.message)
        self._build_key_part(root)
        self.privacy = look.text_label(look.NOTE, t(PRIVACY))
        root.addWidget(self.privacy)
        self._update_buttons()

    def _build_key_part(self, root: QVBoxLayout) -> None:
        """The key field, **Activate**, **Check again** and the line that says what went wrong."""
        self.key_field = look.key_field()
        self.key_field.textChanged.connect(self._update_buttons)
        self.key_field.returnPressed.connect(self._activate)
        root.addWidget(self.key_field)
        self.activate_button = QPushButton()
        self.activate_button.setFixedHeight(34)
        self.activate_button.setStyleSheet(accent_btn())
        self.activate_button.clicked.connect(self._activate)
        root.addWidget(self.activate_button)
        self.check_button = QPushButton()
        self.check_button.setFixedHeight(26)
        self.check_button.setStyleSheet(muted_btn())
        self.check_button.clicked.connect(self._check)
        root.addWidget(self.check_button)
        self.error_label = look.text_label(look.ERROR)
        self.error_label.hide()
        root.addWidget(self.error_label)

    # --- LicencePrompt ----------------------------------------------------------------------------------------

    def show_status(self, status: LicenceStatus) -> None:
        self._status = status
        self.message.setText(status_message(status))
        self.error_label.hide()
        self._update_buttons()
        if not self.isVisible():
            self.adjustSize()
            self._center()
        self.bring_to_front()

    def bring_to_front(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.key_field.setFocus()

    def show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()
        self.adjustSize()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.key_field.setEnabled(not busy)
        self._update_buttons()

    def dismiss(self) -> None:
        """Close without quitting: the licence holds again, or the app is quitting anyway."""
        self._dismissed = True
        self.close()
        self.deleteLater()

    # --- actions ----------------------------------------------------------------------------------------------

    def _activate(self) -> None:
        if self.activate_button.isEnabled():
            self.error_label.hide()
            self._gate.activate(self.key_field.text())

    def _check(self) -> None:
        if self.check_button.isEnabled():
            self.error_label.hide()
            self._gate.check_now()

    def _update_buttons(self) -> None:
        busy = self._busy
        self.activate_button.setText(t("Activating…") if busy else t("Activate"))
        self.activate_button.setEnabled(not busy and normalize_key(self.key_field.text()) is not None)
        # by the saved licence, not the last attempt's outcome: a refused key leaves a check as possible as before
        checkable = self._status is not None and CHECKABLE & {self._status.kind, self._gate.status().kind}
        checkable = bool(checkable)
        self.check_button.setVisible(checkable)
        self.check_button.setText(t("Checking…") if busy else t("Check again"))
        self.check_button.setEnabled(checkable and not busy)

    def _center(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())

    # --- window -----------------------------------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        event.accept()
        if not self._dismissed:  # the user closed it while locked: nothing else runs, so Vitralis quits
            self._quit_app()

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
        look.paint_panel(self)
