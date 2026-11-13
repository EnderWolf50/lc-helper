"""Which event option to take for a team built on a few keywords, in the player's order: maalc's order
(agent/rewards.py _rank and choice_plan, from AALC, maalc #233), with no wanted-gift list.

Tiers, best first: 0 a "???" random gain, 1 a direct gain, 2 a check that gives a gift on a pass, 3 a gift depending on
a following choice, 4 the rest (a battle, a gift only a failed check gives, nothing). Inside a tier an option giving a
gift of the earliest keyword in the list goes first, then the screen order. A keyword never lifts an option across
tiers.
"""

import re

from .events import KEYWORDS

TIER_TEXT = {0: "結果未知（???）的隨機獎勵", 1: "直接獲得飾品", 2: "判定通過獲得飾品", 3: "依後續選擇獲得飾品", 4: "其他"}
CHOICES = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt"]


def rank(option, keywords):
    """(tier, the place in keywords of the earliest one a gift in it has, len(keywords) for none) of a table option:
    sorts best first."""
    kind, hint = option["kind"], option.get("hint") or ""
    given = {k for k, _ in option.get("gift_keywords", ())}
    place = min((i for i, k in enumerate(keywords) if k in given), default=len(keywords))
    if kind == "direct" or (kind == "random" and "???" in hint):
        return (0 if kind == "random" else 1), place
    if kind in ("check", "followup"):  # AALC matches "Advantage check" before "Gain ... depending on"
        if re.search(r"\bcheck\b", hint, re.I):
            return 2, place
        if re.search(r"\bdepending on\b", hint, re.I):
            return 3, place
    return 4, len(keywords)


def best(event, keywords, closed=()):
    """(option, why) to take on event's page for a team of keywords, first one first, or None: no keyword, no event,
    or all closed.

    closed are option texts that cannot be taken (grey on screen: answered in an earlier round)."""
    if not keywords or not event:
        return None
    options = [o for o in event["options"] if o["text"] and o["text"] not in closed]
    if not options:
        return None
    pick = min(options, key=lambda o: (*rank(o, keywords), event["options"].index(o)))
    tier, place = rank(pick, keywords)
    why = TIER_TEXT[tier] + (f"，有{KEYWORDS.get(keywords[place], keywords[place])}飾品" if place < len(keywords) else "")
    return pick, why
