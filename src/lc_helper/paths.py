"""Where lc-helper's files are: the repository when run from source, the folder of lc-helper.exe when built.

assets/ holds the templates, events.json and the OCR model; .local/ holds settings and logs, kept out of git.
"""

import sys
from pathlib import Path

ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
ASSETS = ROOT / "assets"
LOCAL = ROOT / ".local"
