#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 16:06:25.762869
Revised: 2026/11/13 19:56:12.170366
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

from vitralis.updates.registration import INSTALLER_GUID

ISCC_VARIABLE = "ISCC"
"""Path to Inno Setup's ``ISCC.exe`` when it isn't on PATH or in its usual folders."""
ISCC_HINT = "install Inno Setup 6 (winget install JRSoftware.InnoSetup), set ISCC, or build with --no-installer"


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


def find_iscc(env: dict[str, str] | None = None) -> Path | None:
    """Inno Setup's compiler: ``$ISCC``, then PATH, then the per-user and the all-users install folders."""
    env = os.environ if env is None else env
    if env.get(ISCC_VARIABLE):
        given = Path(env[ISCC_VARIABLE])
        return given if given.is_file() else None
    on_path = shutil.which("ISCC")
    if on_path:
        return Path(on_path)
    roots = [env.get("LOCALAPPDATA", ""), env.get("ProgramFiles(x86)", ""), env.get("ProgramFiles", "")]
    for root in filter(None, roots):
        for candidate in (Path(root) / "Programs" / "Inno Setup 6", Path(root) / "Inno Setup 6"):
            if (candidate / "ISCC.exe").is_file():
                return candidate / "ISCC.exe"
    return None


def installer_name(version: str) -> str:
    """The release's installer; ``vitralis.updates.rules`` never takes it for the exe it swaps in."""
    return f"vitralis-{version}-setup.exe"


def iscc_command(iscc: Path, script: Path, version: str, exe: Path, ico: Path, licence: Path, out: Path) -> list[str]:
    return [
        str(iscc),
        "/Q",
        f"/DAppVersion={version}",
        f"/DAppGuid={INSTALLER_GUID}",
        f"/DSourceExe={exe}",
        f"/DIconFile={ico}",
        f"/DLicenseFile={licence}",
        f"/DOutputDir={out}",
        str(script),
    ]


def build_installer(root: Path, version: str, exe: Path, ico: Path, dist: Path) -> Path:
    """Compile ``installer/vitralis.iss`` around ``exe``; exits with a reason when Inno Setup is missing or fails."""
    iscc = find_iscc()
    if iscc is None:
        print(f"\nNo installer: Inno Setup's ISCC.exe wasn't found; {ISCC_HINT}.")
        sys.exit(1)
    command = iscc_command(iscc, root / "installer" / "vitralis.iss", version, exe, ico, root / "LICENSE", dist)
    print("Running Inno Setup...")
    result = subprocess.run(command)
    if result.returncode != 0:
        print("\nInstaller build failed.")
        sys.exit(result.returncode)
    return dist / installer_name(version)


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

    with open(os.path.join(here, "_version.py"), "w") as f:
        f.write(f'__version__ = "{version}"\n')

    exe_name = f"vitralis-{version}"
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
    latest = os.path.join(dist, "vitralis.exe")
    shutil.copy2(built, latest)
    print(f"\nDone ->      {built}")
    print(f"Latest ->    {latest}")
    if not args.no_installer:
        setup = build_installer(Path(root), version, Path(built), Path(ico), Path(dist))
        print(f"Installer -> {setup}")


if __name__ == "__main__":
    main()
