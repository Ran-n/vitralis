#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 09:11:11.023352
Revised: 2026/11/14 00:23:19.956753

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


# --- damaged values -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("saved", [["d"], "d", 7, None])
def test_shortcuts_that_arent_a_table_fall_back_to_the_defaults(settings_file, saved, caplog):
    """Regression guard: a list here used to raise when the toolbar asked for its shortcuts."""
    settings_file.write_text(json.dumps({"shortcuts": saved}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, "vitralis.settings"):
        assert SettingsManager().shortcuts() == DEFAULT_SHORTCUTS
    assert caplog.records


def test_unknown_actions_and_keys_that_arent_text_are_ignored(settings_file):
    saved = {"draw": "q", "pan": 5, "fly": "f", "undo": ""}
    settings_file.write_text(json.dumps({"shortcuts": saved}), encoding="utf-8")
    assert SettingsManager().shortcuts() == {**DEFAULT_SHORTCUTS, "draw": "q", "undo": ""}


@pytest.mark.parametrize("saved", ["Klingon", 7, ["Galego"]])
def test_a_saved_language_vitralis_doesnt_have_falls_back(settings_file, saved, caplog):
    settings_file.write_text(json.dumps({"language": saved}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, "vitralis.settings"):
        assert SettingsManager(lambda: None).language() == "English"
        assert SettingsManager(lambda: "Galego").language() == "Galego"
    assert caplog.records


def test_a_save_leaves_no_temporary_file(settings_file):
    SettingsManager().set_language("Deutsch")
    assert [p.name for p in settings_file.parent.iterdir() if p.suffix == ".tmp"] == []


# --- the toolbar's state ------------------------------------------------------------------------------------


def test_no_toolbar_state_until_one_is_saved(settings_file):
    assert SettingsManager().toolbar_state() == {}


def test_the_toolbar_state_survives_a_restart_part_by_part(settings_file):
    manager = SettingsManager()
    manager.set_toolbar_state(tool="ARROW", color="#12AB34")
    manager.set_toolbar_state(size=9, position=[40, -60])
    assert SettingsManager().toolbar_state() == {"tool": "ARROW", "color": "#12ab34", "size": 9, "position": [40, -60]}


def test_saving_the_same_toolbar_state_writes_nothing(settings_file, monkeypatch):
    manager = SettingsManager()
    manager.set_toolbar_state(tool="LINE")
    writes = []
    monkeypatch.setattr(settings_module, "write_json_atomic", lambda *a, **k: writes.append(a))
    manager.set_toolbar_state(tool="LINE")
    assert writes == []
    manager.set_toolbar_state(tool="PEN")
    assert len(writes) == 1


@pytest.mark.parametrize(
    "saved",
    [
        "PEN",
        {"tool": "LASER", "color": "red", "size": 0, "position": [1]},
        {"tool": 3, "color": 255, "size": "5", "position": "1,2"},
        {"size": True, "position": [1.5, 2]},
        {"size": 5000, "position": [True, False]},
    ],
)
def test_damaged_toolbar_state_is_left_out(settings_file, saved):
    settings_file.write_text(json.dumps({"toolbar": saved}), encoding="utf-8")
    assert SettingsManager().toolbar_state() == {}


def test_a_damaged_toolbar_entry_is_replaced_on_the_next_save(settings_file):
    settings_file.write_text(json.dumps({"toolbar": "PEN", "language": "Deutsch"}), encoding="utf-8")
    manager = SettingsManager()
    manager.set_toolbar_state(size=7)
    assert SettingsManager().toolbar_state() == {"size": 7} and SettingsManager().language() == "Deutsch"
