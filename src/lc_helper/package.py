"""maalc's resource package: the game data, templates and icons lc-helper reads, fetched from maalc-resource.

A package is a folder with `manifest.json` (version, client, format, template, and every file's size and sha256) and
the files under data/, image/ and pipeline/. maalc publishes each version as a tag of maalc-resource, so
`<source>/<version>/<path>` is one file of it for as long as the tag stands, and `<source>/main/manifest.json` is the
newest manifest. The lock file `resource.lock.json` names the version this checkout uses; tools/fetch_resource.py
syncs it, and the app reads the folder through `path` and `manifest`.

`sync` is the one entry point that downloads: the tool calls it with the lock.
"""

import hashlib
import json
import os
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch
from pathlib import PurePosixPath

from .paths import PACKAGE, ROOT

# The versions of the data (data/) and of the templates (image/, pipeline/) this code reads; a package of another
# version is refused rather than read wrongly (maalc docs: 格式版本, 模板版本).
FORMAT = 1
TEMPLATE = 1
LOCK = ROOT / "resource.lock.json"
PARTS = ("data/", "image/", "pipeline/")
TIMEOUT = 30
WORKERS = 8

# What lc-helper reads of the package; everything else in it (the pipeline, gift search images, ...) is never fetched.
USED = (
    "data/event_table.json", "data/event_text.json", "data/gift_text.json", "data/trial_text.json",
    "data/gift_recipes.json", "data/trials.yaml", "data/stagger_word.png",
    "data/keyword_icons/*.webp", "data/gift_icons/*.webp", "data/sin_icons/*.png", "data/gift_slot/plate.png",
    "image/Battle/BattleTurn.png", "image/Battle/BattleTurnPressed.png", "image/Battle/BattleStart.png",
    "image/Battle/BattlePause.png", "image/Battle/BattleMenuResume.png",
    "image/Screen/Connecting.png", "image/Screen/DialogButton.png",
)
# lc-helper's template names (vision.template) that the package supplies; the others are cut by lc-helper itself
# (tools/make_templates.py) and stay in assets/templates.
TEMPLATES = {
    "battle_turn.png": "image/Battle/BattleTurn.png",
    "battle_turn_pressed.png": "image/Battle/BattleTurnPressed.png",
    "battle_start.png": "image/Battle/BattleStart.png",
    "battle_pause.png": "image/Battle/BattlePause.png",
    "battle_menu_resume.png": "image/Battle/BattleMenuResume.png",
    "connecting.png": "image/Screen/Connecting.png",
    "dialog_button.png": "image/Screen/DialogButton.png",
    "stagger_word.png": "data/stagger_word.png",
}


class PackageError(Exception):
    """The package cannot be read or fetched; the message says which file or field and why."""


def used(path):
    return any(fnmatch(path, pattern) for pattern in USED)


def download(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        return response.read()


def read_lock(path=LOCK):
    lock = json.loads(path.read_text(encoding="utf-8"))
    for key in ("version", "source"):
        if not isinstance(lock.get(key), str) or not lock[key]:
            raise PackageError(f"{path.name} has no {key}")
    return lock


def manifest(folder=PACKAGE):
    """The manifest of the package in folder."""
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackageError(f"no resource package in {folder}: run uv run python tools/fetch_resource.py") from None


def path(relative, folder=PACKAGE):
    """A file of the package in folder; the error says to fetch it when it is not there."""
    found = folder / relative
    if not found.is_file():
        manifest(folder)  # the folder has no package at all
        raise PackageError(f"{relative} is not in the resource package {folder}")
    return found


def _same(file, entry):
    if not file.is_file() or file.stat().st_size != entry["size"]:
        return False
    return hashlib.sha256(file.read_bytes()).hexdigest() == entry["sha256"]


def _check_path(relative):
    parts = PurePosixPath(relative).parts
    if not relative.startswith(PARTS) or ".." in parts or "." in parts or ":" in relative or "\\" in relative:
        raise PackageError(f"the manifest names a path outside the package: {relative}")


def sync(folder, source, version, fetch=download, wanted=used):
    """Make folder hold the wanted files of package `version` of source, each checked against the manifest's size
    and sha256. Idempotent: a file that is there and matches is not downloaded again; one that is cut short or
    altered is fetched anew; a file of an earlier version that the wanted set no longer holds is deleted. Files are
    fetched into a staging folder first and swapped in only when all of them verified, with the manifest written last,
    so a failure keeps what folder held and a crash leaves a state the next run completes. Returns the number of files
    downloaded."""
    try:
        text = fetch(f"{source}/{version}/manifest.json")
        new = json.loads(text)
    except (OSError, ValueError) as e:
        raise PackageError(f"manifest of {version}: {e}") from e
    if new.get("version") != version:
        raise PackageError(f"asked for package {version}, the manifest is {new.get('version')}")
    for field, known in (("format", FORMAT), ("template", TEMPLATE)):
        if new.get(field) != known:
            raise PackageError(f"package {version} has {field} {new.get(field)}, this lc-helper reads {known}")
    files = {p: e for p, e in new["files"].items() if wanted(p)}
    for relative in files:
        _check_path(relative)

    staging = folder / ".staging"
    shutil.rmtree(staging, ignore_errors=True)
    missing = [p for p, e in files.items() if not _same(folder / p, e)]
    def stage(relative):
        try:
            data = fetch(f"{source}/{version}/{relative}")
        except OSError as e:
            raise PackageError(f"{relative}: {e}") from e
        entry = files[relative]
        if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise PackageError(f"{relative} does not match the manifest's size and sha256")
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    try:
        with ThreadPoolExecutor(WORKERS) as pool:  # one request takes a third of a second; the files one after another take minutes
            list(pool.map(stage, missing))
        for relative in missing:
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, target)
        for old in _tracked(folder):
            if old not in files:
                (folder / old).unlink()
        _prune(folder)
        temp = folder / "manifest.json.part"
        temp.write_bytes(text)
        os.replace(temp, folder / "manifest.json")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return len(missing)


def _tracked(folder):
    return [p.relative_to(folder).as_posix() for part in PARTS for p in (folder / part.rstrip("/")).rglob("*")
            if p.is_file()]


def _prune(folder):
    for part in PARTS:
        for d in sorted((folder / part.rstrip("/")).rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
