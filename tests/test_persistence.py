#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:10.961213
Revised: 2026/11/14 00:23:22.278473

The drawings on disk (real files in the test's own data folder): strokes per screen surviving a restart, the
first versions' bare list, damaged entries and files, writes that are whole or not at all, failures that are
logged and never raised into the drawing, the snapshots, and the saved format pinned by a checked-in file.
"""

import json
import logging
from pathlib import Path

import pytest
from PyQt6.QtCore import QRect

import vitralis.persistence as persistence
from vitralis.models import Stroke
from vitralis.persistence import (
    DAMAGED_SUFFIX,
    SnapshotError,
    delete_snapshot,
    forget_strokes,
    list_snapshots,
    load_snapshot,
    load_strokes_for,
    save_snapshot,
    save_strokes_for,
    screen_key,
    write_json_atomic,
)

GOLDEN = Path(__file__).parent / "golden" / "strokes-v1.json"
PRIMARY = QRect(0, 0, 1920, 1080)
SECOND = QRect(1920, 0, 1280, 1024)
LINE = Stroke("LINE", "#00c853", 5, [[10.0, 20.0], [300.0, 40.5]], created=1_800_000_000.25)
PEN = Stroke("PEN", "#ff3b3b", 2, [[1.0, 2.0], [3.0, 4.0], [5.5, 6.5]], created=1_800_000_001.0)
ERASER = Stroke("ERASER", "#000000", 24, [[7.0, 8.0]], created=1_800_000_002.0)
GOLDEN_SCREENS = {PRIMARY: [LINE, PEN], SECOND: [ERASER]}


def restart() -> None:
    """What a new start of Vitralis sees: only the files."""
    forget_strokes()


def refuse(*args, **kwargs):
    raise PermissionError("read-only")


# --- strokes ------------------------------------------------------------------------------------------------


def test_no_file_means_no_strokes():
    assert load_strokes_for(PRIMARY) == []


def test_each_screens_strokes_survive_a_restart():
    assert save_strokes_for(PRIMARY, [LINE, PEN]) and save_strokes_for(SECOND, [ERASER])
    restart()
    assert load_strokes_for(PRIMARY) == [LINE, PEN] and load_strokes_for(SECOND) == [ERASER]
    assert load_strokes_for(QRect(-1280, 0, 1280, 1024)) == []


def test_saving_one_screen_keeps_the_others():
    save_strokes_for(PRIMARY, [LINE])
    save_strokes_for(SECOND, [ERASER])
    save_strokes_for(PRIMARY, [])
    restart()
    assert load_strokes_for(PRIMARY) == [] and load_strokes_for(SECOND) == [ERASER]


def test_the_file_is_read_once_and_then_kept_in_memory(monkeypatch):
    save_strokes_for(PRIMARY, [LINE])
    restart()
    reads = []
    real = persistence._read_strokes_file
    monkeypatch.setattr(persistence, "_read_strokes_file", lambda: reads.append(1) or real())
    load_strokes_for(PRIMARY)
    save_strokes_for(SECOND, [ERASER])
    load_strokes_for(SECOND)
    assert reads == [1]


def test_the_first_versions_bare_list_is_the_primary_screen_and_is_kept_on_save():
    persistence.STROKES_FILE.write_text(json.dumps([LINE.to_dict()]), encoding="utf-8")
    assert load_strokes_for(PRIMARY) == [LINE] and load_strokes_for(SECOND) == []
    save_strokes_for(SECOND, [ERASER])  # regression guard: this used to drop the primary screen's old strokes
    restart()
    assert load_strokes_for(PRIMARY) == [LINE] and load_strokes_for(SECOND) == [ERASER]


def test_a_damaged_stroke_is_skipped_and_counted_in_the_log(caplog):
    entries = [LINE.to_dict(), {"tool": "PEN", "color": "#fff", "width": "wide", "points": [[1, 2]]}, PEN.to_dict()]
    persistence.STROKES_FILE.write_text(json.dumps({"0,0": entries}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, "vitralis.persistence"):
        assert load_strokes_for(PRIMARY) == [LINE, PEN]
    assert any("skipped 1 damaged stroke" in r.getMessage() for r in caplog.records)


def test_a_screen_that_isnt_a_list_has_no_strokes_and_is_logged(caplog):
    persistence.STROKES_FILE.write_text(json.dumps({"0,0": {"oops": 1}}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, "vitralis.persistence"):
        assert load_strokes_for(PRIMARY) == []
    assert any("expected a list" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("content", ["{not json", '"just text"', "42"])
def test_an_unreadable_file_is_logged_kept_aside_and_started_over(content, caplog):
    persistence.STROKES_FILE.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        assert load_strokes_for(PRIMARY) == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    kept = persistence.STROKES_FILE.with_name(persistence.STROKES_FILE.name + DAMAGED_SUFFIX)
    assert kept.read_text(encoding="utf-8") == content
    assert save_strokes_for(PRIMARY, [LINE])
    restart()
    assert load_strokes_for(PRIMARY) == [LINE]


def test_a_failed_save_is_logged_not_raised_and_leaves_the_old_file_whole(monkeypatch, caplog):
    save_strokes_for(PRIMARY, [LINE])
    before = persistence.STROKES_FILE.read_bytes()
    monkeypatch.setattr(persistence.os, "replace", refuse)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        assert save_strokes_for(PRIMARY, [LINE, PEN]) is False
    assert any("couldn't save the drawings" in r.getMessage() for r in caplog.records)
    assert persistence.STROKES_FILE.read_bytes() == before
    assert [p.name for p in persistence.STROKES_FILE.parent.iterdir() if p.suffix == ".tmp"] == []


def test_an_atomic_write_replaces_the_file_whole(tmp_path):
    path = tmp_path / "data.json"
    write_json_atomic(path, {"a": 1})
    write_json_atomic(path, {"b": [1, 2]}, indent=None)
    assert json.loads(path.read_text(encoding="utf-8")) == {"b": [1, 2]}
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]


def test_an_atomic_write_that_fails_raises_and_leaves_nothing_behind(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    monkeypatch.setattr(persistence.os, "replace", refuse)
    with pytest.raises(PermissionError):
        write_json_atomic(path, {"a": 1})
    assert list(tmp_path.iterdir()) == []


def test_the_screen_key_is_the_top_left_corner():
    assert screen_key(SECOND) == "1920,0" and screen_key(QRect(-1280, -24, 10, 10)) == "-1280,-24"


# --- the saved format ---------------------------------------------------------------------------------------


def test_the_saved_file_is_the_golden_one():
    """A silent change of the format fails here: ``strokes.json`` outlives the version that wrote it."""
    for geo, strokes in GOLDEN_SCREENS.items():
        save_strokes_for(geo, strokes)
    saved = json.loads(persistence.STROKES_FILE.read_text(encoding="utf-8"))
    assert saved == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_the_golden_file_loads_into_a_fresh_install():
    persistence.STROKES_FILE.write_bytes(GOLDEN.read_bytes())
    for geo, strokes in GOLDEN_SCREENS.items():
        assert load_strokes_for(geo) == strokes


# --- snapshots ----------------------------------------------------------------------------------------------


def test_a_snapshot_is_listed_loaded_and_deleted():
    save_snapshot("Monday review", {"0,0": [LINE, PEN], "1920,0": [ERASER]})
    save_snapshot("alpha", {"0,0": []})
    assert list_snapshots() == ["Monday review", "alpha"]
    assert load_snapshot("Monday review") == {"0,0": [LINE, PEN], "1920,0": [ERASER]}
    delete_snapshot("Monday review")
    delete_snapshot("Monday review")  # already gone: fine
    assert list_snapshots() == ["alpha"]


def test_a_snapshot_name_cant_leave_the_snapshots_folder():
    save_snapshot("..\\..\\outside/name", {"0,0": [LINE]})
    files = sorted(p.name for p in persistence.SNAPSHOTS_DIR.iterdir())
    assert files == ["_outside_name.json"]
    assert load_snapshot("..\\..\\outside/name") == {"0,0": [LINE]}


def test_a_snapshot_skips_its_damaged_strokes():
    path = persistence.SNAPSHOTS_DIR / "old.json"
    path.write_text(json.dumps({"0,0": [LINE.to_dict(), {"tool": "?"}]}), encoding="utf-8")
    assert load_snapshot("old") == {"0,0": [LINE]}


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]"])
def test_a_missing_or_unreadable_snapshot_raises_and_is_logged(content, caplog):
    if content is not None:
        (persistence.SNAPSHOTS_DIR / "broken.json").write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR, "vitralis.persistence"), pytest.raises(SnapshotError):
        load_snapshot("broken")
    assert caplog.records


def test_a_snapshot_that_cant_be_saved_raises_and_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(persistence.os, "replace", refuse)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"), pytest.raises(SnapshotError, match="read-only"):
        save_snapshot("name", {"0,0": [LINE]})
    assert caplog.records and list_snapshots() == []


def test_a_snapshot_that_cant_be_deleted_raises_and_is_logged(monkeypatch, caplog):
    save_snapshot("name", {"0,0": [LINE]})
    monkeypatch.setattr(Path, "unlink", refuse)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"), pytest.raises(SnapshotError):
        delete_snapshot("name")
    assert caplog.records


def test_a_snapshots_folder_that_cant_be_listed_is_empty_and_logged(monkeypatch, caplog):
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", persistence.SNAPSHOTS_DIR / "gone")
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        assert list_snapshots() == []
    assert caplog.records
