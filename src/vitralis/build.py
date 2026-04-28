#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/04/28 16:06:25.762869
Revised: 2026/04/28 16:22:10.695643
"""

import os
import struct
import subprocess
import sys
import tomllib


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


def main() -> None:
    # project root = src/vitralis/../../..
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))

    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        version = tomllib.load(f)["project"]["version"]

    exe_name = f"vitralis-{version}"
    script   = os.path.join(here, "__main__.py")
    build    = os.path.join(root, "build")
    dist     = os.path.join(root, "dist")
    ico      = os.path.join(build, "vitralis.ico")
    png      = os.path.join(here, "media", "logo", "icon.png")

    os.makedirs(build, exist_ok=True)
    os.makedirs(dist, exist_ok=True)

    png_to_ico(png, ico)

    sep       = ";" if sys.platform == "win32" else ":"
    logo_dir  = os.path.join(here, "media", "logo")
    icons_dir = os.path.join(here, "media", "icons")
    src_dir   = os.path.join(root, "src")
    cmd = [
        sys.executable, "-m", "PyInstaller",
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
    if result.returncode == 0:
        print(f"\nDone -> {dist}\\{exe_name}.exe")
    else:
        print("\nBuild failed.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
