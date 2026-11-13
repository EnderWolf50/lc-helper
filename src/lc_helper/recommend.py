"""Which event option to take for a team built on one keyword: maalc's order (agent/rewards.py _rank and choice_plan,
from AALC, maalc #233), with no wanted-gift list.

Tiers, best first: 0 a "???" random gain, 1 a direct gain, 2 a check that gives a gift on a pass, 3 a gift depending on
a following choice, 4 the rest (a battle, a gift only a failed check gives, nothing). Inside a tier an option giving
a gift of the main keyword goes first, then the screen order. The keyword never lifts an option across tiers.
"""

import re

from .events import KEYWORDS

TIER_TEXT = {0: "結果未知（???）的隨機獎勵", 1: "直接獲得飾品", 2: "判定通過獲得飾品", 3: "依後續選擇獲得飾品", 4: "其他"}
CHOICES = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt"]


def rank(option, keyword):
    """(tier, False when a gift of keyword is in it) of a table option: sorts best first."""
    kind, hint = option["kind"], option.get("hint") or ""
    main = any(k == keyword for k, _ in option.get("gift_keywords", ()))
    if kind == "direct" or (kind == "random" and "???" in hint):
        return (0 if kind == "random" else 1), not main
    if kind in ("check", "followup"):  # AALC matches "Advantage check" before "Gain ... depending on"
        if re.search(r"\bcheck\b", hint, re.I):
            return 2, not main
        if re.search(r"\bdepending on\b", hint, re.I):
            return 3, not main
    return 4, True


def best(event, keyword, closed=()):
    """(option, why) to take on event's page for a keyword team, or None: no keyword, no event, or all closed.

    closed are option texts that cannot be taken (grey on screen: answered in an earlier round)."""
    if not keyword or not event:
        return None
    options = [o for o in event["options"] if o["text"] and o["text"] not in closed]
    if not options:
        return None
    pick = min(options, key=lambda o: (*rank(o, keyword), event["options"].index(o)))
    tier, not_main = rank(pick, keyword)
    why = TIER_TEXT[tier] + ("" if not_main else f"，有{KEYWORDS.get(keyword, keyword)}飾品")
    return pick, why
