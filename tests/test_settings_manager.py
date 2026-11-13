#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:11.023352
Revised: 2026/11/13 20:11:36.979973

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


def test_without_a_language_it_starts_in_english(settings_file):
    assert SettingsManager(lambda: None).language() == "English"


@pytest.mark.parametrize("language", ["Galego", "Galego reintegrado", "日本語"])
def test_the_installers_language_is_the_first_one(settings_file, language):
    """Installed in Galician, Vitralis starts in Galician; nothing is written until one is picked."""
    assert SettingsManager(lambda: language).language() == language
    assert not settings_file.exists()


def test_a_language_picked_in_settings_beats_the_installers(settings_file):
    SettingsManager(lambda: "Galego").set_language("Deutsch")
    assert SettingsManager(lambda: "Galego").language() == "Deutsch"


def test_a_file_without_a_language_still_takes_the_installers(settings_file):
    settings_file.write_text(json.dumps({"shortcuts": {"draw": "q"}}), encoding="utf-8")
    assert SettingsManager(lambda: "Français").language() == "Français"


def test_an_unknown_installer_language_is_logged_and_english(settings_file, caplog):
    with caplog.at_level(logging.WARNING, "vitralis.settings"):
        assert SettingsManager(lambda: "Klingon").language() == "English"
    assert any("Klingon" in r.getMessage() for r in caplog.records)


def test_the_default_source_is_the_registry(settings_file, monkeypatch):
    monkeypatch.setattr(settings_module, "installer_language", lambda: "Español")
    assert SettingsManager().language() == "Español"
