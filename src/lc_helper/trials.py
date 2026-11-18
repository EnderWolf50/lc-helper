"""Mirror Dungeon trials (苦難, the game's Trials): what each card of the gift choice after a floor's boss would mount on
the enemies, read off the screen, and how much each card is worth taking.

After a floor's boss the gift choice pairs each E.G.O gift with a Mounting Trial that every later enemy carries: an
Enemy Level Up +N badge and the trial's effects. Hard takes two cards (Select 0/2), Normal one; Refuse Gift hands out
random trials instead. The data is the resource package's trials.yaml and trial_text.json (gamedata.trials): maalc's
trial table, whose score is in pt (1 pt = the enemies' Clash Power +1), with LLC's Chinese name and text. Reading and
scoring are maalc's (agent/event_actions.py trial_card and PickGift, agent/rewards.py read_trial and scores, docs/spec/03 section 12): a
card is worth its gift's score less its trial's burden, the trial's score and 0.36 pt per Enemy Level Up; its gift
scores 3 for a keyword of the team (here the recommended keywords), 2 for another, 0 held already, 0.5 more per tier
above I but held.
"""

import re
from collections import Counter
from dataclasses import dataclass, replace
from functools import cache

from rapidfuzz import fuzz, process

from . import gamedata, labels
from .events import has_cjk, key_cn
from .gifts import GIFT_CARDS, plain

TRIAL_HALF = (-125, 438, 250, 105)  # around a card's centre x: its trial half, badge to effect line (maalc)
TRIAL_NAME_FOOT = 470  # a trial name's box starts above it, its effect line's below (maalc)
TRIAL_BADGE_X = -60  # the badge's "+N" starts further left of the centre than this, the name less (maalc)
TAB_TO_CENTRE = 114  # the Acquire E.G.O Gift tab's right edge, right of its card's centre (maalc)
TAG_FOOT = 178  # the Owned and Acquire tags sit over a card's top edge, above the title (BossGiftTrialsFloor3.png: y 152-170)
GIFT_COUNT = (1060, 555, 160, 50)  # "Select 0/2"; "Select" alone on a page that takes one card (maalc)
UNREAD_LEVELS = 2  # an unread badge counts as +2: only +1 and +2 are seen (maalc rewards.UNREAD_LEVELS)
GIFT_SCORES = {"main": 3, "other": 2, "owned": 0}
TIER_STEP = 0.5
NAME_MATCH, CN_NAME_MATCH = 88, 75  # as gifts.py's names
NUMBER = r"\s*(\d+(?:\.\d+)?)"
# What a trial adds to the enemies, as its effect line shows it (the effects keys of trials.yaml): maalc's English, and
# LLC's Simplified, every phrase of the 105 trials' desc_cn (tests/test_trials.py). Minus Coin Power comes with Plus
# Coin Power, the same number: coin is the plus one.
EFFECTS = {
    "offense": (r"offense level\s*\+" + NUMBER, r"攻击等级\s*\+" + NUMBER),
    "defense": (r"defense level\s*\+" + NUMBER, r"防御等级\s*\+" + NUMBER),
    "hp": (r"(?<!boss )max hp\s*\+" + NUMBER + "%", r"(?<!遭遇战)体力上限\s*\+" + NUMBER + "%"),
    "boss_hp": (r"boss max hp\s*\+" + NUMBER + "%", r"头目遭遇战体力上限\s*\+" + NUMBER + "%"),
    "clash": (r"clash power\s*\+" + NUMBER, r"拼点威力\s*\+" + NUMBER),
    "final": (r"(?<!skill )final power\s*\+" + NUMBER, r"(?<!技能)最终威力\s*\+" + NUMBER),
    "base": (r"base power\s*\+" + NUMBER, r"基础威力\s*\+" + NUMBER),
    "coin": (r"plus coin power\s*\+" + NUMBER, r"加算硬币威力\s*\+" + NUMBER),
    "taken": (r"damage taken\s*[-−–]" + NUMBER + "%", r"受到的伤害\s*[-−–]" + NUMBER + "%"),
    "dealt": (r"damage dealt\s*\+" + NUMBER + "%", r"造成的伤害\s*\+" + NUMBER + "%"),
    "defskill": (r"defense skill final power\s*\+" + NUMBER, r"守备技能最终威力\s*\+" + NUMBER),
}


@cache
def book():
    """{"model": maalc's scoring model, "trials": {English name: its entry}}."""
    return gamedata.trials()


def parse_effects(text):
    """{effect: number} an effect line reads as, in English or LLC's Chinese; an effect without its number is left out."""
    t = " ".join(text.lower().split())
    return {k: float(m[1]) for k, ways in EFFECTS.items() for p in ways if (m := re.search(p, t))}


def numeral(name):
    m = re.search(r"(?<![a-z])([ivx]+)\s*$", name.lower())
    return m[1] if m else ""


def by_name(text, trials):
    """The trial (its English name) whose name text reads as: LLC's Simplified for a read with a Chinese character,
    else English; found whole, else by the gifts' match thresholds."""
    if has_cjk(text):
        names, q, cutoff = {key_cn(t["cn"]): n for n, t in trials.items() if t["cn"]}, key_cn(text), CN_NAME_MATCH
    else:
        names, q, cutoff = {plain(n): n for n in trials}, plain(text), NAME_MATCH
    if not q:
        return None
    if q in names:
        return names[q]
    hit = process.extractOne(q, list(names), scorer=fuzz.ratio, score_cutoff=cutoff)
    return names[hit[0]] if hit else None


def read_trial(name, line, trials):
    """(trial, how) a card shows, from its name's and its effect line's OCR (maalc rewards.read_trial). The effect line
    goes first ("effects"): the trial with the same effects whose numbers agree most, unless two agree as much. Then the
    name ("name"), dropped when its numeral is not the one read. Neither: (None, None)."""
    read = parse_effects(line)
    alike = sorted(((sum(abs(t["effects"][k] - v) < 1e-6 for k, v in read.items()), n)
                    for n, t in trials.items() if read and set(t["effects"]) == set(read)), reverse=True)
    if alike and alike[0][0] and (len(alike) == 1 or alike[1][0] < alike[0][0]):
        return alike[0][1], "effects"
    found = by_name(name, trials)
    if found and numeral(trials[found]["cn"] if has_cjk(name) else found) == numeral(name):
        return found, "name"
    return None, None


@dataclass(frozen=True)
class Card:
    """One card of the post-boss gift choice."""

    x: int  # its centre, in the game's 1280x720 pixels
    gift: dict | None  # gifts.book()'s entry; None when its title was not read as a gift
    owned: bool
    trial: str | None  # its trial's English name (its key in the book); None when not read
    level: int | None  # Enemy Level Up +N; None when the badge was not read
    how: str | None = None  # how the trial was told: "effects", "name" or None


@dataclass(frozen=True)
class TrialPage:
    cards: tuple[Card, ...]  # left to right
    picks: int  # how many cards the page takes: 2 on Hard, 1 on Normal
    source: str | None = None


def read_page(image, lines, gift_reading):
    """The post-boss gift choice in image: each card's gift and trial, and how many cards it takes; None for a gift
    choice without trials (after a fight). lines(image, roi) gives OCR (text, box) pairs; gift_reading is
    gifts.read_gifts' reading of the same image (its gifts' boxes are the cards' titles)."""
    found = lines(image, GIFT_CARDS)
    if not any(labels.shows([t], "mounting") for t, _ in found):
        return None
    # a gift's effect may write the tag's word too (LLC's 获得): only a tag over the card's top edge is one
    centres = sorted(x + w - TAB_TO_CENTRE for t, (x, y, w, h) in found if labels.shows([t], "acquire") and y < TAG_FOOT)
    if not centres:  # the tabs not read: the titles are centred on the cards
        centres = sorted(round(b[0] + b[2] / 2) for _, b in gift_reading.gifts)
    trials = book()["trials"]
    cards = []
    for x in centres:
        gift = next((g for g, b in gift_reading.gifts if abs(b[0] + b[2] / 2 - x) < 130), None)
        owned = any(labels.shows([t], "owned") and b[1] < TAG_FOOT and abs(b[0] + b[2] / 2 - x) < 130
                    for t, b in found)
        level, name, line = trial_half(image, lines, x)
        trial, how = read_trial(name, line, trials)
        cards.append(Card(x, gift, owned, trial, level, how))
    count = re.search(r"\d\s*/\s*(\d)", " ".join(t for t, _ in lines(image, GIFT_COUNT)))
    return TrialPage(tuple(cards), int(count[1]) if count else 1)


def trial_half(image, lines, x):
    """(Enemy Level Up N or None, the trial name's OCR, its effect line's OCR) of the card centred at x: one OCR over its
    trial half, a wrapped effect line joined top to bottom (maalc event_actions.trial_card)."""
    dx, y, w, h = TRIAL_HALF
    level, name, line = None, [], []
    for t, (bx, by, _, _) in sorted(lines(image, (x + dx, y, w, h)), key=lambda r: (r[1][1], r[1][0])):
        badge = re.fullmatch(r"\+\s*(\d)", t.strip())
        if badge and bx < x + TRIAL_BADGE_X:
            level = int(badge[1])
        elif by >= TRIAL_NAME_FOOT:
            line.append(t)
        elif len(plain(t)) >= 3 or len(key_cn(t)) >= 2:
            if not labels.shows([t], "mounting"):
                name.append(t)
    return level, " ".join(name), "".join(line) if has_cjk("".join(line)) else " ".join(line)


@dataclass(frozen=True)
class Worth:
    """What a card is worth taking: its gift's score less its trial's burden, in pt."""

    card: Card
    gift: float
    burden: float
    total: float
    rank: int  # 1: the best card of the page
    pick: bool  # among the cards the page takes


def gift_score(card, keywords):
    if card.owned:
        return GIFT_SCORES["owned"]
    g = card.gift or {}
    main = g.get("keyword") in keywords
    return GIFT_SCORES["main" if main else "other"] + TIER_STEP * ((g.get("tier") or 1) - 1)


def burden(card, pool):
    """A card's trial cost in pt: its score (past maalc's early pools, every Coin Power unit at coin_over: lc-helper does
    not count the run's coins) and the model's level per Enemy Level Up; a trial not read costs its pool's worst."""
    table = book()
    model, trials = table["model"], table["trials"]

    def score(t):
        coin = t["effects"].get("coin", 0) if t["pool"] > model["early_pools"] else 0
        return t["score"] + (model["coin_over"] - model["coin_in"]) * coin

    worst = max(score(t) for t in trials.values() if pool is None or t["pool"] == pool)
    own = score(trials[card.trial]) if card.trial else worst
    return own + model["level"] * (UNREAD_LEVELS if card.level is None else card.level)


def worth(page, keywords):
    """Each card's worth, left to right, ranked best first: by total, then the lighter trial, then the left one (maalc);
    the page's picks best ones are its picks. The pool is the one most of the read trials come from."""
    pools = Counter(book()["trials"][c.trial]["pool"] for c in page.cards if c.trial)
    pool = pools.most_common(1)[0][0] if pools else None
    rows = []
    for c in page.cards:
        gift, cost = gift_score(c, keywords), burden(c, pool)
        rows.append(Worth(c, gift, cost, gift - cost, 0, False))
    order = sorted(range(len(rows)), key=lambda i: (-rows[i].total, rows[i].burden, i))
    for rank, i in enumerate(order, 1):
        rows[i] = replace(rows[i], rank=rank, pick=rank <= page.picks)
    return rows
