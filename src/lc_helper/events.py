"""Mirror Dungeon events: find one by its text (typed, or read off the screen) and say what each option does.

The data is assets/events.json (tools/sync_maalc.py): maalc's event table with the full English and Chinese text.
"""

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache

from rapidfuzz import fuzz, process

from .vision import ASSETS

KEYWORDS = {"Burn": "燒傷", "Bleed": "流血", "Tremor": "震顫", "Rupture": "破裂", "Sinking": "沉淪", "Poise": "呼吸",
            "Charge": "充能", "Slash": "斬擊", "Pierce": "突刺", "Blunt": "打擊", "Keywordless": "無體系"}
HOW = {"direct": "直接獲得", "direct_random": "機率獲得", "check_pass": "判定成功獲得", "check_fail": "判定失敗獲得",
       "win_battle": "戰鬥勝利獲得", "later_direct": "下一頁獲得", "later_direct_random": "下一頁機率獲得",
       "later_win_battle": "下一頁戰鬥勝利獲得"}
KIND = {"direct": "直接", "random": "隨機", "check": "判定", "check_fail_gift": "判定", "followup": "後續頁",
        "battle": "戰鬥", "check_other": "判定", "followup_other": "後續頁", "other": "其他"}
TARGETS = {"ChosenPersonality": "判定的罪人", "EveryAlly": "全體", "NotAffectedAlly": "其餘罪人",
           "LowestMpAlly_1": "SP 最低的 1 人", "RandomAlly_3": "隨機 3 人", "Donquixote": "唐吉訶德"}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
STATS = {"hp": "HP", "sp": "SP", "hp%": "HP", "sp%": "SP"}
CONDITIONS = {"Failed": "失敗次數", "MpAverage": "全隊平均 SP"}
STORY_MATCH = 0.85  # maalc rewards.match_event: OCR'd story end vs the table's key
OPTION_MATCH = 80  # rapidfuzz ratio (0-100) an OCR'd option needs to count as one of an event's options


@dataclass(frozen=True)
class Effect:
    """One line of what an option does: when it applies (a label) and what happens."""

    when: str
    what: str


def key(text):
    """Letters and digits, lower case: how the table keys a story (its last 60)."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def has_cjk(text):
    return re.search(r"[㐀-鿿]", text) is not None


@cache
def book():
    return json.loads((ASSETS / "events.json").read_text(encoding="utf-8"))


@cache
def by_id():
    return {e["id"]: e for e in book()["events"]}


@cache
def _haystacks():
    en, zh = [], []
    for e in book()["events"]:
        en.append(" ".join([e["story"]] + [f"{o['text']} {o['hint']}" for o in e["options"]]).lower())
        zh.append(" ".join([e["story_zh"]] + [f"{o['text_zh']} {o['hint_zh']}" for o in e["options"]]))
    return en, zh


def search(query, limit=8):
    """Events whose text holds query best, best first: Chinese against the Chinese text, else the English."""
    query = query.strip()
    if len(query) < 2:
        return []
    en, zh = _haystacks()
    hay = zh if has_cjk(query) else en
    q = query if has_cjk(query) else query.lower()
    hits = process.extract(q, hay, scorer=fuzz.partial_ratio, limit=limit, score_cutoff=60)
    events = book()["events"]
    return [events[i] for _, _, i in hits]


def fragment(line, text):
    """How well an OCR'd line reads as text or a piece of it (a wrapped hint shows a line at a time), 0-100."""
    return fuzz.partial_ratio(line, text) if len(line) <= len(text) else fuzz.ratio(line, text)


def candidates(story, options=()):
    """The events an event page may show, best first, from its OCR'd story box and option texts; [] when none fits.

    The story box shows a long story's end, so it is matched against the table's key, the story's last 60 letters
    and digits (maalc rewards.match_event); the longest matching key wins. Several pages share a key (13 events, some
    only "What will you do?"): the options read on screen rank those. With no story match, the options alone pick.
    More than one event comes back only when the screen cannot tell them apart (971098 and 971099 read the same).
    """
    s = key(story)
    shown = [key(o) for o in options if len(key(o)) >= 4]
    events = [e for e in book()["events"] if not e["page"]]

    def score(e):
        texts = [key(t) for o in e["options"] for t in (o["text"], o["hint"]) if key(t)]
        return sum(max(fragment(o, t) for t in texts) for o in shown) / len(shown) if texts and shown else 0

    if s:
        hits = [e for e in events if SequenceMatcher(None, e["key"], s[-len(e["key"]):]).ratio() >= STORY_MATCH]
        longest = max((len(e["key"]) for e in hits), default=0)
        hits = [e for e in hits if len(e["key"]) == longest]
        if hits:
            best = max(map(score, hits))
            return [e for e in hits if score(e) == best]
    if not shown:
        return []
    scored = sorted(((score(e), i) for i, e in enumerate(events)), reverse=True)
    best = scored[0][0]
    return [events[i] for sc, i in sorted(scored, key=lambda t: t[1]) if sc == best] if best >= OPTION_MATCH else []


def match_screen(story, options=()):
    """The likeliest event for an event page, or None (candidates)."""
    found = candidates(story, options)
    return found[0] if found else None


@dataclass(frozen=True)
class Reading:
    """What an event page shows: the event found (None when none fits) and the text read to find it."""

    event: dict | None
    story: str
    options: tuple[str, ...]
    others: tuple[dict, ...] = ()  # events the screen reads the same as event


def on_choices_page(image):
    """Whether image is an event's Choices page (the header reads Choices): the page whose story box shows the end."""
    from . import ocr, vision

    return any("choice" in t.lower() for t, _ in ocr.lines(image, vision.CHOICES_HEADER, only_rec=True))


def read_screen(image):
    """Read the event page in image: its story box and option list, matched against the table."""
    from . import ocr, vision

    story = " ".join(t for t, _ in ocr.lines(image, vision.EVENT_STORY))
    options = tuple(t for t, _ in ocr.lines(image, vision.CHOICE_ROWS))
    found = candidates(story, options)
    return Reading(found[0] if found else None, story, options, tuple(found[1:]))


def gift_name(gift_id):
    g = book()["gifts"].get(str(gift_id))
    if not g:
        return f"飾品 {gift_id}"
    tier = f" {ROMAN[g['tier']]}" if g.get("tier") in ROMAN else ""
    return f"「{g['zh'] or g['en']}」（{KEYWORDS.get(g['keyword'], g['keyword'])}{tier}）"


def _number(x):
    return f"{x:+g}" if isinstance(x, (int, float)) else str(x)


def get_text(g):
    """One gets entry of the table (docs: maalc spec 05 section 7) in words."""
    what = g[0]
    if what in STATS:
        amount = "補滿" if g[1] == "max" else _number(g[1]) + ("%" if what.endswith("%") else "")
        target = f"（{TARGETS.get(g[2], g[2])}）" if len(g) > 2 else ""
        return f"{STATS[what]} {amount}{target}"
    if what == "cost":
        return f"Cost {_number(g[1])}"
    if what == "gift":
        return f"獲得 {gift_name(g[1])}"
    if what == "win_gift":
        return f"戰鬥勝利獲得 {gift_name(g[1])}"
    if what in ("buff", "win_buff"):
        return "戰鬥勝利獲得隱藏的戰鬥增益" if what == "win_buff" else "獲得隱藏的戰鬥增益"
    if what == "battle":
        return "開始戰鬥"
    if what == "next":
        return "進入後續頁"
    return " ".join(map(str, g))


def condition_text(cond):
    name, _, rest = cond.partition("_")
    m = re.fullmatch(r"(Under|NotLessThan)(-?\d+)", rest)
    if not m:
        return cond
    return f"{CONDITIONS.get(name, name)} {'<' if m[1] == 'Under' else '≥'} {m[2]}"


def branch_text(b):
    gets = "、".join(get_text(g) for g in b["gets"] if g[0] != "next") or "沒事發生"
    if "p" in b:
        return f"機率 {b['p'] * 100:g}%", gets
    if "p_per_pick" in b:
        return f"機率每選一次 {b['p_per_pick'] * 100:+g}%", gets
    return condition_text(b["if"]), gets


def effects(option, follow=True):
    """What an option does, as (when, what) lines: its gifts, its random outcomes, what a failed check costs, and
    with follow, one line per option of the follow-up page it leads to (one page deep: some pages lead to themselves)."""
    odds = option.get("odds", [])
    in_branches = {g[1] for b in odds + option.get("fail", []) for g in b["gets"] if g[0] in ("gift", "win_gift")}
    # A gift a branch names is said there, with its odds or its battle; a second line would contradict it.
    lines = [Effect(HOW.get(how, how), gift_name(gid)) for gid, how in option.get("gift_ids", []) if gid not in in_branches]
    lines += [Effect(*branch_text(b)) for b in odds]
    for b in option.get("fail", []):
        when, what = branch_text(b)
        lines.append(Effect("判定失敗" if when == "機率 100%" else f"判定失敗，{when}", what))
    for page_id in option.get("next", []) if follow else []:
        page = by_id().get(page_id)
        for o in (page or {}).get("options", []):
            if o["text"]:
                sub = "；".join(f"{e.when}：{e.what}" for e in effects(o, follow=False)) or o["hint"] or "沒有記錄效果"
                lines.append(Effect(f"後續「{o['text_zh'] or o['text']}」", sub))
    return lines


def kind_text(option):
    return KIND.get(option["kind"], option["kind"])
