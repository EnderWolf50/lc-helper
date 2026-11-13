"""E.G.O gifts: their effects looked up by name, and the gifts a screen shows.

The data is assets/gifts.json (tools/sync_maalc.py build_gifts). Two screens are read, both by OCR in maalc's
regions (agent/actions.py): the gift choice after a battle (its "Refuse Gift" button; the cards' titles) and the
"E.G.O Gift GET!" window (its name plate). A line is a gift when it reads as a gift's whole English name.
"""

import json
import re
from dataclasses import dataclass
from functools import cache

from rapidfuzz import fuzz, process

from .events import KEYWORDS, ROMAN, has_cjk
from .paths import ASSETS

GIFT_CHOICE_HEADER = (870, 560, 160, 40)  # "Refuse Gift" (maalc GiftChoice node)
GIFT_CARDS = (100, 150, 1080, 410)  # every card's text on the gift choice (maalc GIFT_CARDS)
GIFT_GET_HEADER = (520, 160, 240, 40)  # "Gift GET" (maalc GiftGet node)
GET_NAME = (320, 405, 180, 80)  # the GET! window's name plate (maalc GET_NAME)
NAME_MATCH = 88  # an OCR'd line against a whole name, 0-100 (maalc run_start.match_name takes 0.9)


@cache
def book():
    return {int(i): {"id": int(i), **g} for i, g in
            json.loads((ASSETS / "gifts.json").read_text(encoding="utf-8"))["gifts"].items()}


def plain(text):
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("’", "'").replace("‘", "'"))


@cache
def _names():
    gifts = list(book().values())
    return gifts, [plain(g["en"]) for g in gifts], [g["zh"] or "" for g in gifts]


def search(query, limit=8):
    """Gifts whose name holds query best, best first: Chinese names for a Chinese query, else English."""
    query = query.strip()
    if len(query) < 2:
        return []
    gifts, en, zh = _names()
    hay, q = (zh, query) if has_cjk(query) else (en, plain(query))
    if not q:
        return []
    hits = process.extract(q, hay, scorer=fuzz.partial_ratio, limit=limit, score_cutoff=75)
    return [gifts[i] for _, _, i in hits]


def by_name(text):
    """The gift whose English name text reads as, or None."""
    gifts, en, _ = _names()
    q = plain(text)
    if len(q) < 4:
        return None
    hit = process.extractOne(q, en, scorer=fuzz.ratio, score_cutoff=NAME_MATCH)
    return gifts[hit[2]] if hit else None


def label(g):
    tier = f" {ROMAN[g['tier']]}" if g.get("tier") in ROMAN else ""
    return f"{g['zh'] or g['en']}（{KEYWORDS.get(g['keyword'], g['keyword'])}{tier}）"


@dataclass(frozen=True)
class GiftReading:
    """The gifts a screen shows: page "choice" (after a battle) or "get" (the GET! window), each with its box."""

    page: str
    gifts: tuple  # ((gift, (x, y, w, h)), ...), left to right
    source: str | None = None


def gift_page(image, read):
    """Which gift screen image is ("choice", "get"), or None. read(image, roi, only_rec) gives OCR lines."""
    if any("refuse" in t.lower() for t in read(image, GIFT_CHOICE_HEADER, True)):
        return "choice"
    if any("get" in t.lower() for t in read(image, GIFT_GET_HEADER, True)):
        return "get"
    return None


def read_gifts(image, page, lines):
    """The gifts on a gift screen. lines(image, roi) gives OCR (text, box) pairs."""
    found = []
    if page == "choice":
        for text, box in lines(image, GIFT_CARDS):
            if (g := by_name(text)) and g not in [f for f, _ in found]:
                found.append((g, box))
    elif page == "get":
        rows = lines(image, GET_NAME)
        whole = " ".join(t for t, _ in rows)  # a long name wraps on the plate
        g = by_name(whole) or next((by_name(t) for t, _ in rows if by_name(t)), None)
        if g:
            found.append((g, rows[0][1]))
    return GiftReading(page, tuple(sorted(found, key=lambda f: f[1][0])))
