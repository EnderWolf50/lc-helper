"""Fetch the resource package version named in resource.lock.json into resource/ (gitignored).

Usage: uv run python tools/fetch_resource.py

Downloads that version's manifest and the files lc-helper reads (src/lc_helper/package.py USED) from maalc-resource,
checking each file's size and sha256. A rerun downloads only what is missing or altered, and a failed run keeps what
was there. Another package version: change `version` in resource.lock.json (a tag of maalc-resource) and rerun.
The OCR model is not in the package: tools/fetch_ocr.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lc_helper import package  # noqa: E402
from lc_helper.paths import PACKAGE  # noqa: E402


def main():
    lock = package.read_lock()
    try:
        count = package.sync(PACKAGE, lock["source"], lock["version"])
    except package.PackageError as e:
        sys.exit(f"resource package {lock['version']}: {e}")
    info = package.manifest(PACKAGE)
    print(f"resource package {info['version']} (client {info['client']}) in {PACKAGE}: {count} files downloaded")


if __name__ == "__main__":
    main()
