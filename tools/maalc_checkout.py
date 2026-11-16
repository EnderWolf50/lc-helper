"""Where a maalc checkout is, for the tools and tests that read what the resource package does not carry: maalc's
tests/screens (live captures).

The folder is the path in .local/maalc_dir, else ../maalc next to this repository. lc-helper itself needs none of it
to run or build: the game data, templates and icons come from the resource package (tools/fetch_resource.py).
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def maalc_dir():
    local = REPO / ".local/maalc_dir"
    path = Path(local.read_text(encoding="utf-8").strip()) if local.is_file() else REPO.parent / "maalc"
    if not (path / "tests/screens").is_dir():
        raise SystemExit(f"no maalc checkout at {path}: write its path into .local/maalc_dir")
    return path
