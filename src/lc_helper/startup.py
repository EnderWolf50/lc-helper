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

The readers take the folder from `paths.PACKAGE` when they read, so `start` sets it before the window opens.
"""

import shutil
import sys
import time

from . import package, paths

DOWNLOAD_SECONDS = 60  # all the files of one update; a start waits for them, so the budget is short
LOG_LINES = 200  # the log keeps this many of its last lines, give or take LOG_SLACK
LOG_SLACK = 50
LOG = paths.LOCAL / "resource.log"


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


def run(offline=False, bundled=paths.BUNDLED, downloaded=paths.DOWNLOADED, fetch=package.download, log=print,
        seconds=package.CHECK_SECONDS, download_seconds=DOWNLOAD_SECONDS):
    """The folder to read the package from, after an update when one is due. Never raises."""
    folder = choose(bundled, downloaded)
    log(describe(folder, bundled))
    if offline:
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
    """A copy of folder with package `version` synced into it, which then becomes the downloaded folder."""
    parent = downloaded.parent
    new, old = parent / f"{downloaded.name}.new", parent / f"{downloaded.name}.old"
    for leftover in (new, old):  # what a crash of an earlier start left
        shutil.rmtree(leftover, ignore_errors=True)
    deadline = time.monotonic() + seconds

    def within_budget(url):
        if time.monotonic() >= deadline:
            raise OSError(f"the download took longer than {seconds:g} s")
        return fetch(url)

    try:
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, new)
        count = package.sync(new, source, version, fetch=within_budget, on_skip=lambda line: log(f"resource update: {line}"))
        if downloaded.exists():
            downloaded.rename(old)
        new.rename(downloaded)
    except (package.PackageError, OSError) as e:
        log(f"resource update: kept {describe(folder, bundled)}: {e}")
        return folder
    finally:
        shutil.rmtree(new, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)
    log(f"resource update: {info(folder)['version']} -> {version}, {count} files downloaded")
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


def start(argv, bundled=paths.BUNDLED, downloaded=paths.DOWNLOADED, fetch=package.download, log=None):
    """Choose, and update when due, the package folder, and make it the one the readers use. --offline and --self-test
    never touch the network."""
    def write(line):
        try:
            append_log(LOG, line)
        except OSError:
            pass
        if sys.stdout is not None:  # None in the built lc-helper.exe, which has no console
            print(line)

    folder = run(offline=bool({"--offline", "--self-test"} & set(argv)), bundled=bundled, downloaded=downloaded, fetch=fetch,
                 log=log or write)
    paths.use_package(folder)
    return folder
