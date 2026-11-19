"""Run lc-helper's screen readings over every screenshot in a folder and print one row per screen.

Usage: uv run python tools/sweep_screens.py [--gifts] [folder]   (default: maalc's tests/screens, see
tools/maalc_checkout.py)

Columns: battle_turn box and score, turn_playing, start plaque, disc lit, focused gear, staggered slots.
The thresholds' claims ("never fires on X") are checked against this sweep (tests/test_vision.py runs it).
--gifts: each screen read as a gift screen instead (gifts.gift_page, then gifts.read_gifts), its page and gift ids,
OCR included (about a minute).
"""

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lc_helper import gifts, ocr, vision  # noqa: E402
from maalc_checkout import maalc_dir  # noqa: E402


def best(image, name, roi):
    area = vision.crop(image, roi)
    return float(cv2.minMaxLoc(cv2.matchTemplate(area, vision.template(name), cv2.TM_CCOEFF_NORMED))[1])


def read(image):
    box = vision.battle_turn(image)
    row = {"turn": box, "turn_score": max(best(image, "battle_turn.png", vision.BATTLE_TURN_ROI),
                                          best(image, "battle_turn_pressed.png", vision.BATTLE_TURN_ROI)),
           "playing": vision.turn_playing(image), "menu": vision.battle_menu(image), "popup": vision.popup(image),
           "victory": vision.victory(image), "wiped": vision.wiped(image)}
    if box:
        disc = vision.start_disc(box)
        xs = vision.slot_xs(box[0])
        row |= {"plaque": vision.start_shown(image, disc), "lit": vision.disc_lit(image, disc),
                "hollow": vision.gear_hollow(image, box),
                "staggered": [i for i, s in enumerate(vision.staggered(image, xs), 1) if s]}
    return row


def sweep(folder):
    return {p.name: read(vision.imread(p)) for p in sorted(Path(folder).glob("*.png"))
            if vision.imread(p).shape[:2] == (720, 1280)}


def gift_sweep(folder):
    """{name: (page, gift ids)} of every 1280x720 capture in folder that reads as a gift screen."""
    def read(image, roi, only_rec):
        return [t for t, _ in ocr.lines(image, roi, only_rec=only_rec)]
    rows = {}
    for p in sorted(Path(folder).glob("*.png")):
        image = vision.imread(p)
        if image.shape[:2] == (720, 1280) and (page := gifts.gift_page(image, read)):
            rows[p.name] = (page, [g["id"] for g, _ in gifts.read_gifts(image, page, ocr.lines).gifts])
    return rows


def main():
    args = [a for a in sys.argv[1:] if a != "--gifts"]
    folder = Path(args[0]) if args else maalc_dir() / "tests/screens"
    if "--gifts" in sys.argv:
        for name, row in gift_sweep(folder).items():
            print(name, *row)
        return
    for name, row in sweep(folder).items():
        if (row["turn"] or row["playing"] or row["menu"] or row["popup"] or row["victory"] or row["wiped"]
                or row["turn_score"] > 0.5):
            print(name, row)


if __name__ == "__main__":
    main()
