#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 21:39:56.674110
Revised: 2026/11/15 21:40:17.881391

The rendered tests' guard against personal data on screen (``personal.py``): it finds the user's names as
whole words or path components, at any depth and in keys too, but not inside longer words; its scratch folder
sits under ``%PUBLIC%`` and refuses a path that names the user; and the folder is deleted afterwards. These
run in the default run: the guard must work before any picture is taken.
"""

import os
from pathlib import Path

import pytest

from tests.rendered import personal
from tests.rendered.personal import PersonalData, find_personal, refuse_personal, remove_scratch, scratch_folder

NAMES = ("ana",)


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\ana\AppData\Local\Temp\x",
        "C:/Users/ANA/x",
        "signed in as ana",
        {"deep": [{"list": ["ok", "ana"]}]},
        {"ana": 1},
        "ana.txt",
    ],
)
def test_a_name_as_a_word_or_path_part_is_found(value):
    assert find_personal(value, NAMES)


@pytest.mark.parametrize("value", ["banana", "anagram", "dian-ana-x", "", None, 3, {"k": ["banana"]}, "ana_b"])
def test_a_name_inside_a_longer_word_is_not(value):
    assert not find_personal(value, NAMES)


def test_the_finding_says_where(monkeypatch):
    monkeypatch.setattr(personal, "personal_names", lambda: NAMES)
    with pytest.raises(PersonalData) as raised:
        refuse_personal({"panels": ["x", r"C:\Users\ana"]})
    assert "state.panels[1]:" in str(raised.value) and "state.panels[0]" not in str(raised.value)


def test_the_names_are_the_account_and_the_profile_folder(monkeypatch):
    monkeypatch.setenv("USERNAME", "ana")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\ana.work")
    assert personal.personal_names() == ("ana", "ana.work")


def test_no_names_means_nothing_found(monkeypatch):
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert personal.personal_names() == () and find_personal("anything") == []


def test_the_scratch_folder_is_under_public_and_is_deleted_after(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC", str(tmp_path / "Public"))
    monkeypatch.setattr(personal, "personal_names", lambda: NAMES)
    folder = scratch_folder()
    assert folder.parent == tmp_path / "Public" / "vitralis-tests" and folder.is_dir()
    (folder / "driver.log").write_text("x", encoding="utf-8")
    remove_scratch(folder)
    assert not (tmp_path / "Public" / "vitralis-tests").exists()


def test_a_scratch_folder_whose_path_names_the_user_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC", str(tmp_path / "ana"))
    monkeypatch.setattr(personal, "personal_names", lambda: NAMES)
    with pytest.raises(PersonalData):
        scratch_folder()
    assert not any((tmp_path / "ana" / "vitralis-tests").iterdir())  # nothing left behind


def test_without_public_there_is_no_scratch_folder(monkeypatch):
    monkeypatch.delenv("PUBLIC", raising=False)
    with pytest.raises(PersonalData, match="PUBLIC"):
        scratch_folder()


def test_the_real_scratch_folder_names_nobody():
    if not os.environ.get("PUBLIC"):
        pytest.skip("Windows only: %PUBLIC% is the shared profile")
    folder = scratch_folder()
    try:
        assert not find_personal(str(folder)) and Path(os.environ["PUBLIC"]) in folder.parents
    finally:
        remove_scratch(folder)
