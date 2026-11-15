#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/13 19:56:04.526845
Revised: 2026/11/15 21:40:14.131007

``uv run build`` and the installer: the release target the exe is built with (a value that isn't a target
stops the build), the files the packaged exe reads, the installer script's command line, a real compile of
``packaging/windows/vitralis.iss`` around a stand-in exe through ``build-installer.ps1``, and what the
script declares (per-user folder, publisher, application id, languages, the running-copy check).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from vitralis import build
from vitralis.installed import INSTALLER_GUID
from vitralis.settings import LANGUAGES
from vitralis.updates.target import asset_name, installer_name

ROOT = Path(__file__).resolve().parent.parent
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Inno Setup and PowerShell run on Windows")
MACHINE_ENV = dict(os.environ)
"""As the shell gave it, before a fixture moves ``LOCALAPPDATA``: Inno Setup may be installed per user there."""


def test_without_a_release_target_the_build_is_a_build_from_source():
    assert build.release_target({}) is None


def test_a_release_target_is_taken_when_it_is_one():
    assert build.release_target({"VITRALIS_RELEASE_TARGET": "windows-x86_64"}) == "windows-x86_64"


def test_a_release_target_that_isnt_one_stops_the_build(capsys):
    with pytest.raises(SystemExit) as raised:
        build.release_target({"VITRALIS_RELEASE_TARGET": "windows-arm64"})
    assert raised.value.code == 2 and "isn't a target" in capsys.readouterr().out


def test_the_build_writes_the_version_and_the_target_the_packaged_exe_reads(tmp_path):
    build.write_build_info(tmp_path, "1.4.0", "windows-x86_64")
    assert (tmp_path / "_version.py").read_text(encoding="utf-8") == '__version__ = "1.4.0"\n'
    namespace: dict = {}
    exec((tmp_path / "_release.py").read_text(encoding="utf-8"), namespace)
    assert namespace["TARGET"] == "windows-x86_64"
    build.write_build_info(tmp_path, "1.4.0", None)
    namespace = {}
    exec((tmp_path / "_release.py").read_text(encoding="utf-8"), namespace)
    assert namespace["TARGET"] is None


def test_the_exe_and_the_installer_never_share_a_name():
    assert asset_name("1.4.0", build.TARGET) == "vitralis-1.4.0-windows-x86_64.exe"
    assert installer_name("1.4.0", build.TARGET) == "vitralis-1.4.0-windows-x86_64-setup.exe"


def test_the_installer_command_runs_the_script_with_the_exe_the_icon_and_the_folder(tmp_path):
    command = build.installer_command(ROOT, Path("v.exe"), Path("v.ico"), tmp_path)
    assert command[:5] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert command[5] == str(ROOT / "packaging" / "windows" / "build-installer.ps1")
    assert command[6:] == ["-Binary", "v.exe", "-OutputDirectory", str(tmp_path), "-Icon", "v.ico"]


def test_no_installer_flag():
    assert build.parse_arguments(["--no-installer"]).no_installer
    assert not build.parse_arguments([]).no_installer


def test_a_failed_installer_build_stops_the_build(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(build.subprocess, "run", lambda command: subprocess.CompletedProcess(command, 3))
    with pytest.raises(SystemExit) as raised:
        build.build_installer(tmp_path, tmp_path / "v.exe", tmp_path / "v.ico", tmp_path)
    assert raised.value.code == 3 and "Installer build failed" in capsys.readouterr().out


def run_script(*arguments: str) -> subprocess.CompletedProcess:
    script = ROOT / "packaging" / "windows" / "build-installer.ps1"
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments]
    return subprocess.run(command, capture_output=True, text=True, timeout=300, env=MACHINE_ENV)


@windows_only
def test_the_script_compiles_a_versioned_installer_around_the_exe(tmp_path, qapp):
    exe = tmp_path / "stand-in.exe"
    exe.write_bytes(b"MZ stand-in exe")
    ico = tmp_path / "vitralis.ico"
    build.png_to_ico(str(ROOT / "src" / "vitralis" / "media" / "logo" / "icon.png"), str(ico))
    out = tmp_path / "dist"
    result = run_script("-Binary", str(exe), "-Icon", str(ico), "-OutputDirectory", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    version = re.search(r'(?m)^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    setup = out / installer_name(version, build.TARGET)
    assert result.stdout.strip().splitlines()[-1] == str(setup)
    assert setup.is_file() and setup.read_bytes()[:2] == b"MZ"


@windows_only
def test_the_script_says_what_is_missing(tmp_path):
    result = run_script("-Binary", str(tmp_path / "missing.exe"), "-Icon", str(tmp_path / "missing.ico"))
    assert result.returncode != 0 and "missing.exe is missing" in result.stdout + result.stderr
    exe = tmp_path / "v.exe"
    exe.write_bytes(b"MZ")
    ico = tmp_path / "v.ico"
    ico.write_bytes(b"")
    result = run_script("-Binary", str(exe), "-Icon", str(ico), "-Compiler", str(tmp_path / "no-iscc.exe"))
    assert result.returncode != 0 and "Inno Setup 6 is missing" in result.stdout + result.stderr


SCRIPT = ROOT / "packaging" / "windows" / "vitralis.iss"
LANGUAGE_FILES = ROOT / "packaging" / "windows" / "languages"
PLACEHOLDER = re.compile(r"%\d|%n|\[[a-z/]+\]|&")


def script_section(name: str) -> list[str]:
    """The lines of one ``[section]`` of ``packaging/windows/vitralis.iss``, without comments or blank lines."""
    lines, inside = [], False
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            inside = line.strip() == f"[{name}]"
            continue
        if inside and line.strip() and not line.startswith(";"):
            lines.append(line)
    return lines


def installer_languages() -> list[str]:
    return [re.match(r'Name: "([^"]+)"', line).group(1) for line in script_section("Languages")]


def custom_messages(message: str) -> dict[str, str]:
    found = (line.split("=", 1) for line in script_section("CustomMessages"))
    return {key.split(".")[0]: value for key, value in found if key.endswith("." + message)}


def messages(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"[A-Za-z0-9]+=", line)
    )


def test_the_uninstaller_looks_for_the_mutex_a_running_vitralis_holds():
    """The script and the app must name the same mutex, or uninstalling under a running Vitralis goes ahead and
    leaves its exe behind. Every language's messages file has the sentence that asks to close it."""
    from vitralis.single_instance import RUNNING_MUTEX

    script = SCRIPT.read_text(encoding="utf-8")
    assert f'#define AppMutex "{RUNNING_MUTEX}"' in script
    code = " ".join(script_section("Code"))
    assert "function InitializeUninstall(): Boolean;" in code
    assert "CheckForMutexes('{#AppMutex}')" in code and "msgUninstallAppRunningError" in code
    for path in LANGUAGE_FILES.glob("*.isl"):
        assert "%1" in messages(path)["UninstallAppRunningError"], path.name


def test_the_installer_speaks_every_language_vitralis_does():
    """Each installer language saves a name Settings has, and every Settings language has its installer one."""
    names = custom_messages("AppLanguage")
    assert set(names) == set(installer_languages())
    assert sorted(names.values()) == sorted(label for _, label in LANGUAGES)


def test_every_installer_language_has_every_custom_message():
    for message in ("StartWithWindows", "AppLanguage"):
        assert set(custom_messages(message)) == set(installer_languages()), message


def test_every_bundled_messages_file_is_there():
    for line in script_section("Languages"):
        file = re.search(r'MessagesFile: "([^"]+)"', line).group(1)
        if not file.startswith("compiler:"):
            assert (SCRIPT.parent / file).is_file(), file


def test_the_reintegrated_galician_has_every_message_with_its_placeholders():
    """Vitralis's own translation, checked against the Galician one it was written from."""
    galician = messages(LANGUAGE_FILES / "Galician.isl")
    reintegrated = messages(LANGUAGE_FILES / "GalicianReintegrated.isl")
    assert set(reintegrated) == set(galician)
    for key, text in galician.items():
        if key in ("LanguageName", "LanguageCodePage"):
            continue
        assert sorted(PLACEHOLDER.findall(reintegrated[key])) == sorted(PLACEHOLDER.findall(text)), key


def setup_value(name: str) -> str:
    found = [line.split("=", 1)[1] for line in script_section("Setup") if line.startswith(name + "=")]
    assert len(found) == 1, name
    return found[0]


def test_the_installer_is_per_user_published_by_breren_and_keeps_its_id():
    """Its id must stay the one Vitralis looks its installed-apps record up by, or an in-app update would never
    correct the version shown, and a new installer would install beside the old one instead of over it."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert '#define AppId "{{' + INSTALLER_GUID + '}"' in text
    assert setup_value("PrivilegesRequired") == "lowest"
    assert setup_value("DefaultDirName") == r"{localappdata}\Programs\{#AppName}"
    assert setup_value("AppPublisher") == "Breren"
    assert setup_value("UninstallDisplayName") == "{#AppName}"  # the plain name, never with a version
    assert setup_value("MinVersion") == "10.0.17763"
    assert setup_value("ArchitecturesAllowed") == "x64compatible"
    assert setup_value("OutputBaseFilename") == "vitralis-{#AppVersion}-windows-x86_64-setup"
    assert setup_value("CloseApplications") == "yes" and setup_value("RestartApplications") == "no"
    assert "AppVerName" not in text
    assert '#define AppExe "vitralis.exe"' in text


def test_the_desktop_shortcut_is_offered_unchecked_and_the_launch_is_skipped_when_silent():
    tasks = " ".join(script_section("Tasks"))
    assert 'Name: "desktopicon"' in tasks and "Flags: unchecked" in tasks
    run = " ".join(script_section("Run"))
    assert "postinstall" in run and "skipifsilent" in run


def test_a_test_build_can_change_every_identity_the_script_has():
    text = SCRIPT.read_text(encoding="utf-8")
    for name in ("AppId", "AppName", "AppKey", "AppMutex"):
        assert f"#ifndef {name}" in text, name
    test_script = (ROOT / "packaging" / "windows" / "test-installer.ps1").read_text(encoding="utf-8")
    assert f"[string]$AppId = '{INSTALLER_GUID}'" in test_script


def test_the_exe_carries_every_picture_folder_at_the_place_the_app_reads_it():
    """Regression guard: a logo the build doesn't pack is missing from the toolbar of the packaged exe only."""
    from vitralis.icons import BUNDLED_FOLDERS

    package = Path(build.__file__).parent
    separator = ";" if sys.platform == "win32" else ":"
    packed = {}
    for argument in build.bundled_data(package):
        source, _, inside = argument.removeprefix("--add-data=").rpartition(separator)
        packed[inside] = Path(source)
    assert set(packed) == {folder.as_posix() for folder in BUNDLED_FOLDERS}
    for inside, source in packed.items():
        assert source == package / inside and source.is_dir()


def test_the_logo_on_the_toolbar_is_in_a_folder_the_exe_carries(monkeypatch, tmp_path):
    from vitralis import icons

    assert icons.logo_path().is_file() and icons.logo_path(icons.COMPANY_LOGO).is_file()
    assert icons.LOGO_FOLDER in icons.BUNDLED_FOLDERS
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert icons.logo_path() == tmp_path / "media" / "logo" / "icon.png"  # where PyInstaller unpacks it
