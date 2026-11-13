"""Mirror Dungeon events: find one by its text (typed, or read off the screen) and say what each option does.

The data is assets/events.json (tools/sync_maalc.py): maalc's event table with the full English and Chinese text.
A screen is read in the game's English or in LLC's Simplified Chinese (Script): each against its own text.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from functools import cache

from rapidfuzz import fuzz, process

from . import labels
from .paths import ASSETS

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
CJK = "㐀-鿿"
# Chinese characters, letters and digits of a Simplified story's end that key it, as maalc keys the English by its
# last 60 letters and digits. From 20 to 60 only 971098/971099 and 971105/971107 come together (English also
# brings 90109505/90109506, whose LLC options differ); 15 adds 862901/862902 (2026-11-14, LLC 2026110501).
CN_KEY = 30


@dataclass(frozen=True)
class Effect:
    """One line of what an option does: when it applies (a label) and what happens."""

    when: str
    what: str


def key(text):
    """Letters and digits, lower case: how the table keys a story (its last 60)."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def key_cn(text):
    """Chinese characters, letters and digits, lower case: key over LLC's Simplified text."""
    return re.sub(f"[^a-z0-9{CJK}]", "", text.lower())


def has_cjk(text):
    return re.search(f"[{CJK}]", text) is not None


def reads_chinese(text):
    """Whether OCR'd text is LLC's Chinese: more Chinese characters than Latin letters. Not has_cjk: OCR of an
    English page may slip in a Chinese character, and LLC writes E.G.O and SP in Latin."""
    return len(re.findall(f"[{CJK}]", text)) > len(re.findall(r"[A-Za-z]", text))


@dataclass(frozen=True)
class Script:
    """How a page read in one script is looked up: the event's fields to compare it with, and how a text is folded
    for comparing. ENGLISH is maalc's; CHINESE reads LLC's Simplified text."""

    key: str  # the event's field holding its story key
    text: str  # the option's fields: its text, and the game's hint under it
    hint: str
    keyed: Callable[[str], str]  # a text as candidates compares it
    shortest: int  # an OCR'd option shorter than this once keyed is noise to candidates
    fold: Callable[[str], str]  # a line and an option's text as option_rows compares them
    shortest_line: int  # an OCR'd line shorter than this is noise to option_rows


ENGLISH = Script("key", "text", "hint", key, 4, str.lower, 3)
CHINESE = Script("key_cn", "text_cn", "hint_cn", key_cn, 2, key_cn, 2)


def script(text):
    return CHINESE if reads_chinese(text) else ENGLISH


@cache
def book():
    data = json.loads((ASSETS / "events.json").read_text(encoding="utf-8"))
    for e in data["events"]:
        e["key_cn"] = key_cn(e["story_cn"])[-CN_KEY:]
    return data


@cache
def by_id():
    return {e["id"]: e for e in book()["events"]}


@cache
def _haystacks():
    en, zh = [], []
    for e in book()["events"]:
        en.append(" ".join([e["story"]] + [f"{o['text']} {o['hint']}" for o in e["options"]]).lower())
        # Traditional and LLC's Simplified both: a player on an LLC client types what the game shows.
        zh.append(" ".join([e["story_zh"], e.get("story_cn") or ""]
                           + [f"{o['text_zh']} {o['hint_zh']} {o.get('text_cn', '')} {o.get('hint_cn', '')}"
                              for o in e["options"]]))
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
    A page that reads as Chinese is matched against LLC's Simplified text (Script), any other against the English.
    """
    sc = script(" ".join([story, *options]))
    s = sc.keyed(story)
    shown = [sc.keyed(o) for o in options if len(sc.keyed(o)) >= sc.shortest]
    events = [e for e in book()["events"] if not e["page"]]

    def score(e):
        texts = [sc.keyed(t) for o in e["options"] for t in (o[sc.text], o[sc.hint]) if sc.keyed(t)]
        return sum(max(fragment(o, t) for t in texts) for o in shown) / len(shown) if texts and shown else 0

    if s:
        hits = [e for e in events if SequenceMatcher(None, e[sc.key], s[-len(e[sc.key]):]).ratio() >= STORY_MATCH]
        longest = max((len(e[sc.key]) for e in hits), default=0)
        hits = [e for e in hits if len(e[sc.key]) == longest]
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
    lines: tuple = ()  # the option list's OCR lines as (text, (x, y, w, h)) in 1280x720 pixels
    source: str | None = None  # the device address it was read from (device.PC for the PC client)
    closed: tuple[str, ...] = ()  # option texts shown grey: answered in an earlier round, a tap does nothing
    watched: bool = False  # the worker watches the page it was read from and tells its leaving (page_left)


def on_choices_page(image):
    """Whether image is an event's Choices page (the header reads Choices, or LLC's 选项): the page whose story box
    shows the end."""
    from . import ocr, vision

    return labels.shows([t for t, _ in ocr.lines(image, vision.CHOICES_HEADER, only_rec=True)], "choices")


def read_screen(image):
    """Read the event page in image: its story box and option list, matched against the table."""
    from . import ocr, vision

    story = " ".join(t for t, _ in ocr.lines(image, vision.EVENT_STORY))
    lines = tuple(ocr.lines(image, vision.CHOICE_ROWS))
    options = tuple(t for t, _ in lines)
    found = candidates(story, options)
    event = found[0] if found else None
    closed = tuple(o["text"] for o, box in option_rows(event, lines) if not choice_open(image, box[1] + box[3] // 2))
    return Reading(event, story, options, tuple(found[1:]), lines, closed=closed)


def choice_open(image, y):
    """Whether the option whose first line is at y can be taken: its frame left of the text is red-brown (maalc
    rewards.choice_open, live #34: an answer taken in an earlier round turns grey, red - blue ~0)."""
    b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)
    return bool(r - b > 10)


def option_rows(event, lines):
    """Each of event's options shown in lines, as (option, box of its first line), top to bottom.

    An option's first line is its text's start (a long option wraps); the lines under it, its wrap and the game's
    hint, start otherwise. Options scrolled out of the list have no line and are left out. Chinese lines are compared
    with the options' Simplified text (Script). Of two lines that start an option alike, the one closer to the whole
    option is its: a shorter option can be another's start (971117's 说我们没有眼球。).
    """
    sc = script(" ".join(t for t, _ in lines))
    folded = [(sc.fold(t), box) for t, box in lines if len(t) >= sc.shortest_line]
    rows = []
    for option in (event or {}).get("options", []):
        text = sc.fold(option[sc.text])
        if not text:
            continue
        scored = [(fuzz.ratio(t, text[:len(t)]), fuzz.ratio(t, text), box) for t, box in folded if t]
        score, _, box = max(scored, default=(0, 0, None))
        if score >= 85:
            rows.append((option, box))
    return sorted(rows, key=lambda r: r[1][1])


def short_effect(option, limit=46):
    """An option's effects in one line for the overlay: the effects lines joined, cut at limit characters."""
    text = "；".join(f"{e.when} {e.what}" for e in effects(option, follow=False)) or option.get("hint_zh") \
        or option.get("hint") or ("進入後續頁" if option.get("next") else "沒有記錄效果")
    return text if len(text) <= limit else text[:limit - 1] + "…"


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


def branch_when(b):
    if "p" in b:
        return f"機率 {b['p'] * 100:g}%"
    if "p_per_pick" in b:
        return f"機率每選一次 {b['p_per_pick'] * 100:+g}%"
    return condition_text(b["if"])


def branch_text(b):
    return branch_when(b), "、".join(get_text(g) for g in b["gets"] if g[0] != "next") or "沒事發生"


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


SINS = ("暴怒", "色慾", "怠惰", "暴食", "憂鬱", "傲慢", "嫉妒")
CHECK = re.compile(f"((?:{'|'.join(SINS)})(?:、(?:{'|'.join(SINS)}))*)優勢判定")
# How a gift of gift_ids comes, said short beside it on the game, and whether it is a check's pass or fail.
OUTCOME_WHEN = {"direct": ("獲得", ""), "direct_random": ("機率獲得", ""), "check_pass": ("成功", "pass"),
                "check_fail": ("失敗", "fail"), "win_battle": ("勝利後", ""), "later_direct": ("下一頁", ""),
                "later_direct_random": ("下一頁機率", ""), "later_win_battle": ("下一頁勝利後", "")}


def check_sins(option):
    """The sins of an option's check, from the game's hint ("傲慢、嫉妒優勢判定 ..."): () when it has none."""
    m = CHECK.search(option.get("hint_zh") or "")
    return tuple(m[1].split("、")) if m else ()


@dataclass(frozen=True)
class Outcome:
    """One way an option can end, for the hints on the game: when, whether that is a check passed or failed, the
    gifts it gives (gift id, and "勝利後" for one won in battle), and the table's other gets entries (hp, sp, cost...)."""

    when: str
    tone: str = ""  # "pass", "fail" or ""
    gifts: tuple[tuple[int, str], ...] = ()
    gets: tuple[tuple, ...] = ()


def outcomes(option):
    """What an option does, as effects() says it, kept apart for drawing: one outcome per way it comes about, a
    check passed first and failed last."""
    odds, fail = option.get("odds", []), option.get("fail", [])
    in_branches = {g[1] for b in odds + fail for g in b["gets"] if g[0] in ("gift", "win_gift")}
    by_how = {}
    for gid, how in option.get("gift_ids", []):
        if gid not in in_branches:
            by_how.setdefault(how, []).append((gid, ""))
    found = [Outcome(*OUTCOME_WHEN.get(how, (how, "")), tuple(ids)) for how, ids in by_how.items()]
    for b, tone in [(b, "") for b in odds] + [(b, "fail") for b in fail]:
        when = branch_when(b)
        if tone:
            when = "失敗" if when == "機率 100%" else f"失敗，{when}"
        gifts = tuple((g[1], "勝利後" if g[0] == "win_gift" else "") for g in b["gets"] if g[0] in ("gift", "win_gift"))
        found.append(Outcome(when, tone, gifts, tuple(tuple(g) for g in b["gets"] if g[0] not in ("gift", "win_gift", "next"))))
    merged = {}  # a failed check's gift and its costs are one outcome
    for f in found:
        k = (f.when, f.tone)
        merged[k] = replace(merged[k], gifts=merged[k].gifts + f.gifts, gets=merged[k].gets + f.gets) if k in merged else f
    return sorted(merged.values(), key=lambda f: ("pass", "", "fail").index(f.tone))
