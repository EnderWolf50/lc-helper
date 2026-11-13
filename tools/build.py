"""Build a portable lc-helper folder that runs without uv or Python: dist/lc-helper/lc-helper.exe plus assets/.

Usage: uv run --group build python tools/build.py

PyInstaller onedir (not onefile: a onefile exe unpacks itself to a temp folder on every start). MaaFramework's
native libraries sit in the maa package's bin folder, which PyInstaller's import analysis does not see, so they are
collected explicitly (MaaFramework issue #440 is a build that missed them). assets/ (templates, events.json, the OCR
model) is copied beside the exe, where lc_helper.paths looks when frozen; settings go to .local/ there too. PyInstaller
empties dist/lc-helper on every build, so its .local is set aside first and put back after: a rebuild keeps the
settings of the build it replaces.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "lc-helper"
KEPT = DIST / "lc-helper.local"  # the replaced build's .local while PyInstaller rebuilds


def main():
    if not (ROOT / "assets/maa/model/ocr/rec.onnx").is_file():
        sys.exit("no OCR model: run uv run --group sync python tools/sync_maalc.py first")
    if (APP / ".local").is_dir() and not KEPT.exists():
        shutil.move(APP / ".local", KEPT)
    try:
        build()
    finally:
        if KEPT.is_dir():
            APP.mkdir(parents=True, exist_ok=True)
            shutil.move(KEPT, APP / ".local")
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"{APP / 'lc-helper.exe'}  ({size / 2**20:.0f} MB in all)")


def build():
    subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "tools/entry.py"),
                    "--name", "lc-helper", "--onedir", "--noconsole", "--noconfirm", "--clean",
                    "--paths", str(ROOT / "src"),
                    "--collect-binaries", "maa", "--collect-data", "maa",
                    "--distpath", str(DIST), "--workpath", str(ROOT / "build/pyinstaller"),
                    "--specpath", str(ROOT / "build")], check=True)
    shutil.copytree(ROOT / "assets", APP / "assets", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
