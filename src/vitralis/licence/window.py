#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.249623
Revised: 2026/11/14 12:31:23.753148

The licence window: what Vitralis shows instead of its overlay until a key is activated on this computer, and
again whenever the licence stops holding. It says why (one message per outcome), takes a key, and offers an
online check when one can unlock it by itself. Closing it quits Vitralis, since nothing else runs while locked.
"""

from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vitralis.icons import media_base
from vitralis.licence.gate import LicenceGate
from vitralis.licence.messages import CHECKABLE, PRIVACY, status_message
from vitralis.licence.rules import LicenceStatus, normalize_key
from vitralis.styles import accent_btn, danger_btn, muted_btn
from vitralis.translations import t
from vitralis.widgets import LineEdit

KEY_PLACEHOLDER = "BRN-XXXX-XXXX-XXXX-XXXX"
WIDTH = 380
_MESSAGE = "color: rgba(255,255,255,210); font-size: 12px; background: transparent;"
_ERROR = "color: #ff8a65; font-size: 11px; background: transparent;"
_NOTE = "color: rgba(255,255,255,90); font-size: 10px; background: transparent;"
_FIELD = (
    "QLineEdit { background: rgba(255,255,255,10); color: #f0f0f0; border: 1px solid rgba(255,255,255,30);"
    "border-radius: 6px; padding: 6px 8px; font-size: 14px; font-family: Consolas, monospace; }"
    "QLineEdit:focus { border: 1px solid #2272c3; }"
    "QLineEdit:disabled { color: rgba(255,255,255,80); }"
)


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
        self.setFixedWidth(WIDTH)
        self._build_ui()
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 18)
        root.setSpacing(10)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setStyleSheet(danger_btn())
        self.close_button.setToolTip(t("Quit"))
        self.close_button.clicked.connect(self.close)
        close_row.addWidget(self.close_button)
        root.addLayout(close_row)

        icon_path = media_base() / "media" / "logo" / "icon.png"
        if icon_path.exists():
            logo = QLabel()
            logo.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setStyleSheet("background: transparent;")
            root.addWidget(logo)

        title = QLabel("Vitralis")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 700; background: transparent;")
        root.addWidget(title)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message.setStyleSheet(_MESSAGE)
        root.addWidget(self.message)

        self.key_field = LineEdit()
        self.key_field.setPlaceholderText(KEY_PLACEHOLDER)
        self.key_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_field.setStyleSheet(_FIELD)
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

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet(_ERROR)
        self.error_label.hide()
        root.addWidget(self.error_label)

        self.privacy = QLabel(t(PRIVACY))
        self.privacy.setWordWrap(True)
        self.privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.privacy.setStyleSheet(_NOTE)
        root.addWidget(self.privacy)

        self._update_buttons()

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.setBrush(QColor(18, 18, 22, 230))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        painter.end()
