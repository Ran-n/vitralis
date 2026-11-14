#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:10.961213
Revised: 2026/11/14 17:53:31.508633

The drawings on disk (real files in the test's own data folder): strokes per screen surviving a restart, the
first versions' bare list, damaged entries and files, writes that are whole or not at all and never make the
caller wait for the disk, failures that are logged and never raised into the drawing, the snapshots, and the
saved format pinned by a checked-in file.
"""

import json
import logging
import threading
from pathlib import Path

import pytest
from PyQt6.QtCore import QRect

import vitralis.persistence as persistence
from vitralis.models import Stroke
from vitralis.persistence import (
    DAMAGED_SUFFIX,
    BackgroundWriter,
    SnapshotError,
    delete_snapshot,
    flush_writes,
    forget_strokes,
    list_snapshots,
    load_snapshot,
    load_strokes_for,
    save_snapshot,
    save_strokes_for,
    screen_key,
    write_json_atomic,
)

GOLDEN = Path(__file__).parent / "golden" / "strokes-v2.json"
GOLDEN_BEFORE = Path(__file__).parent / "golden" / "strokes-v1.json"
"""As written up to 1.3.0: every stroke carried a ``filled`` that no tool ever set."""
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


def hold(monkeypatch, path: Path) -> dict:
    """Make ``path`` unreadable, as while another program holds it, until the ``held`` it returns is turned
    off."""
    state = {"held": True}
    read = type(path).read_bytes

    def read_bytes(self):
        if state["held"] and self == path:
            raise PermissionError("held by another program")
        return read(self)

    monkeypatch.setattr(type(path), "read_bytes", read_bytes)
    return state


# --- strokes ------------------------------------------------------------------------------------------------


def test_no_file_means_no_strokes():
    assert load_strokes_for(PRIMARY) == []


def test_each_screens_strokes_survive_a_restart():
    save_strokes_for(PRIMARY, [LINE, PEN])
    save_strokes_for(SECOND, [ERASER])
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
    save_strokes_for(PRIMARY, [LINE])
    restart()
    assert load_strokes_for(PRIMARY) == [LINE]


def test_a_file_that_cant_be_read_is_never_written_over(monkeypatch, caplog):
    """Regression guard: a file held by another program at start counted as empty, and the first stroke drawn
    replaced every screen's drawings in it."""
    save_strokes_for(PRIMARY, [LINE])
    save_strokes_for(SECOND, [PEN])
    restart()
    before = persistence.STROKES_FILE.read_bytes()
    state = hold(monkeypatch, persistence.STROKES_FILE)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        assert load_strokes_for(PRIMARY) == []  # the app starts without drawings
        save_strokes_for(PRIMARY, [ERASER])
        assert flush_writes(5)
    state["held"] = False  # for the test's own look at the file
    assert persistence.STROKES_FILE.read_bytes() == before
    messages = [r.getMessage() for r in caplog.records]
    assert any("leaving the file as it is" in m for m in messages) and any("not saving" in m for m in messages)
    kept = persistence.STROKES_FILE.with_name(persistence.STROKES_FILE.name + DAMAGED_SUFFIX)
    assert not kept.exists()  # nothing is damaged: there is nothing to keep aside


def test_once_the_file_can_be_read_again_a_save_keeps_the_other_screens_and_a_copy(monkeypatch):
    save_strokes_for(PRIMARY, [LINE])
    save_strokes_for(SECOND, [PEN])
    restart()
    before = persistence.STROKES_FILE.read_bytes()
    state = hold(monkeypatch, persistence.STROKES_FILE)
    assert load_strokes_for(PRIMARY) == []
    state["held"] = False
    save_strokes_for(PRIMARY, [ERASER])
    restart()
    assert load_strokes_for(PRIMARY) == [ERASER]  # what was drawn since
    assert load_strokes_for(SECOND) == [PEN]  # the screen not drawn on keeps its drawings
    kept = persistence.STROKES_FILE.with_name(persistence.STROKES_FILE.name + DAMAGED_SUFFIX)
    assert kept.read_bytes() == before  # the first screen's earlier drawings can still be got back


def test_a_restart_forgets_that_the_file_couldnt_be_read(monkeypatch):
    save_strokes_for(PRIMARY, [LINE])
    restart()
    state = hold(monkeypatch, persistence.STROKES_FILE)
    assert load_strokes_for(PRIMARY) == []
    state["held"] = False
    restart()
    assert load_strokes_for(PRIMARY) == [LINE]
    save_strokes_for(PRIMARY, [LINE, PEN])
    restart()
    assert load_strokes_for(PRIMARY) == [LINE, PEN]


def test_a_failed_save_is_logged_not_raised_and_leaves_the_old_file_whole(monkeypatch, caplog):
    save_strokes_for(PRIMARY, [LINE])
    assert flush_writes(5)
    before = persistence.STROKES_FILE.read_bytes()
    monkeypatch.setattr(persistence.os, "replace", refuse)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        save_strokes_for(PRIMARY, [LINE, PEN])
        assert flush_writes(5)
    assert any("couldn't save" in r.getMessage() and "strokes.json" in r.getMessage() for r in caplog.records)
    assert persistence.STROKES_FILE.read_bytes() == before
    assert load_strokes_for(PRIMARY) == [LINE, PEN]  # still drawn, and saved by the next save that works
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


# --- writing off the calling thread -------------------------------------------------------------------------


class SlowDisk:
    """Stands in for ``write_json_atomic``: holds every write until ``release`` is set, and records them."""

    def __init__(self, monkeypatch) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.written: list[tuple[str, object]] = []
        self.threads: set[str] = set()
        monkeypatch.setattr(persistence, "write_json_atomic", self.write)

    def write(self, path, data, indent=2) -> None:
        self.started.set()
        self.threads.add(threading.current_thread().name)
        assert self.release.wait(5)
        self.written.append((path.name, data))


def test_a_save_doesnt_wait_for_the_disk(monkeypatch):
    disk = SlowDisk(monkeypatch)
    save_strokes_for(PRIMARY, [LINE])  # returns although the disk hasn't taken a byte yet
    assert disk.started.wait(5) and disk.written == []
    assert not flush_writes(0.05)  # still writing
    disk.release.set()
    assert flush_writes(5)
    assert [name for name, _ in disk.written] == ["strokes.json"]
    assert disk.threads == {"vitralis-writer"}


def test_of_several_saves_waiting_only_the_latest_is_written(tmp_path, monkeypatch):
    disk = SlowDisk(monkeypatch)
    writer = BackgroundWriter()
    writer.write(tmp_path / "a.json", 1)
    assert disk.started.wait(5)  # a.json is being written; the rest waits
    for version in (2, 3, 4):
        writer.write(tmp_path / "a.json", version)
    writer.write(tmp_path / "b.json", "b")
    disk.release.set()
    assert writer.flush(5)
    assert disk.written == [("a.json", 1), ("a.json", 4), ("b.json", "b")]


def test_a_write_that_fails_is_logged_and_the_next_file_is_still_written(tmp_path, caplog):
    writer = BackgroundWriter()
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        (tmp_path / "taken").write_text("a file where a.json's folder should be", encoding="utf-8")
        writer.write(tmp_path / "taken" / "a.json", {"a": 1})
        writer.write(tmp_path / "bad.json", {"when": object()})  # not JSON: a bug, logged with its traceback
        writer.write(tmp_path / "b.json", {"b": 2})
        assert writer.flush(5)
    assert json.loads((tmp_path / "b.json").read_text(encoding="utf-8")) == {"b": 2}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.json", "taken"]
    assert sum("a.json" in r.getMessage() for r in caplog.records) == 1
    assert any("bad.json" in r.getMessage() and r.exc_info for r in caplog.records)


def test_the_writer_starts_again_after_it_ran_dry(tmp_path):
    writer = BackgroundWriter()
    assert writer.flush(0)  # nothing waiting: nothing to wait for
    for version in (1, 2):
        writer.write(tmp_path / "a.json", version)
        assert writer.flush(5)
        assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == version


def test_what_was_saved_is_what_is_written_whatever_is_drawn_meanwhile(monkeypatch):
    """The canvas goes on changing its list of strokes while the writer still holds the last save."""
    disk = SlowDisk(monkeypatch)
    drawn = [LINE]
    save_strokes_for(PRIMARY, drawn)
    assert disk.started.wait(5)
    drawn.append(PEN)
    disk.release.set()
    assert flush_writes(5)
    assert disk.written[0][1] == {"0,0": [LINE.to_dict()]}


def test_the_screen_key_is_the_top_left_corner():
    assert screen_key(SECOND) == "1920,0" and screen_key(QRect(-1280, -24, 10, 10)) == "-1280,-24"


# --- the saved format ---------------------------------------------------------------------------------------


def test_the_saved_file_is_the_golden_one():
    """A silent change of the format fails here: ``strokes.json`` outlives the version that wrote it."""
    for geo, strokes in GOLDEN_SCREENS.items():
        save_strokes_for(geo, strokes)
    assert flush_writes(5)
    saved = json.loads(persistence.STROKES_FILE.read_text(encoding="utf-8"))
    assert saved == json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("golden", [GOLDEN, GOLDEN_BEFORE], ids=["current", "up to 1.3.0"])
def test_the_golden_file_loads_into_a_fresh_install(golden):
    persistence.STROKES_FILE.write_bytes(golden.read_bytes())
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


@pytest.mark.parametrize("name", ["CON", "nul", "Com1", "LPT9", "aux"])
def test_a_snapshot_named_like_a_windows_device_is_still_saved(name):
    """Regression guard: Windows makes no file called ``CON.json``, so such a name could never be saved."""
    save_snapshot(name, {"0,0": [LINE]})
    assert list_snapshots() == [f"_{name}"]
    assert load_snapshot(name) == {"0,0": [LINE]} == load_snapshot(f"_{name}")
    delete_snapshot(name)
    assert list_snapshots() == []


def test_a_name_that_only_starts_like_a_device_is_kept_as_typed():
    save_snapshot("console", {"0,0": []})
    save_snapshot("COM10", {"0,0": []})
    assert list_snapshots() == ["COM10", "console"]


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
    def refuse_listing(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", refuse_listing)
    with caplog.at_level(logging.ERROR, "vitralis.persistence"):
        assert list_snapshots() == []
    assert caplog.records


def test_before_any_snapshot_was_saved_there_are_none_and_nothing_to_log(monkeypatch, caplog):
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", persistence.SNAPSHOTS_DIR / "not-made-yet")
    with caplog.at_level(logging.DEBUG, "vitralis.persistence"):
        assert list_snapshots() == []
    assert caplog.records == []


def test_the_data_folder_is_made_by_the_first_write_not_by_importing(tmp_path, monkeypatch):
    """Regression guard: importing the module made ``%APPDATA%\\Vitralis`` and its ``snapshots`` folder, on
    the machine of whoever only ran the tests."""
    import ast

    for node in ast.parse(Path(persistence.__file__).read_text(encoding="utf-8")).body:  # nothing runs at import
        assert not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)), ast.unparse(node)
    fresh = tmp_path / "Vitralis"
    monkeypatch.setattr(persistence, "STROKES_FILE", fresh / "strokes.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", fresh / "snapshots")
    assert load_strokes_for(PRIMARY) == [] and list_snapshots() == [] and not fresh.exists()
    save_strokes_for(PRIMARY, [LINE])
    save_snapshot("first", {"0,0": [LINE]})
    assert flush_writes(5)
    assert sorted(p.name for p in fresh.iterdir()) == ["snapshots", "strokes.json"]
    assert list_snapshots() == ["first"]
