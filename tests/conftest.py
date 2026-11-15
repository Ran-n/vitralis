#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/11 11:02:11.370504
Revised: 2026/11/15 22:45:12.754796

What every test shares: each runs on data and download folders of its own, with no updater override from the
shell, in English. Qt's fixtures are in ``qt_support.py`` and the licence's in ``licence_support.py``.
"""

import pytest

from vitralis.translations import set_language

pytest_plugins = ["tests.qt_support", "tests.licence_support"]


@pytest.fixture(autouse=True)
def own_data_folder(monkeypatch, tmp_path_factory):
    """Every test gets a data folder of its own: none may read or write the real ``%APPDATA%\\Vitralis``."""
    import vitralis.persistence as persistence
    import vitralis.settings as settings

    data = tmp_path_factory.mktemp("vitralis-data")  # not in tmp_path, which tests expect to start empty
    (data / "snapshots").mkdir()
    monkeypatch.setattr(persistence, "STROKES_FILE", data / "strokes.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", data / "snapshots")
    monkeypatch.setattr(settings, "SETTINGS_FILE", data / "settings.json")
    persistence.forget_strokes()
    yield data
    persistence.forget_strokes()  # waits for what the test left on its way to the disk, too


@pytest.fixture(autouse=True)
def no_update_overrides(monkeypatch, tmp_path_factory):
    """No updater override from the shell running the tests, and downloads in a folder of the test's own:
    none may land in the real ``%LOCALAPPDATA%\\Vitralis``."""
    from vitralis.updates.target import OVERRIDES, release_target

    for name in OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("local-app-data")))
    release_target.cache_clear()
    yield
    release_target.cache_clear()


@pytest.fixture(autouse=True)
def english(monkeypatch):
    """English, and no installer language: an installed Vitralis on the test machine changes nothing."""
    monkeypatch.setattr("vitralis.settings.installer_language", lambda: None)
    set_language("English")
    yield
    set_language("English")
