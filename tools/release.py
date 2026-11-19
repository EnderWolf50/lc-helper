"""Publish a version of lc-helper as a GitHub release: the portable folder zipped, under the tag v<version>.

Usage: uv run --group build python tools/release.py <version> --notes <notes.md> [--dry-run]

Run it on main, clean and level with origin/main. When pyproject.toml names another version, it is changed to
<version> (uv.lock with it), committed as "Version <version>" and pushed to main. The tag waits for that commit's test
run (.github/workflows/test.yml) to pass. Then the folder is built from it (tools/fetch_resource.py, tools/build.py),
checked (tools/exe_check.py), zipped to dist/lc-helper-<version>-windows.zip and published with the notes as the
release text. --dry-run builds, checks and zips the commit as it is, and commits, pushes and publishes nothing.

The zip leaves out the built folder's .local: build.py keeps the settings and the battle log of the build it replaces
there, and they are whoever built it's own.
"""

import argparse
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "dist/lc-helper"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = "test.yml"
VERSION_LINE = re.compile(r'^version = "([^"]*)"$', re.MULTILINE)
RUN_APPEARS = 120  # seconds GitHub gets to start the test run of a pushed commit


def check_version(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"{version!r} is not a version: give three numbers, such as 0.3.0")


def version_of(text):
    found = VERSION_LINE.findall(text)
    if len(found) != 1:
        sys.exit(f"pyproject.toml has {len(found)} version lines, not one")
    return found[0]


def bumped(text, version):
    """text with its one version line naming version."""
    version_of(text)
    return VERSION_LINE.sub(lambda _: f'version = "{version}"', text)


def pack(app, out):
    """Zip app as lc-helper/..., without its .local; the number of files zipped."""
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(app.rglob("*")):
            rel = f.relative_to(app)
            if rel.parts[0] == ".local" or not f.is_file():
                continue
            z.write(f, Path("lc-helper") / rel)
            count += 1
    with zipfile.ZipFile(out) as z:
        if any(Path(n).parts[1:2] == (".local",) for n in z.namelist()):
            sys.exit(f"{out} holds .local: it is not published")
    return count


def run(*args, capture=False):
    done = subprocess.run(args, cwd=ROOT, check=True, text=True, encoding="utf-8",
                          stdout=subprocess.PIPE if capture else None)
    return done.stdout.strip() if capture else None


def git(*args):
    return run("git", *args, capture=True)


def check_tree(tag):
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        sys.exit("check out main first")
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("commit or set aside your changes first")
    run("git", "fetch", "--quiet", "--tags", "origin")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        sys.exit("main is not level with origin/main: pull or push first")
    if git("tag", "--list", tag):
        sys.exit(f"{tag} already exists")


def bump(version):
    """Commit and push the version on main when pyproject.toml names another."""
    text = PYPROJECT.read_text(encoding="utf-8")
    if version_of(text) == version:
        return
    PYPROJECT.write_text(bumped(text, version), encoding="utf-8")
    run("uv", "lock")
    run("git", "add", "pyproject.toml", "uv.lock")
    run("git", "commit", "--quiet", "-m", f"Version {version}")
    run("git", "push", "origin", "main")


def wait_for_tests(sha):
    """Stop unless the test run of sha passes."""
    deadline = time.monotonic() + RUN_APPEARS
    while not (found := run("gh", "run", "list", "--workflow", WORKFLOW, "--commit", sha, "--limit", "1",
                            "--json", "databaseId", "--jq", ".[0].databaseId // empty", capture=True)):
        if time.monotonic() > deadline:
            sys.exit(f"no {WORKFLOW} run for {sha} after {RUN_APPEARS} s")
        time.sleep(10)
    print(f"waiting for {WORKFLOW} run {found} on {sha[:7]}")
    if subprocess.run(["gh", "run", "watch", found, "--exit-status"], cwd=ROOT, stdout=subprocess.DEVNULL).returncode:
        sys.exit(f"{WORKFLOW} run {found} did not pass: nothing is tagged")


def build():
    run("uv", "run", "python", "tools/fetch_resource.py")
    run("uv", "run", "--group", "build", "python", "tools/build.py")
    run("uv", "run", "python", "tools/exe_check.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--notes", type=Path, required=True, help="the release text, in Markdown")
    parser.add_argument("--dry-run", action="store_true", help="build, check and zip only")
    args = parser.parse_args()
    check_version(args.version)
    tag = f"v{args.version}"
    if not args.notes.is_file():
        sys.exit(f"no notes at {args.notes}")
    check_tree(tag)
    if not args.dry_run:
        bump(args.version)
        sha = git("rev-parse", "HEAD")
        wait_for_tests(sha)
    build()
    out = ROOT / f"dist/lc-helper-{args.version}-windows.zip"
    count = pack(APP, out)
    print(f"{out}: {count} files, {out.stat().st_size / 2**20:.0f} MB")
    if args.dry_run:
        return
    run("gh", "release", "create", tag, str(out), "--target", sha, "--title", f"lc-helper {args.version}",
        "--notes-file", str(args.notes))


if __name__ == "__main__":
    main()
