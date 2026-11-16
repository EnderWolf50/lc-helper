"""Which resource package lc-helper reads, and the check for a newer one at start (EnderWolf50/maalc ADR 0012).

Two copies can exist. The bundled one (paths.BUNDLED) is what the build carries, the version resource.lock.json named.
The downloaded one (paths.DOWNLOADED, in .local beside the settings, the one folder lc-helper already writes to) is what
an earlier start fetched from maalc-resource. The one in use is the newer of the two, the bundled one when they tie or
the downloaded one has no manifest this code reads (`choose`).

`run` then asks the sources the chosen manifest lists for their newest manifest, within 10 s in all. When it is newer, the
chosen copy is copied beside the downloaded folder, `package.sync` brings the changed files into the copy (every file
checked against the manifest's size and sha256; a format or template version this code does not know skips that part and
keeps its files), and only a copy that is whole replaces the downloaded folder. Any failure (offline, a timeout, a bad
file, a download past its budget) deletes the copy, keeps the folder at hand, and logs one line. Nothing here raises.

Only the lc-helper that holds .local/resource.lock checks and swaps: the lock lives as long as the process, so a second
lc-helper started meanwhile reads the folder as it is and never swaps it under the first.

The readers take the folder from `paths.PACKAGE` when they read, so `start` sets it before the window opens.
"""

import msvcrt
import shutil
import sys
import threading
import time

from . import package, paths

DOWNLOAD_SECONDS = 60  # all the files of one update; a start waits for them, so the budget is short
LOG_LINES = 200  # the log keeps this many of its last lines, give or take LOG_SLACK
LOG_SLACK = 50
LOG = paths.LOCAL / "resource.log"
LOCK = paths.LOCAL / "resource.lock"
_held = []  # the lock file's handle, open until the process ends


def acquire(path):
    """The open lock file at path when this process now holds its lock, None when another one does. Windows releases the
    lock when the handle closes, however the process ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def release(handle):
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    handle.close()


def info(folder):
    """The manifest of the package in folder when this code can read it, else None."""
    try:
        found = package.check_manifest(package.manifest(folder))
    except (package.PackageError, ValueError, OSError):
        return None
    if found["format"] != package.FORMAT or found["template"] != package.TEMPLATE:
        return None
    return found


def choose(bundled, downloaded):
    """The newer package of the two; the bundled one when they tie or the downloaded one cannot be read."""
    ours, theirs = info(bundled), info(downloaded)
    if theirs and (not ours or package.version_key(theirs["version"]) > package.version_key(ours["version"])):
        return downloaded
    return bundled


def describe(folder, bundled):
    found = info(folder) or {}
    where = "bundled" if folder == bundled else "downloaded"
    return (f"resource package {found.get('version', '?')} (client {found.get('client', '?')}, format "
            f"{found.get('format', '?')}, template {found.get('template', '?')}), {where}")


def recover(downloaded):
    """Undo what a start killed between the two renames of a swap left: the folder it moved aside goes back, and the
    copy it was building is deleted. Only the start that holds the lock calls this."""
    new, old = _beside(downloaded, "new"), _beside(downloaded, "old")
    shutil.rmtree(new, ignore_errors=True)
    if old.exists():
        if downloaded.exists():
            shutil.rmtree(old, ignore_errors=True)
        else:
            old.rename(downloaded)


def _beside(downloaded, suffix):
    return downloaded.parent / f"{downloaded.name}.{suffix}"


def run(offline=False, bundled=paths.BUNDLED, downloaded=paths.DOWNLOADED, fetch=package.download, log=print,
        seconds=package.CHECK_SECONDS, download_seconds=DOWNLOAD_SECONDS, may_update=True):
    """The folder to read the package from, after an update when one is due. Never raises. may_update is False for a
    start that does not hold the lock: it reads what is there and checks nothing."""
    try:
        if may_update:
            recover(downloaded)
    except OSError as e:
        log(f"resource update: could not tidy {downloaded.parent}: {e}")
    folder = choose(bundled, downloaded)
    log(describe(folder, bundled))
    if offline:
        return folder
    if not may_update:
        log("resource update: skipped, another lc-helper is running and may be reading the package")
        return folder
    try:
        return update(folder, bundled, downloaded, fetch, log, seconds, download_seconds)
    except Exception as e:  # a start goes on with the copy at hand
        log(f"resource update: kept {describe(folder, bundled)}: {type(e).__name__}: {e}")
        return folder


def update(folder, bundled, downloaded, fetch, log, seconds, download_seconds):
    current = info(folder)
    if not current:
        log(f"resource update: skipped, the package in {folder} has no manifest this lc-helper reads")
        return folder
    if not current.get("sources"):
        log("resource update: skipped, the manifest lists no source (updates off)")
        return folder
    deadline = time.monotonic() + seconds
    remote, source, reasons = None, None, []
    for source in current["sources"]:
        try:
            remote = package.newest(source, fetch, max(deadline - time.monotonic(), 0))
            break
        except package.PackageError as e:
            reasons.append(str(e))
    if remote is None:
        log(f"resource update: kept {describe(folder, bundled)}: {'; '.join(reasons)}")
        return folder
    if package.version_key(remote["version"]) <= package.version_key(current["version"]):
        return folder  # up to date: the log already names the package in use
    if remote["format"] != package.FORMAT and remote["template"] != package.TEMPLATE:
        log(f"resource update: package {remote['version']} has format {remote['format']} and template "
            f"{remote['template']}, this lc-helper reads {package.FORMAT} and {package.TEMPLATE}: skipped")
        return folder
    return download(folder, bundled, downloaded, source, remote["version"], fetch, log, download_seconds)


def download(folder, bundled, downloaded, source, version, fetch, log, seconds):
    """A copy of folder with package `version` synced into it, which then becomes the downloaded folder: the folder that
    was there is moved aside, the copy moved in, and the old one deleted; a failure moves the old one back."""
    parent = downloaded.parent
    new, old = _beside(downloaded, "new"), _beside(downloaded, "old")
    before = package.version_key(info(folder)["version"])
    deadline = time.monotonic() + seconds

    def within_budget(url):
        if time.monotonic() >= deadline:
            raise OSError(f"the download took longer than {seconds:g} s")
        return fetch(url)

    box = {}

    def work():
        try:
            box["count"] = package.sync(new, source, version, fetch=within_budget,
                                        on_skip=lambda line: log(f"resource update: {line}"))
        except BaseException as e:  # handed to the caller below
            box["error"] = e

    try:
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, new)
        # one slow read is no more than urlopen's own timeout, but the files together are bounded here: the thread is
        # left behind when the time is up, and its next fetch raises
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(max(deadline - time.monotonic(), 0) + 1)
        if thread.is_alive():
            raise OSError(f"the download took longer than {seconds:g} s")
        if "error" in box:
            raise box["error"]
        if downloaded.exists():
            downloaded.rename(old)
        try:
            new.rename(downloaded)
        except OSError:
            if not downloaded.exists() and old.exists():
                old.rename(downloaded)  # the folder that was there stays
            raise
        shutil.rmtree(old, ignore_errors=True)
    except (package.PackageError, OSError) as e:
        log(f"resource update: kept {describe(folder, bundled)}: {e}")
        return folder
    finally:
        shutil.rmtree(new, ignore_errors=True)
    log(f"resource update: {'.'.join(map(str, before))} -> {version}, {box['count']} files downloaded")
    return choose(bundled, downloaded)


def append_log(path, line):
    """line with the time in front, added to the log file at path; the file is cut to its last LOG_LINES lines when it
    has grown LOG_SLACK past that."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > LOG_LINES + LOG_SLACK:
        path.write_text("\n".join(lines[-LOG_LINES:]) + "\n", encoding="utf-8")


def start(argv, bundled=paths.BUNDLED, downloaded=paths.DOWNLOADED, fetch=package.download, log=None, lock=LOCK):
    """Choose, and update when due, the package folder, and make it the one the readers use. --offline and --self-test
    never touch the network, and take no lock."""
    def write(line):
        try:
            append_log(LOG, line)
        except OSError:
            pass
        if sys.stdout is not None:  # None in the built lc-helper.exe, which has no console
            print(line)

    offline = bool({"--offline", "--self-test"} & set(argv))
    mine = None
    if not offline:
        try:
            mine = acquire(lock)
        except OSError:
            mine = None
        if mine:
            _held.append(mine)
    folder = run(offline=offline, bundled=bundled, downloaded=downloaded, fetch=fetch, log=log or write,
                 may_update=bool(mine))
    paths.use_package(folder)
    return folder
