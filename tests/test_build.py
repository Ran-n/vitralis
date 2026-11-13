#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 19:56:04.526845
Revised: 2026/11/13 19:56:11.641168

``uv run build``'s installer step: finding Inno Setup, the command it runs, the installer's name (never taken
for the exe the updater swaps in), and a real compile of ``installer/vitralis.iss`` around a stand-in exe.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from vitralis import build
from vitralis.updates.registration import INSTALLER_GUID
from vitralis.updates.rules import exe_name, exe_version, parse_version

ROOT = Path(__file__).resolve().parent.parent


def fake_iscc(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "ISCC.exe").write_bytes(b"")
    return folder / "ISCC.exe"


def test_iscc_variable_wins(tmp_path, monkeypatch):
    given = fake_iscc(tmp_path / "custom")
    monkeypatch.setattr(build.shutil, "which", lambda name: "C:/elsewhere/ISCC.exe")
    assert build.find_iscc({"ISCC": str(given)}) == given


def test_an_iscc_variable_naming_no_file_finds_nothing(tmp_path):
    assert build.find_iscc({"ISCC": str(tmp_path / "missing.exe")}) is None


def test_path_comes_before_the_install_folders(tmp_path, monkeypatch):
    fake_iscc(tmp_path / "Programs" / "Inno Setup 6")
    monkeypatch.setattr(build.shutil, "which", lambda name: "C:/on/path/ISCC.exe")
    assert build.find_iscc({"LOCALAPPDATA": str(tmp_path)}) == Path("C:/on/path/ISCC.exe")


@pytest.mark.parametrize(
    ("variable", "sub"),
    [("LOCALAPPDATA", ("Programs", "Inno Setup 6")), ("ProgramFiles(x86)", ("Inno Setup 6",))],
)
def test_the_usual_install_folders_are_searched(tmp_path, monkeypatch, variable, sub):
    found = fake_iscc(tmp_path.joinpath(*sub))
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    assert build.find_iscc({variable: str(tmp_path)}) == found


def test_nothing_found_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    assert build.find_iscc({"LOCALAPPDATA": str(tmp_path)}) is None


def test_the_installer_is_never_taken_for_the_update_exe():
    name = build.installer_name("1.4.0")
    assert name == "vitralis-1.4.0-setup.exe"
    assert exe_version(name) is None and name != exe_name(parse_version("1.4.0"))


def test_the_command_passes_everything_the_script_needs(tmp_path):
    command = build.iscc_command(
        Path("ISCC.exe"), Path("vitralis.iss"), "1.4.0", Path("v.exe"), Path("v.ico"), Path("LICENSE"), tmp_path
    )
    assert command[0] == "ISCC.exe" and command[-1] == "vitralis.iss"
    assert {
        "/DAppVersion=1.4.0",
        f"/DAppGuid={INSTALLER_GUID}",
        "/DSourceExe=v.exe",
        "/DIconFile=v.ico",
        "/DLicenseFile=LICENSE",
        f"/DOutputDir={tmp_path}",
    } <= set(command)


def test_no_installer_flag():
    assert build.parse_arguments(["--no-installer"]).no_installer
    assert not build.parse_arguments([]).no_installer


def test_a_missing_inno_setup_stops_the_build_with_the_hint(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(build, "find_iscc", lambda: None)
    with pytest.raises(SystemExit) as raised:
        build.build_installer(tmp_path, "1.4.0", tmp_path / "v.exe", tmp_path / "v.ico", tmp_path)
    assert raised.value.code == 1 and "--no-installer" in capsys.readouterr().out


def test_a_failed_compile_stops_the_build(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "find_iscc", lambda: Path("ISCC.exe"))
    monkeypatch.setattr(build.subprocess, "run", lambda command: subprocess.CompletedProcess(command, 2))
    with pytest.raises(SystemExit) as raised:
        build.build_installer(tmp_path, "1.4.0", tmp_path / "v.exe", tmp_path / "v.ico", tmp_path)
    assert raised.value.code == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Inno Setup runs on Windows")
def test_the_script_compiles_into_a_versioned_installer(tmp_path, qapp):
    if build.find_iscc() is None:
        pytest.fail(f"Inno Setup's ISCC.exe wasn't found: {build.ISCC_HINT}")
    exe = tmp_path / "vitralis-9.8.7.exe"
    exe.write_bytes(b"MZ stand-in exe")
    ico = tmp_path / "vitralis.ico"
    build.png_to_ico(str(ROOT / "src" / "vitralis" / "media" / "logo" / "icon.png"), str(ico))
    out = tmp_path / "dist"
    setup = build.build_installer(ROOT, "9.8.7", exe, ico, out)
    assert setup == out / "vitralis-9.8.7-setup.exe"
    assert setup.is_file() and setup.read_bytes()[:2] == b"MZ"
