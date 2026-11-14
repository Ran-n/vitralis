#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 12:31:22.614829
Revised: 2026/11/14 12:31:22.614829

The Snapshots window: the drawings of every screen saved under a name, listed, loaded back and deleted. The
disk is never waited for on the UI thread: the buttons are greyed out until it answers, and a failure is said in
the window.
"""

import logging

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout

from vitralis.background import BackgroundTasks
from vitralis.icons import svg_icon
from vitralis.persistence import (
    SnapshotError,
    delete_snapshot,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    save_strokes_for,
    screen_key,
)
from vitralis.styles import danger_btn, muted_btn
from vitralis.translations import t
from vitralis.widgets import LineEdit, Panel

logger = logging.getLogger("vitralis.snapshots")

SNAPSHOT_SAVE_FAILED = "The snapshot couldn't be saved. Try another name."
SNAPSHOT_LOAD_FAILED = "The snapshot couldn't be loaded: its file is damaged or gone."
SNAPSHOT_DELETE_FAILED = "The snapshot couldn't be deleted."


class _SnapshotList(QListWidget):
    """The list of snapshots, with Enter to load the selected one and Delete to delete the selected ones.

    The keys are the list's own while it has the focus (it claims them before the shortcuts are looked at):
    as window-wide shortcuts, Enter in the name field loaded instead of saving, and Delete clashed with the
    toolbar's Clear all, so that neither ran."""

    load_asked = pyqtSignal()
    delete_asked = pyqtSignal()
    _OWN_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Delete)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and (
            event.key() in self._OWN_KEYS or event.matches(QKeySequence.StandardKey.SelectAll)
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.load_asked.emit()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_asked.emit()
        else:
            super().keyPressEvent(event)  # Ctrl+A, the arrows, typing to find


class SnapshotWindow(Panel):
    _LIST_STYLE = (
        "QListWidget { background: rgba(255,255,255,8); border: 1px solid rgba(255,255,255,18);"
        "border-radius: 6px; color: #f0f0f0; font-size: 12px; padding: 2px; }"
        "QListWidget::item { padding: 5px 8px; border-radius: 4px; }"
        "QListWidget::item:selected { background: #e07020; color: white; }"
        "QListWidget::item:hover { background: rgba(255,255,255,15); }"
    )
    _INPUT_STYLE = (
        "QLineEdit { background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,25);"
        "border-radius: 6px; color: #f0f0f0; font-size: 12px; padding: 5px 8px; }"
        "QLineEdit:focus { border-color: rgba(255,255,255,60); }"
    )
    _ERROR_STYLE = "color: #ff8a65; font-size: 11px; background: transparent;"

    def __init__(self, canvases: list, parent=None) -> None:
        super().__init__(f"Vitralis — {t('Snapshots')}", parent)
        self.canvases = canvases
        self._all_names: list[str] = []
        self._error_key = ""
        self._tasks = BackgroundTasks(self)
        """The snapshots are listed, saved, read and deleted off the UI thread; the buttons wait meanwhile."""
        self._build_ui()
        self._tasks.busy_changed.connect(self._update_buttons)
        self._refresh_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(8)

        # title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_lbl = QLabel(t("Snapshots"))
        title_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        self._title_lbl = title_lbl
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(danger_btn())
        close_btn.clicked.connect(self.close)
        title_row.addWidget(title_lbl, stretch=1)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # search / name input
        self._name_edit = LineEdit()
        self._name_edit.setPlaceholderText(t("Snapshot name…"))
        self._name_edit.setClearButtonEnabled(True)
        self._name_edit.setStyleSheet(self._INPUT_STYLE)
        self._name_edit.textChanged.connect(self._on_filter)
        self._name_edit.returnPressed.connect(self._save)
        root.addWidget(self._name_edit)

        # list
        self._list = _SnapshotList()
        self._list.setMinimumHeight(130)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setStyleSheet(self._LIST_STYLE)
        self._list.load_asked.connect(self._load)
        self._list.delete_asked.connect(self._delete)
        root.addWidget(self._list)

        # action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._save_btn = QPushButton(svg_icon("save", 15), "  " + t("Save"))
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(muted_btn())
        self._save_btn.clicked.connect(self._save)

        self._load_btn = QPushButton(svg_icon("load", 15), "  " + t("Load"))
        self._load_btn.setFixedHeight(30)
        self._load_btn.setStyleSheet(muted_btn())
        self._load_btn.clicked.connect(self._load)

        self._del_btn = QPushButton(svg_icon("trash", 15), "  " + t("Delete"))
        self._del_btn.setFixedHeight(30)
        self._del_btn.setStyleSheet(muted_btn())
        self._del_btn.clicked.connect(self._delete)

        for b in (self._save_btn, self._load_btn, self._del_btn):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        self._error_lbl = QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(self._ERROR_STYLE)
        self._error_lbl.hide()
        root.addWidget(self._error_lbl)

        self._list.itemSelectionChanged.connect(self._update_buttons)
        self._name_edit.textChanged.connect(self._update_buttons)
        self._update_buttons()

    @property
    def busy(self) -> bool:
        """Whether the disk is still being read or written for this window."""
        return self._tasks.busy

    def _update_buttons(self, *_) -> None:
        n = len(self._list.selectedItems())
        has_name = bool(self._name_edit.text().strip())
        idle = not self.busy
        self._save_btn.setEnabled(idle and (has_name or n == 1) and n <= 1)
        self._load_btn.setEnabled(idle and n == 1)
        self._del_btn.setEnabled(idle and n >= 1)

    def _refresh_list(self, keep_filter: bool = False) -> None:
        def listed(names: list[str] | None, error: Exception | None) -> None:
            if error is not None:  # list_snapshots logs and returns nothing when the folder can't be read
                logger.error("couldn't list the snapshots: %s", error)
            self._all_names = names or []
            self._apply_filter(self._name_edit.text().strip().lower() if keep_filter else "")

        self._tasks.run("snapshots-list", lambda: list_snapshots(), listed)

    def _on_filter(self, text: str) -> None:
        self._apply_filter(text.strip().lower())

    def _apply_filter(self, query: str) -> None:
        selected = {item.text() for item in self._list.selectedItems()}
        self._list.clear()
        for name in self._all_names:
            if not query or query in name.lower():
                self._list.addItem(name)
        for i in range(self._list.count()):
            if self._list.item(i).text() in selected:
                self._list.item(i).setSelected(True)

    def _show_error(self, key: str) -> None:
        """Say what went wrong (``key`` is the English sentence), or clear the line with ``""``."""
        self._error_key = key
        self._error_lbl.setText(t(key) if key else "")
        self._error_lbl.setVisible(bool(key))
        self.adjustSize()

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            items = self._list.selectedItems()
            if len(items) == 1:
                name = items[0].text()
        if not name or self.busy:
            return
        # each list copied: the canvases go on drawing into theirs while the snapshot is written
        screens = {screen_key(c.screen_geometry): list(c.strokes) for c in self.canvases}

        def saved(_result: None, error: Exception | None) -> None:
            if error is not None:
                self._fail(SNAPSHOT_SAVE_FAILED, error)
                return
            self._show_error("")
            self._name_edit.clear()
            self._refresh_list()

        self._tasks.run("snapshot-save", lambda: save_snapshot(name, screens), saved)

    def _load(self) -> None:
        items = self._list.selectedItems()
        if len(items) != 1 or self.busy:
            return
        name = items[0].text()

        def loaded(data: dict[str, list] | None, error: Exception | None) -> None:
            if error is not None:
                self._fail(SNAPSHOT_LOAD_FAILED, error)
                self._refresh_list(keep_filter=True)
                return
            self._show_error("")
            for canvas in self.canvases:
                key = screen_key(canvas.screen_geometry)
                if key in data:
                    canvas.load(data[key])
                    save_strokes_for(canvas.screen_geometry, canvas.strokes)

        self._tasks.run("snapshot-load", lambda: load_snapshot(name), loaded)

    def _delete(self) -> None:
        names = [item.text() for item in self._list.selectedItems()]
        if not names or self.busy:
            return

        def delete_all() -> int:
            """How many couldn't be deleted (each is logged where it fails); one failing doesn't stop the rest."""
            failed = 0
            for name in names:
                try:
                    delete_snapshot(name)
                except SnapshotError:
                    failed += 1
            return failed

        def deleted(failed: int | None, error: Exception | None) -> None:
            if error is not None:
                self._fail(SNAPSHOT_DELETE_FAILED, error)
            else:
                self._show_error(SNAPSHOT_DELETE_FAILED if failed else "")
            self._refresh_list(keep_filter=True)

        self._tasks.run("snapshot-delete", delete_all, deleted)

    def _fail(self, key: str, error: Exception) -> None:
        """Say ``key`` in the window; an error the snapshots' own code didn't expect (and so didn't log) is
        logged here."""
        if not isinstance(error, SnapshotError):
            logger.error("snapshot work failed unexpectedly", exc_info=error)
        self._show_error(key)

    def retranslate(self) -> None:
        self._title_lbl.setText(t("Snapshots"))
        self.setWindowTitle(f"Vitralis — {t('Snapshots')}")
        self._error_lbl.setText(t(self._error_key) if self._error_key else "")
        self._name_edit.setPlaceholderText(t("Snapshot name…"))
        self._save_btn.setText("  " + t("Save"))
        self._load_btn.setText("  " + t("Load"))
        self._del_btn.setText("  " + t("Delete"))
