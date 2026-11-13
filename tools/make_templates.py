"""Cut lc-helper's own templates out of live captures into assets/templates.

Usage: uv run --group sync python tools/make_templates.py

wipe_text.png: the line "All participating Sinners have been" of the wipe dialog (maalc's WipeDialog.png), found by
OCR so the cut follows the text. tests/test_vision.py checks it fires on that capture and on no other.

battle_turn_llc.png: the Win Rate label of an LLC (Simplified Chinese) client, which reads 胜率 where maalc's template
reads Win Rate (tests/screens_llc/LlcBattleTurn6.png, a PC client capture). The plate is the same picture in both
languages, so the plate is found by its text-free right end (cut from maalc's English BattleTurn.png) and the Chinese
label is cut where the English template sits on it: every tap offset from the label (Win Rate, Damage, START, the
slots) then holds unchanged.
"""

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lc_helper import ocr, vision  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402

LLC_SCREENS = Path(__file__).resolve().parent.parent / "tests/screens_llc"
PLATE_END = (1026, 536, 26, 20)  # the Win Rate plate's right end (triangle, border) on maalc's BattleTurn.png


def save(piece, name, box):
    path = vision.ASSETS / "templates" / name
    path.write_bytes(cv2.imencode(".png", piece)[1].tobytes())
    print(path, box)


def cut(capture, roi, starts, name, pad=3):
    image = vision.imread(maalc_dir() / "tests/screens" / capture)
    box = next(b for text, b in ocr.lines(image, roi) if text.startswith(starts))
    x, y, w, h = box
    save(image[y - pad:y + h + pad, x - pad:x + w + pad], name, box)


def cut_turn_label(capture, name):
    english = vision.imread(maalc_dir() / "tests/screens/BattleTurn.png")
    ex, ey, ew, eh = vision.battle_turn(english)
    image = vision.imread(LLC_SCREENS / capture)
    x0, y0, w0, h0 = vision.BATTLE_TURN_ROI
    area = vision.crop(image, (x0, y0 - 15, w0, h0 + 30))
    _, score, _, (bx, by) = cv2.minMaxLoc(cv2.matchTemplate(area, vision.crop(english, PLATE_END), cv2.TM_CCOEFF_NORMED))
    assert score > 0.85, f"the plate's end not found on {capture} ({score:.2f})"
    x, y = x0 + bx - (PLATE_END[0] - ex), y0 - 15 + by - (PLATE_END[1] - ey)
    save(image[y:y + eh, x:x + ew], name, (x, y, ew, eh))


def main():
    cut("WipeDialog.png", vision.WIPE_ROI, "All participating", "wipe_text.png")
    cut_turn_label("LlcBattleTurn6.png", "battle_turn_llc.png")


if __name__ == "__main__":
    main()
