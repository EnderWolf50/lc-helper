"""Draw the hints the overlay puts on the game over captures of Choices pages and of the gift choice after a boss,
without the game: a PNG per capture in .local/evidence/overlay-*.png.

Usage: uv run python tools/overlay_preview.py [width]   (default 1920: the game window's width; 1280 is the smallest)

The captures are maalc's tests/screens (tools/sync_maalc.py), read as lc-helper reads them, with Charge and Sinking
as the recommended keywords. The "busiest" pictures put the options with the most to say (gifts, chances, a check's
costs) on EventChoicesLitTop.png's three rows: their text on the game is not theirs, only the cards are; their
"opened" twins have the top card opened in full, as a click on it does. The post-boss
captures get each card's worth above it (trials.worth), the same keywords as the team's.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")  # offscreen has no CJK font; nothing is shown either way
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from lc_helper import events, gifts, ocr, overlay, recommend, trials, vision  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402

KEYWORDS = ["Charge", "Sinking"]
CAPTURES = ["EventChoices.png", "EventChoicesLitTop.png", "EventChoicesUsed.png", "EventChoicesScrolledBack.png"]
TRIAL_CAPTURES = ["BossGiftTrials.png", "BossGiftTrialsHard.png", "BossGiftTrialsFloor3.png"]
ROWS = [(733, 217, 300, 22), (733, 343, 300, 22), (733, 470, 300, 22)]  # EventChoicesLitTop.png's first lines


def qimage(image, width):
    h, w = image.shape[:2]
    picture = QImage(image.data, w, h, image.strides[0], QImage.Format_BGR888)
    return picture.scaledToWidth(width, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32_Premultiplied)


def draw(image, items, width, out, worths=(), opened=None):
    picture = qimage(image, width)
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(picture.width(), picture.height())
    o.items, o.trials, o.opened = items, list(worths), opened
    p = QPainter(picture)
    o.render(p, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
    p.end()
    picture.save(str(out))
    print(out)


def busiest(count):
    """The options with the most outcomes, gifts and costs in the table."""
    def weight(o):
        found = events.outcomes(o)
        return len(found) + sum(len(f.gifts) + len(f.gets) for f in found) + len(events.check_sins(o))
    return sorted((o for e in events.book()["events"] for o in e["options"] if o["text"]), key=weight)[-count:]


def main():
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1920
    QApplication.instance() or QApplication([])
    out = ROOT / ".local/evidence"
    out.mkdir(parents=True, exist_ok=True)
    screens = maalc_dir() / "tests/screens"
    for name in CAPTURES:
        image = vision.imread(screens / name)
        reading = events.read_screen(image)
        pick = recommend.best(reading.event, KEYWORDS, reading.closed)
        items = overlay.labels(reading, lambda o: pick is not None and o is pick[0])
        draw(image, items, width, out / f"overlay-{Path(name).stem}-{width}.png")
    background = vision.imread(screens / "EventChoicesLitTop.png")
    options = busiest(6)
    for i in (0, 3):
        items = [overlay.Label(box, o, recommended=j == 0, middle=box[1] + 13)
                 for j, (box, o) in enumerate(zip(ROWS, options[i:i + 3]))]
        draw(background, items, width, out / f"overlay-busiest-{i // 3 + 1}-{width}.png")
        draw(background, items, width, out / f"overlay-busiest-{i // 3 + 1}-opened-{width}.png",
             opened=items[0].option["text"])
    for name in TRIAL_CAPTURES:
        image = vision.imread(screens / name)
        page = trials.read_page(image, ocr.lines, gifts.read_gifts(image, "choice", ocr.lines))
        draw(image, [], width, out / f"overlay-{Path(name).stem}-{width}.png", trials.worth(page, KEYWORDS))


if __name__ == "__main__":
    main()
