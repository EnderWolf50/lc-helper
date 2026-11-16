"""The event, gift and trial books lc-helper reads, joined from the resource package's data/ files.

The package keeps structure and text apart. Structure (an option's kind, odds, gift ids, next pages; a gift's recipe;
a trial's effects and score) is in event_table.json, gift_recipes.json and trials.yaml; the text, in English, LLC's
Simplified original (`_cn`, `cn`) and the Traditional converted from it (`_zh`, `zh`), is in event_text.json,
gift_text.json and trial_text.json, all keyed by id. Here they are joined by that id into the shapes events.py,
gifts.py and trials.py have always read; no text is converted or edited here.
"""

import json
from pathlib import Path

import yaml

from . import package
from .paths import PACKAGE


def load(name, folder: Path = PACKAGE):
    return json.loads(package.path(f"data/{name}", folder).read_text(encoding="utf-8"))


def events(folder: Path = PACKAGE):
    """{"client", "zh_release", "gifts": {id: {en, zh, keyword, tier}}, "events": [...]}: every event and page of
    event_table.json with its text; an option holds its table row (gifts as gift_keywords) and its text."""
    table, text, gift_text = load("event_table.json", folder), load("event_text.json", folder), load("gift_text.json", folder)
    rows = []
    for page, group in ((False, table["events"]), (True, table["pages"])):
        for row in group:
            t = text["events"][str(row["id"])]
            options = []
            for o, to in zip(row["options"], t["options"], strict=True):
                rest = {k: v for k, v in o.items() if k not in ("text", "hint", "gifts")}
                options.append({
                    "text": to["text"], "hint": o["hint"], "text_zh": to["text_zh"], "hint_zh": to["hint_zh"],
                    "text_cn": to["text_cn"], "hint_cn": to["hint_cn"], "gift_keywords": o.get("gifts", []), **rest})
            rows.append({"id": row["id"], "page": page, "key": row.get("key", ""), "title": t["title"], "story": t["story"],
                         "story_zh": t["story_zh"], "story_cn": t["story_cn"], "options": options})
    gifts = {i: {k: g[k] for k in ("en", "zh", "keyword", "tier")} for i, g in gift_text["gifts"].items()}
    return {"client": text["client"], "zh_release": text["zh_release"], "gifts": gifts, "events": rows}


def gifts(folder: Path = PACKAGE):
    """{"gifts": {id: row}}: gift_text.json's rows, each with the `recipe` ({recipes, groups}, only the keys the row
    has) of its gift_recipes.json row when it has one."""
    recipes = {str(g["id"]): {k: g[k] for k in ("recipes", "groups") if k in g} for g in load("gift_recipes.json", folder)["gifts"]}
    rows = {}
    for i, g in load("gift_text.json", folder)["gifts"].items():
        rows[i] = {**g, "recipe": recipes[i]} if i in recipes else dict(g)
    return {"gifts": rows}


def trials(folder: Path = PACKAGE):
    """{"client", "model", "trials": {English name: row}}: each trials.yaml entry with its text, by buff id."""
    table = yaml.safe_load(package.path("data/trials.yaml", folder).read_text(encoding="utf-8"))
    text = load("trial_text.json", folder)["trials"]
    return {"client": table["client"], "model": table["model"],
            "trials": {name: {**t, **text[t["id"]]} for name, t in table["trials"].items()}}
