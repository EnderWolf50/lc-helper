"""Cut lc-helper's own templates (the ones maalc reads by OCR) out of maalc's live captures into assets/templates.

Usage: uv run --group sync python tools/make_templates.py

wipe_text.png: the line "All participating Sinners have been" of the wipe dialog (WipeDialog.png), found by OCR so
the cut follows the text. tests/test_vision.py checks it fires on that capture and on no other.
"""

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lc_helper import ocr, vision  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402


def cut(capture, roi, starts, name, pad=3):
    image = vision.imread(maalc_dir() / "tests/screens" / capture)
    box = next(b for text, b in ocr.lines(image, roi) if text.startswith(starts))
    x, y, w, h = box
    piece = image[y - pad:y + h + pad, x - pad:x + w + pad]
    path = vision.ASSETS / "templates" / name
    path.write_bytes(cv2.imencode(".png", piece)[1].tobytes())
    print(path, box)


def main():
    cut("WipeDialog.png", vision.WIPE_ROI, "All participating", "wipe_text.png")


if __name__ == "__main__":
    main()
