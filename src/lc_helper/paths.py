"""Where lc-helper's files are: the repository when run from source, the folder of lc-helper.exe when built.

assets/ holds what lc-helper keeps itself (hand-cut templates, sin icons, fonts) and the OCR model; resource/ the
resource package fetched from maalc-resource (src/lc_helper/package.py, gitignored); .local/ settings and logs.
"""

import sys
from pathlib import Path

BUILT = getattr(sys, "frozen", False)  # running as lc-helper.exe
ROOT = Path(sys.executable).parent if BUILT else Path(__file__).resolve().parent.parent.parent
ASSETS = ROOT / "assets"
PACKAGE = ROOT / "resource"
LOCAL = ROOT / ".local"
