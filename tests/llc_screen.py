"""LLC-looking screens for the tests: one of maalc's English captures with LLC's Simplified text painted over the
English text that lc-helper reads, so the real OCR path reads a Chinese screen.

Synthetic: the text is drawn with Microsoft YaHei through Qt, in the English text's boxes, sized to them. The game's
own Chinese font, sizes, wrapping and layout under LLC are not reproduced; no LLC capture exists to check them.
"""

import os
from functools import cache
from itertools import accumulate
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor, QGlyphRun, QImage, QPainter, QRawFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import event_skip, events, gifts, ocr, vision  # noqa: E402

FONT = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc"  # Simplified Chinese
STORY_SIZE = 18  # px: the English story text's height on maalc's captures
_app = []


@cache
def font(size):
    """Microsoft YaHei at size px, read from its file: a raw font is never added to Qt's font database, so the
    other tests' text keeps the fallback fonts it has without it."""
    _app.append(QApplication.instance() or QApplication([]))
    f = QRawFont(str(FONT), size)
    assert f.isValid(), f"no font at {FONT}"
    return f


def width(text, size):
    f = font(size)
    return sum(a.x() for a in f.advancesForGlyphIndexes(f.glyphIndexesForString(text)))


def glyphs(text, size, x, top, height):
    """text as a glyph run at size px, from x, its middle on the middle of the line top..top + height."""
    f = font(size)
    ids = f.glyphIndexesForString(text)
    baseline = top + (height + f.ascent() - f.descent()) / 2
    run = QGlyphRun()
    run.setRawFont(f)
    run.setGlyphIndexes(ids)
    run.setPositions([QPointF(x + dx, baseline) for dx in
                      accumulate((a.x() for a in f.advancesForGlyphIndexes(ids)), initial=0.0)][:len(ids)])
    return run


def colours(image, box, pad=4):
    """(background, text) colour of the text in box: the median of a ring around it, and the median of the tenth of
    its pixels that differ most from that."""
    x, y, w, h = box
    x0, y0 = max(x - pad, 0), max(y - pad, 0)
    outer = image[y0:y + h + pad, x0:x + w + pad].astype(int)
    ring = np.ones(outer.shape[:2], bool)
    ring[y - y0:y - y0 + h, x - x0:x - x0 + w] = False
    inner = image[y:y + h, x:x + w].reshape(-1, 3).astype(int)
    background = np.median(outer[ring], 0)
    far = np.abs(inner - background).sum(1)
    text = np.median(inner[far >= np.quantile(far, 0.9)], 0)
    return QColor(*map(int, background[::-1])), QColor(*map(int, text[::-1]))


def draw(image, jobs):
    """image (BGR) with each job (box, lines, size) done: box filled with the colour around it, then lines (top to
    bottom, size px, the text colour box had) drawn from its top left. Returns a new image."""
    plan = [(box, lines, size, *colours(image, box)) for box, lines, size in jobs]
    h, w = image.shape[:2]
    canvas = QImage(np.ascontiguousarray(image).tobytes(), w, h, 3 * w, QImage.Format.Format_BGR888).copy()
    p = QPainter(canvas)
    for (x, y, bw, bh), lines, size, background, text in plan:
        p.fillRect(x, y, bw, bh, background)
        p.setPen(text)
        step = round(size * 1.45) if len(lines) > 1 else bh
        for i, line in enumerate(lines):
            p.drawGlyphRun(QPointF(0, 0), glyphs(line, size, x, y + i * step, step))
    p.end()
    out = np.frombuffer(canvas.constBits(), np.uint8).reshape(h, canvas.bytesPerLine())[:, :3 * w]
    return out.reshape(h, w, 3).copy()


def fit(text, size, room):
    """The largest size up to size that keeps text on one line room px wide (the game shrinks no text; this keeps
    a long Chinese option inside its row)."""
    while size > 12 and width(text, size) > room:
        size -= 1
    return size


def wrap(text, size, room):
    """text broken into lines room px wide at size, paragraph by paragraph."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for c in paragraph:
            if width(line + c, size) > room:
                lines.append(line)
                line = ""
            line += c
        lines.append(line)
    return lines


def union(boxes):
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0


def line(box, text, right):
    """A job writing text over box's line, as large as box is high and no wider than up to right."""
    size = fit(text, round(box[3] * 0.85), right - box[0])
    return box, [text], size


def choices_page(image, event=None):
    """image, a Choices capture, as LLC shows it: the header 选项, the end of the story in the story box, and each
    option shown (with the game's hint under it) in Simplified. event is what to show: by default the capture's own,
    each option in its row; another event's options take the capture's rows top to bottom."""
    shown = events.read_screen(image)
    rows = events.option_rows(shown.event, shown.lines)
    if event is not None:
        rows = list(zip([o for o in event["options"] if o["text_cn"]], [box for _, box in rows]))
    event = event or shown.event
    jobs = [line(box, "选项", box[0] + box[2] + 60) for _, box in ocr.lines(image, vision.CHOICES_HEADER)]
    story = [box for _, box in ocr.lines(image, vision.EVENT_STORY)]
    if story:
        box = union(story)
        jobs.append((box, wrap(event["story_cn"], STORY_SIZE, box[2])[-(box[3] // round(STORY_SIZE * 1.45)):],
                     STORY_SIZE))
    right = vision.CHOICE_ROWS[0] + vision.CHOICE_ROWS[2] - 20
    jobs += [(box, [], 10) for _, box in shown.lines]
    for i, (option, box) in enumerate(rows):
        jobs.append(line(box, option["text_cn"], right))
        below = rows[i + 1][1][1] if i + 1 < len(rows) else 10 ** 4
        under = [b for _, b in shown.lines if box[1] < b[1] < below]
        if under and option["hint_cn"]:
            jobs.append(line(under[0], option["hint_cn"], right))
    return draw(image, jobs)


def read(image, roi, only_rec):
    return [t for t, _ in ocr.lines(image, roi, only_rec=only_rec)]


def gift_screen(image):
    """image, a gift choice or E.G.O Gift GET! capture, as LLC shows it: the Refuse Gift button or the window's title,
    each card's Acquire E.G.O Gift tag (LLC writes it as the GET! title, without the ！), and each gift's name (a
    card's title, the GET! name plate) in Simplified. The cards' effect text stays English: no line of LLC's own
    effect text reads as a gift's name (measured on LLC 2026110501), and Chinese here would only be this helper's
    guess at the game's wrapping."""
    page = gifts.gift_page(image, read)
    shown = gifts.read_gifts(image, page, ocr.lines).gifts
    jobs = []
    if page == "choice":
        jobs += [line(box, "拒绝饰品", box[0] + box[2] + 20) for _, box in ocr.lines(image, gifts.GIFT_CHOICE_HEADER)]
        jobs += [line(box, "获得E.G.O饰品", box[0] + box[2]) for text, box in ocr.lines(image, gifts.GIFT_CARDS)
                 if "acquire" in text.lower()]
        jobs += [line(box, g["cn"], box[0] + max(box[2], 150)) for g, box in shown]
    elif page == "get":
        jobs += [line(box, "获得E.G.O饰品！", box[0] + box[2] + 20) for _, box in ocr.lines(image, gifts.GIFT_GET_HEADER)]
        plate = [box for _, box in ocr.lines(image, gifts.GET_NAME)]
        jobs += [(box, [], 10) for box in plate]
        x, y, w, h = union(plate)
        jobs.append(line((x, y, w, plate[0][3]), shown[0][0]["cn"], x + max(w, 160)))
    return draw(image, jobs)


# LLC's text for the labels the story skipper reads (BattleUIText ab_event_next, choice_event_resume,
# ab_event_decision, selection, choice_personality).
LLC_BUTTONS = {"proceed": "继续", "continue": "继续", "commence": "进行判定"}
LLC_CHOICES = "选项"
LLC_CHECK = "选择一位罪人来进行判定："
PROMPT = (850, 290, 330, 60)  # a check's English prompt, both its lines


def event_page(image):
    """image, an event capture, as LLC shows it to the story skipper: the bottom-right button's label (SKIP stays: no
    LLC text for it was found), the Choices header, and a check's prompt (on one line, where the English one starts)
    in Simplified."""
    jobs = []
    for text, box in ocr.lines(image, event_skip.EVENT_BUTTON_LABEL):
        if cn := LLC_BUTTONS.get(text.lower()):
            jobs.append(line(box, cn, box[0] + box[2]))
    jobs += [line(box, LLC_CHOICES, box[0] + box[2] + 60) for text, box in ocr.lines(image, vision.CHOICES_HEADER)
             if "choice" in text.lower()]
    prompt = ocr.lines(image, PROMPT)
    if any("choose a character" in text.lower() for text, _ in prompt):
        jobs += [(box, [], 10) for _, box in prompt]
        jobs.append(line(prompt[0][1], LLC_CHECK, prompt[0][1][0] + 330))
    return draw(image, jobs)
