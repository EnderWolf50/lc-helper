"""Run lc-helper's screen readings over every screenshot in a folder and print one row per screen.

Usage: uv run python tools/sweep_screens.py [folder]   (default: maalc's tests/screens, see tools/sync_maalc.py)

Columns: battle_turn box and score, turn_playing, start plaque, disc lit, focused gear, staggered slots.
The thresholds' claims ("never fires on X") are checked against this sweep (tests/test_vision.py runs it).
"""

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lc_helper import vision  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402


def best(image, name, roi):
    area = vision.crop(image, roi)
    return float(cv2.minMaxLoc(cv2.matchTemplate(area, vision.template(name), cv2.TM_CCOEFF_NORMED))[1])


def read(image):
    box = vision.battle_turn(image)
    row = {"turn": box, "turn_score": max(best(image, "battle_turn.png", vision.BATTLE_TURN_ROI),
                                          best(image, "battle_turn_pressed.png", vision.BATTLE_TURN_ROI)),
           "playing": vision.turn_playing(image), "menu": vision.battle_menu(image), "popup": vision.popup(image)}
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


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else maalc_dir() / "tests/screens"
    for name, row in sweep(folder).items():
        if row["turn"] or row["playing"] or row["menu"] or row["popup"] or row["turn_score"] > 0.5:
            print(name, row)


if __name__ == "__main__":
    main()
