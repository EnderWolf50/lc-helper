"""Build a portable lc-helper folder that runs without uv or Python: dist/lc-helper/lc-helper.exe plus assets/.

Usage: uv run --group build python tools/build.py

PyInstaller onedir (not onefile: a onefile exe unpacks itself to a temp folder on every start). MaaFramework's
native libraries sit in the maa package's bin folder, which PyInstaller's import analysis does not see, so they are
collected explicitly (MaaFramework issue #440 is a build that missed them). assets/ (templates, events.json, the OCR
model) is copied beside the exe, where lc_helper.paths looks when frozen; settings go to .local/ there too. PyInstaller
empties dist/lc-helper on every build, so its .local is set aside first and put back after: a rebuild keeps the
settings of the build it replaces.

Two builds at once lost the built app's settings on 2026-11-14: the one stopped early put the other's set-aside .local
back into the folder the other then emptied. So a build holds build/build.lock while it runs, and refuses to start
while another holds it; and every build first copies the built app's .local to .local/app-backups/<time>/ in this
repository, keeping the last KEEP_BACKUPS.
"""

import msvcrt
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "lc-helper"
KEPT = DIST / "lc-helper.local"  # the replaced build's .local while PyInstaller rebuilds
LOCK = ROOT / "build/build.lock"
BACKUPS = ROOT / ".local/app-backups"
KEEP_BACKUPS = 5


def main():
    if not (ROOT / "assets/maa/model/ocr/rec.onnx").is_file():
        sys.exit("no OCR model: run uv run --group sync python tools/sync_maalc.py first")
    with alone():
        if running(APP / "lc-helper.exe"):
            sys.exit(f"{APP / 'lc-helper.exe'} is open: close it first, the build empties the folder it runs from")
        if saved := back_up():
            print(f"the built app's .local copied to {saved}")
        if (APP / ".local").is_dir() and not KEPT.exists():
            shutil.move(APP / ".local", KEPT)
        try:
            build()
        finally:
            put_back()
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"{APP / 'lc-helper.exe'}  ({size / 2**20:.0f} MB in all)")


@contextmanager
def alone():
    """Hold build/build.lock while the build runs: a build started meanwhile stops at once. Windows lets go of the
    lock when the process ends, however it ends, so a killed build leaves none behind."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+b") as f:
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            sys.exit(f"another build is running ({LOCK} is held): wait for it to end, or end its python process")
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def back_up():
    """A copy of the built app's .local in .local/app-backups/<time>/, MaaFramework's logs left out; the oldest copies
    past KEEP_BACKUPS are removed. None when there is none to copy."""
    if not (APP / ".local").is_dir():
        return None
    to = BACKUPS / time.strftime("%Y%m%d-%H%M%S")
    shutil.copytree(APP / ".local", to, ignore=shutil.ignore_patterns("debug", "*.log"))
    for old in sorted(p for p in BACKUPS.iterdir() if p.is_dir())[:-KEEP_BACKUPS]:
        shutil.rmtree(old)
    return to


def put_back():
    """The set-aside .local back into the built app; beside a .local already there, never into it."""
    if not KEPT.is_dir():
        return
    APP.mkdir(parents=True, exist_ok=True)
    to = APP / ".local"
    if to.exists():
        to = APP / f".local-kept-{time.strftime('%Y%m%d-%H%M%S')}"
        print(f"{APP / '.local'} already exists: the replaced build's settings are in {to}")
    shutil.move(KEPT, to)


def running(exe):
    """Whether exe runs: Windows refuses to open a running program's file for writing (checked 2026-11-14 on
    lc-helper.exe open, PermissionError 13). Nothing is written."""
    try:
        with open(exe, "r+b"):
            return False
    except FileNotFoundError:
        return False
    except PermissionError:
        return True


def build():
    subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "tools/entry.py"),
                    "--name", "lc-helper", "--onedir", "--noconsole", "--noconfirm", "--clean",
                    "--paths", str(ROOT / "src"),
                    "--collect-binaries", "maa", "--collect-data", "maa",
                    "--distpath", str(DIST), "--workpath", str(ROOT / "build/pyinstaller"),
                    "--specpath", str(ROOT / "build")], check=True)
    shutil.copytree(ROOT / "assets", APP / "assets", dirs_exist_ok=True)
    for name in ("LICENSE", "NOTICE.md"):  # what the folder hands on carries its licences (CC BY-NC-SA 4.0 for LLC's text)
        shutil.copy2(ROOT / name, APP)


if __name__ == "__main__":
    main()
