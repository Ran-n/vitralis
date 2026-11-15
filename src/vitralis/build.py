#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 16:06:25.762869
Revised: 2026/11/15 14:26:59.902779
"""

import argparse
import os
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

from vitralis.updates.target import RELEASE_TARGET_VARIABLE, TARGETS, asset_name


def png_to_ico(png_path: str, ico_path: str) -> None:
    """Convert a PNG to a multi-resolution ICO file."""
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    src = QPixmap(png_path)
    if src.isNull():
        raise FileNotFoundError(f"Could not load icon: {png_path}")

    sizes = [16, 32, 48, 64, 128, 256]
    frames: list[bytes] = []
    for size in sizes:
        scaled = src.scaled(size, size)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "PNG")
        frames.append(bytes(buf.data()))

    n = len(frames)
    header = struct.pack("<HHH", 0, 1, n)
    data_offset = 6 + n * 16
    pos = data_offset
    offsets: list[int] = []
    for raw in frames:
        offsets.append(pos)
        pos += len(raw)

    directory = b""
    for i, raw in enumerate(frames):
        s = sizes[i]
        w = h = s if s < 256 else 0
        directory += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(raw), offsets[i])

    with open(ico_path, "wb") as f:
        f.write(header + directory + b"".join(frames))
    print(f"Icon -> {ico_path}")


INSTALLER_SCRIPT = Path("packaging") / "windows" / "build-installer.ps1"
TARGET = "windows-x86_64"
"""What this machine builds: Vitralis runs on Windows on x86-64 only."""


def release_target(env: dict[str, str] | None = None) -> str | None:
    """``VITRALIS_RELEASE_TARGET`` when it names a target; ``None`` (a build from source) when unset. A value
    that isn't a target stops the build rather than ship an exe that would never update."""
    env = os.environ if env is None else env
    given = env.get(RELEASE_TARGET_VARIABLE, "")
    if not given:
        return None
    if given not in TARGETS:
        print(f"{RELEASE_TARGET_VARIABLE}={given!r} isn't a target; targets: {', '.join(TARGETS)}")
        sys.exit(2)
    return given


def write_build_info(package: Path, version: str, target: str | None) -> None:
    """``_version.py`` (the version the exe reports) and ``_release.py`` (its release target, ``None`` for a
    build from source), both read by the packaged exe."""
    (package / "_version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (package / "_release.py").write_text(f"TARGET = {target!r}\n", encoding="utf-8")


def installer_command(root: Path, exe: Path, ico: Path, dist: Path) -> list[str]:
    script = root / INSTALLER_SCRIPT
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Binary",
        str(exe),
        "-OutputDirectory",
        str(dist),
        "-Icon",
        str(ico),
    ]


def build_installer(root: Path, exe: Path, ico: Path, dist: Path) -> None:
    """Run ``packaging/windows/build-installer.ps1`` around ``exe``; exits with its code when it fails (it says
    why, Inno Setup missing included)."""
    print("Building the installer...")
    result = subprocess.run(installer_command(root, exe, ico, dist))
    if result.returncode != 0:
        print("\nInstaller build failed.")
        sys.exit(result.returncode)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build", description="Build the Windows exe and its installer.")
    parser.add_argument("--no-installer", action="store_true", help="build only the exe (no Inno Setup needed)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_arguments(sys.argv[1:])
    # project root = src/vitralis/../../..
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))

    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        version = tomllib.load(f)["project"]["version"]

    target = release_target()
    write_build_info(Path(here), version, target)
    print(f"Building Vitralis {version}, " + (f"release target {target}" if target else "a build from source"))

    exe_name = asset_name(version, TARGET).removesuffix(".exe")
    script = os.path.join(here, "__main__.py")
    build = os.path.join(root, "build")
    dist = os.path.join(root, "dist")
    ico = os.path.join(build, "vitralis.ico")
    png = os.path.join(here, "media", "logo", "icon.png")

    os.makedirs(build, exist_ok=True)
    os.makedirs(dist, exist_ok=True)

    png_to_ico(png, ico)

    sep = ";" if sys.platform == "win32" else ":"
    logo_dir = os.path.join(here, "media", "logo")
    icons_dir = os.path.join(here, "media", "icons")
    src_dir = os.path.join(root, "src")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        f"--icon={ico}",
        f"--name={exe_name}",
        f"--distpath={dist}",
        f"--workpath={build}",
        f"--specpath={build}",
        f"--paths={src_dir}",
        f"--add-data={logo_dir}{sep}media/logo",
        f"--add-data={icons_dir}{sep}media/icons",
        script,
    ]

    print("Running PyInstaller...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nBuild failed.")
        sys.exit(result.returncode)
    built = os.path.join(dist, f"{exe_name}.exe")
    print(f"\nDone ->      {built}")
    if not args.no_installer:
        build_installer(Path(root), Path(built), Path(ico), Path(dist))


if __name__ == "__main__":
    main()
