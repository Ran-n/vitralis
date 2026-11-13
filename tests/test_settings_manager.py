#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:11.023352
Revised: 2026/11/13 09:11:11.361118

``settings.json`` through ``SettingsManager`` (a real file in ``tmp_path``): the update defaults, an old file
without ``"updates"``, values surviving a restart, two managers not undoing each other's changes, and a broken
file falling back to the defaults with a warning.
"""

import json
import logging

import pytest

import vitralis.settings as settings_module
from vitralis.settings import DEFAULT_SHORTCUTS, SettingsManager


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", path)
    return path


def test_the_update_defaults(settings_file):
    manager = SettingsManager()
    assert manager.update_check() is True and manager.skipped_version() == ""


def test_an_old_file_without_updates_loads_with_the_defaults(settings_file):
    settings_file.write_text(json.dumps({"language": "Deutsch", "shortcuts": {"draw": "q"}}), encoding="utf-8")
    manager = SettingsManager()
    assert manager.language() == "Deutsch" and manager.shortcuts()["draw"] == "q"
    assert manager.update_check() is True and manager.skipped_version() == ""


def test_update_values_survive_a_restart(settings_file):
    manager = SettingsManager()
    manager.set_update_check(False)
    manager.set_skipped_version("1.4.0")
    again = SettingsManager()
    assert again.update_check() is False and again.skipped_version() == "1.4.0"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["updates"] == {"check": False, "skipped": "1.4.0"}


def test_two_managers_dont_undo_each_others_changes(settings_file):
    """Regression guard: the toolbar's manager saving shortcuts used to write back its stale copy of the file,
    which would drop the updater's skipped version."""
    toolbar, updater = SettingsManager(), SettingsManager()
    updater.set_skipped_version("1.4.0")
    toolbar.set_shortcuts({**DEFAULT_SHORTCUTS, "draw": "q"})
    toolbar.set_language("Español")
    fresh = SettingsManager()
    assert fresh.skipped_version() == "1.4.0" and fresh.shortcuts()["draw"] == "q" and fresh.language() == "Español"


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"updates": "yes"}', '{"updates": {"skipped": 7}}'])
def test_a_broken_file_falls_back_to_the_defaults(settings_file, content, caplog):
    settings_file.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.WARNING, "vitralis.settings"):
        manager = SettingsManager()
    assert manager.update_check() is True and manager.skipped_version() == ""
    if content in ("{not json", "[1, 2]"):
        assert caplog.records


def test_a_failed_save_is_logged(settings_file, monkeypatch, caplog):
    def refuse(*args, **kwargs):
        raise PermissionError("read-only")

    manager = SettingsManager()
    monkeypatch.setattr(type(settings_file), "write_text", refuse)
    with caplog.at_level(logging.ERROR, "vitralis.settings"):
        manager.set_skipped_version("1.4.0")
    assert any("couldn't save" in r.getMessage() for r in caplog.records)
