"""Pull what lc-helper reuses from a maalc checkout: battle templates, the OCR model and the event data.

Usage: uv run --group sync python tools/sync_maalc.py

maalc's folder: the path in .local/maalc_dir, else ../maalc next to this repository. Rerun it after maalc
updates its event table or templates (a new season); it overwrites everything it writes.

Writes:
- assets/templates/*.png: maalc's battle and event templates (assets/resource/base/image, data/stagger_word.png).
- assets/maa/model/ocr/: maalc's ppocr_v6 model (gitignored; tools/fetch_ocr.py in maalc downloads it).
- assets/events.json: maalc's event table (assets/resource/base/data/event_table.json), joined by event id with
  the full English story and option text (maalc's .local/unpack/out/events-md8.json), their Chinese text from the
  newest Localize Limbus Company zip in maalc's .local/llc/ (Simplified, converted with OpenCC s2twp), and the
  name, keyword and tier of every gift an option gives (maalc's .local/unpack static data and localization).
"""

import json
import re
import shutil
import zipfile
from pathlib import Path

import opencc

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = {
    "Battle/BattleTurn.png": "battle_turn.png",
    "Battle/BattleTurnPressed.png": "battle_turn_pressed.png",
    "Battle/BattleStart.png": "battle_start.png",
    "Battle/BattlePause.png": "battle_pause.png",
    "Battle/BattleMenuResume.png": "battle_menu_resume.png",
    "Screen/Connecting.png": "connecting.png",
    "Screen/DialogButton.png": "dialog_button.png",
}
STATIC = ".local/unpack/static/Assets/Resources_moved/StaticData/static-data"
LOCALIZE_EN = ".local/unpack/raw/Localize/en"
LLC_LANG = "LimbusCompany_Data/Lang/LLC_zh-CN/"
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
_S2TWP = opencc.OpenCC("s2twp")
# Where s2twp's Taiwan wording is wrong for the game text (maalc tools/llc_text.py FIXES).
ZH_FIXES = {"指標": "指針", "重新整理": "刷新", "映象": "鏡像", "透過階層": "通過階層", "松肉": "鬆肉"}


def maalc_dir():
    local = REPO / ".local/maalc_dir"
    path = Path(local.read_text(encoding="utf-8").strip()) if local.is_file() else REPO.parent / "maalc"
    if not (path / "assets/resource/base/data/event_table.json").is_file():
        raise SystemExit(f"no maalc checkout at {path}: write its path into .local/maalc_dir")
    return path


def plain(s):
    return re.sub(r"<[^>]*>", "", s or "").strip()


def zh(s):
    s = _S2TWP.convert(plain(s))
    for wrong, right in ZH_FIXES.items():
        s = s.replace(wrong, right)
    return s


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def copy_assets(maalc):
    out = REPO / "assets/templates"
    out.mkdir(parents=True, exist_ok=True)
    image = maalc / "assets/resource/base/image"
    for src, dst in TEMPLATES.items():
        shutil.copyfile(image / src, out / dst)
    shutil.copyfile(maalc / "assets/resource/base/data/stagger_word.png", out / "stagger_word.png")
    model = maalc / "assets/resource/base/model/ocr"
    if (model / "rec.onnx").is_file():
        shutil.copytree(model, REPO / "assets/maa/model/ocr", dirs_exist_ok=True)
    else:
        print(f"no OCR model in {model}: run `uv run python tools/fetch_ocr.py` in maalc, then this again")


def llc_zip(maalc):
    zips = sorted((maalc / ".local/llc").glob("*.zip"))
    if not zips:
        raise SystemExit("no Localize Limbus Company zip in maalc's .local/llc: run maalc's tools/llc_text.py once")
    return zips[-1]


def llc_rows(z, name):
    try:
        return {r["id"]: r for r in json.loads(z.read(LLC_LANG + name).decode("utf-8-sig"))["dataList"]}
    except KeyError:
        return {}


def gift_info(maalc, z, ids):
    """gift id -> {en, zh, keyword, tier} for the ids options give."""
    static = maalc / STATIC
    info = {i: {"en": "", "zh": "", "keyword": "Keywordless", "tier": None} for i in ids}
    for f in sorted(static.glob("ego-gift*/*.json")):
        for g in load(f).get("list", []):
            if not isinstance(g, dict) or g.get("id") not in info:
                continue
            row = info[g["id"]]
            if g.get("keyword") and row["keyword"] == "Keywordless":
                row["keyword"] = UI_KW.get(g["keyword"], "Keywordless")
            tier = next((int(m.group(1)) for t in g.get("tag") or [] if (m := re.fullmatch(r"TIER_(\d)", str(t)))), None)
            if tier and not row["tier"]:
                row["tier"] = tier
    for f in sorted((maalc / LOCALIZE_EN).glob("EN_EGOgift*.json")):
        for g in load(f).get("dataList") or []:
            if g.get("id") in info and not info[g["id"]]["en"]:
                info[g["id"]]["en"] = plain(g.get("name")).replace("’", "'")
    for name in sorted(n[len(LLC_LANG):] for n in z.namelist() if n.startswith(LLC_LANG + "EGOgift_")):
        for i, g in llc_rows(z, name).items():
            if i in info and not info[i]["zh"]:
                info[i]["zh"] = zh(g.get("name"))
    return info


def option_zh(loc, i):
    opts = (loc or {}).get("options") or []
    if i >= len(opts):
        return "", ""
    return zh(opts[i].get("message")), zh(opts[i].get("messageDesc"))


def build(maalc):
    table = load(maalc / "assets/resource/base/data/event_table.json")
    md8 = {e["id"]: e for e in load(maalc / ".local/unpack/out/events-md8.json")["events"]}
    zpath = llc_zip(maalc)
    z = zipfile.ZipFile(zpath)
    loc_cache = {}

    def loc(event_id):
        f = md8[event_id]["locFile"].removeprefix("EN_")
        if f not in loc_cache:
            loc_cache[f] = llc_rows(z, f)
        return loc_cache[f].get(event_id)

    rows, missing_zh = [], []
    for page, e in [(False, e) for e in table["events"]] + [(True, p) for p in table["pages"]]:
        src, zrow = md8[e["id"]], loc(e["id"])
        if zrow is None:
            missing_zh.append(e["id"])
        options = []
        for i, o in enumerate(e["options"]):
            text_zh, hint_zh = option_zh(zrow, i)
            full = src["options"][i] if i < len(src["options"]) else {}
            options.append({"text": plain(full.get("text")) or o["text"], "hint": o["hint"], "text_zh": text_zh,
                            "hint_zh": hint_zh, **{k: v for k, v in o.items() if k not in ("text", "hint", "gifts")}})
        rows.append({"id": e["id"], "page": page, "key": e.get("key", ""), "title": plain(src.get("title")),
                     "story": plain(src.get("desc")), "story_zh": zh((zrow or {}).get("desc") or (zrow or {}).get("eventDesc")),
                     "options": options})
    ids = {g[1] for r in rows for o in r["options"] for b in o.get("odds", []) + o.get("fail", []) for g in b["gets"]
           if g[0] in ("gift", "win_gift")} | {g[0] for r in rows for o in r["options"] for g in o.get("gift_ids", [])}
    gifts = gift_info(maalc, z, ids)
    note = ("Mirror Dungeon choice events for lc-helper, written by tools/sync_maalc.py from maalc's event table "
            f"(client {table['client']}) and unpacked game text. Chinese: Localize Limbus Company {zpath.stem} "
            "(CC BY-NC-SA 4.0), OpenCC s2twp. Game data (c) Project Moon.")
    return {"note": note, "client": table["client"], "zh_release": zpath.stem,
            "gifts": {str(k): v for k, v in sorted(gifts.items())}, "events": rows}, missing_zh


def main():
    maalc = maalc_dir()
    copy_assets(maalc)
    data, missing_zh = build(maalc)
    out = REPO / "assets/events.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    no_name = [i for i, g in data["gifts"].items() if not g["en"] or not g["zh"]]
    print(f"{len(data['events'])} events, {len(data['gifts'])} gifts -> {out} ({out.stat().st_size} bytes)")
    print(f"events without Chinese text: {missing_zh or 'none'}; gifts missing a name: {no_name or 'none'}")


if __name__ == "__main__":
    main()
