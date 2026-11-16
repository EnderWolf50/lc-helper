"""Where lc-helper's files are: the repository when run from source, the folder of lc-helper.exe when built.

assets/ holds what lc-helper keeps itself (hand-cut templates, fonts) and the OCR model; resource/ the
resource package fetched from maalc-resource (src/lc_helper/package.py, gitignored); .local/ settings and logs, and
.local/resource the package a start downloaded (src/lc_helper/startup.py).

PACKAGE is the package folder in use. Readers look it up as `paths.PACKAGE` when they read, never import the name, so
that startup.run can set it before anything loads.
"""

import sys
from pathlib import Path

BUILT = getattr(sys, "frozen", False)  # running as lc-helper.exe
ROOT = Path(sys.executable).parent if BUILT else Path(__file__).resolve().parent.parent.parent
ASSETS = ROOT / "assets"
BUNDLED = ROOT / "resource"  # the package the build carries, or fetch_resource.py put there
LOCAL = ROOT / ".local"
DOWNLOADED = LOCAL / "resource"  # the package a start downloaded, newer than the bundled one
PACKAGE = BUNDLED


def use_package(folder):
    """Make folder the package the readers use; startup.run does this once, before any of them loads."""
    global PACKAGE
    PACKAGE = folder
