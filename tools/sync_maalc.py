"""Pull what lc-helper reuses from a maalc checkout: battle templates, the OCR model and the event data.

Usage: uv run --group sync python tools/sync_maalc.py

maalc's folder: the path in .local/maalc_dir, else ../maalc next to this repository. Rerun it after maalc
updates its event table or templates (a new season); it overwrites everything it writes.

Writes:
- assets/templates/*.png: maalc's battle and event templates (assets/resource/base/image, data/stagger_word.png).
- assets/maa/model/ocr/: maalc's ppocr_v6 model (gitignored; tools/fetch_ocr.py in maalc downloads it).
- assets/keywords/*.png: the game's keyword icons (maalc's assets/resource/base/data/keyword_icons), as PNG: Qt reads
  maalc's webp only through its qwebp image format plugin, and PNG through none.
- assets/events.json: maalc's event table (assets/resource/base/data/event_table.json), joined by event id with
  the full English story and option text (maalc's .local/unpack/out/events-md8.json), their Chinese text from
  Localize Limbus Company (llc_source: the Simplified original in the _cn fields, converted with OpenCC s2twp in the
  _zh ones), and the name, keyword and tier of every gift an option gives (maalc's .local/unpack static data and
  localization).
- assets/gifts.json: every gift in maalc's gift search and fusion recipes (and the event table), with its effect in
  English and Chinese, its enhanced effect, its fusion recipe, and its Simplified name, cn (build_gifts).
"""

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
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


def copy_keyword_icons(maalc):
    out = REPO / "assets/keywords"
    out.mkdir(parents=True, exist_ok=True)
    for src in sorted((maalc / "assets/resource/base/data/keyword_icons").glob("*.webp")):
        image = cv2.imdecode(np.fromfile(src, np.uint8), cv2.IMREAD_UNCHANGED)  # imread fails on a non-ASCII path
        cv2.imencode(".png", image)[1].tofile(out / f"{src.stem}.png")


@dataclass(frozen=True)
class Llc:
    """One Localize Limbus Company release: the json files of its LLC_zh-CN folder by name, and where it came from."""

    read: dict  # file name -> () -> its bytes
    version: str  # Info/version.json
    source: str  # for the data's note: the game's folder, or the zip's name

    def names(self, prefix):
        return sorted(n for n in self.read if n.startswith(prefix))

    def rows(self, name):
        data = json.loads(self.read[name]().decode("utf-8-sig")) if name in self.read else {}
        return {r["id"]: r for r in (data.get("dataList") or [] if isinstance(data, dict) else [])}


def llc_folder(path):
    for d in (path / LLC_LANG, path):
        if (d / "Info/version.json").is_file():
            return d
    return None


def steam_games():
    """The Limbus Company folder in each Steam library on this machine (Steam's libraryfolders.vdf)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except (ImportError, OSError):
        return []
    vdf = steam / "steamapps/libraryfolders.vdf"
    libs = [steam] + ([Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8"))]
                      if vdf.is_file() else [])
    return [lib / "steamapps/common/Limbus Company" for lib in libs]


def installed_llc(folder):
    read = {p.name: p.read_bytes for p in folder.glob("*.json")}
    version = json.loads((folder / "Info/version.json").read_text("utf-8-sig"))["version"]
    return Llc(read, str(version), "the LLC_zh-CN folder installed in the game")


def zipped_llc(path):
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if n.startswith(LLC_LANG) and "/" not in n[len(LLC_LANG):]]
    read = {n[len(LLC_LANG):]: (lambda n=n: z.read(n)) for n in names}
    version = json.loads(z.read(LLC_LANG + "Info/version.json").decode("utf-8-sig"))["version"]
    return Llc(read, str(version), f"maalc's {path.name}")


def llc_source(maalc):
    """The LLC text to read: the folder installed in the game (the game's folder in .local/llc_dir, else Limbus
    Company in any Steam library), else the newest zip in maalc's .local/llc."""
    local = REPO / ".local/llc_dir"
    if local.is_file():
        game = Path(local.read_text(encoding="utf-8").strip())
        if not (folder := llc_folder(game)):
            raise SystemExit(f"no {LLC_LANG}Info/version.json in {game}, the folder .local/llc_dir names")
    else:
        folder = next(filter(None, map(llc_folder, steam_games())), None)
    if folder:
        return installed_llc(folder)
    zips = sorted((maalc / ".local/llc").glob("*.zip"))
    if not zips:
        raise SystemExit("no Localize Limbus Company: install it in the game, write the game's folder into "
                         ".local/llc_dir, or run maalc's tools/llc_text.py once for a zip in maalc's .local/llc")
    return zipped_llc(zips[-1])


def cn_names(llc, prefix):
    """id -> the Simplified name in LLC's files whose names start with prefix (the first file naming an id)."""
    names = {}
    for name in llc.names(prefix):
        for i, row in llc.rows(name).items():
            if text := plain(row.get("name")):
                names.setdefault(i, text)
    return names


def gift_info(maalc, llc, ids):
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
    for i, name in cn_names(llc, "EGOgift_").items():
        if i in info and not info[i]["zh"]:
            info[i]["zh"] = zh(name)
    return info


def buff_names(maalc, llc):
    """The game's buff ids ([Combustion] in gift text) -> (English name, Chinese name)."""
    en = {}
    for f in sorted((maalc / LOCALIZE_EN).glob("EN_Bufs*.json")):
        for b in load(f).get("dataList") or []:
            en.setdefault(b.get("id"), plain(b.get("name")))
    return en, {i: zh(name) for i, name in cn_names(llc, "Bufs").items()}


def gift_text(s, names):
    """A gift's description for a reader: [BuffId] tags named, markup dropped, blank lines squeezed."""
    s = re.sub(r"\[(\w+)\]", lambda m: f"「{names.get(m[1]) or m[1]}」", plain(s))
    return re.sub(r"\n{3,}", "\n\n", s.replace("\r", "")).strip()


def build_gifts(maalc, llc, event_ids):
    """assets/gifts.json: every gift maalc's gift search, fusion recipes and the event table name, with its effect in
    English and Chinese, the effect once enhanced (the gift id + 10000), the gifts it is fused from, and its
    Simplified name as LLC shows it (cn)."""
    data = maalc / "assets/resource/base/data"
    search = load(data / "gift_search.json")["gifts"]
    recipes = load(data / "gift_recipes.json")
    rows = {g["id"]: {k: g.get(k) for k in ("en", "zh", "keyword", "tier")}
            for g in search + recipes["materials"] + recipes["extra_gifts"] + recipes["vestiges"] + recipes["gifts"]}
    for g in recipes["gifts"]:
        # recipes: any one list of gift ids fuses it; groups: need of each group's ids (maalc gift_recipes.json note)
        rows[g["id"]]["recipe"] = {k: g[k] for k in ("recipes", "groups") if k in g}
    for i, g in gift_info(maalc, llc, set(event_ids) - set(rows)).items():
        rows[i] = dict(g)
    en_buffs, zh_buffs = buff_names(maalc, llc)
    desc_en, desc_zh = {}, {}
    for f in sorted((maalc / LOCALIZE_EN).glob("EN_EGOgift*.json")):
        for g in load(f).get("dataList") or []:
            desc_en.setdefault(g.get("id"), gift_text(g.get("desc"), en_buffs))
    for name in llc.names("EGOgift_"):
        for i, g in llc.rows(name).items():
            desc_zh.setdefault(i, zh(gift_text(g.get("desc"), zh_buffs)))
    cn = cn_names(llc, "EGOgift_")
    for i, row in rows.items():
        row["en"] = (row.get("en") or "").replace("’", "'")
        row.update(cn=cn.get(i, ""), desc_en=desc_en.get(i, ""), desc_zh=desc_zh.get(i, ""),
                   plus_en=desc_en.get(i + 10000, ""), plus_zh=desc_zh.get(i + 10000, ""))
    note = ("E.G.O gifts for lc-helper, written by tools/sync_maalc.py from maalc's gift search and recipe data and "
            f"the unpacked game text. Chinese: {llc_credit(llc)}; Traditional names from maalc's data where it has "
            "them. Game data (c) Project Moon.")
    return {"note": note, "gifts": {str(k): v for k, v in sorted(rows.items())}}


def llc_credit(llc):
    return (f"Localize Limbus Company {llc.version} from {llc.source} (CC BY-NC-SA 4.0), the Simplified original in "
            "cn and the _cn fields, converted with OpenCC s2twp in zh and the _zh fields")


def option_text(loc, i):
    """(text, hint) of option i in an event's LLC row, Simplified as LLC has them."""
    opts = (loc or {}).get("options") or []
    if i >= len(opts):
        return "", ""
    return plain(opts[i].get("message")), plain(opts[i].get("messageDesc"))


def build(maalc, llc):
    table = load(maalc / "assets/resource/base/data/event_table.json")
    md8 = {e["id"]: e for e in load(maalc / ".local/unpack/out/events-md8.json")["events"]}
    loc_cache = {}

    def loc(event_id):
        f = md8[event_id]["locFile"].removeprefix("EN_")
        if f not in loc_cache:
            loc_cache[f] = llc.rows(f)
        return loc_cache[f].get(event_id)

    rows, missing_zh = [], []
    for page, e in [(False, e) for e in table["events"]] + [(True, p) for p in table["pages"]]:
        src, zrow = md8[e["id"]], loc(e["id"])
        if zrow is None:
            missing_zh.append(e["id"])
        options = []
        for i, o in enumerate(e["options"]):
            text_cn, hint_cn = option_text(zrow, i)
            full = src["options"][i] if i < len(src["options"]) else {}
            options.append({"text": plain(full.get("text")) or o["text"], "hint": o["hint"], "text_zh": zh(text_cn),
                            "hint_zh": zh(hint_cn), "text_cn": text_cn, "hint_cn": hint_cn,
                            "gift_keywords": o.get("gifts", []),
                            **{k: v for k, v in o.items() if k not in ("text", "hint", "gifts")}})
        story_cn = plain((zrow or {}).get("desc") or (zrow or {}).get("eventDesc"))
        rows.append({"id": e["id"], "page": page, "key": e.get("key", ""), "title": plain(src.get("title")),
                     "story": plain(src.get("desc")), "story_zh": zh(story_cn), "story_cn": story_cn,
                     "options": options})
    ids = {g[1] for r in rows for o in r["options"] for b in o.get("odds", []) + o.get("fail", []) for g in b["gets"]
           if g[0] in ("gift", "win_gift")} | {g[0] for r in rows for o in r["options"] for g in o.get("gift_ids", [])}
    gifts = gift_info(maalc, llc, ids)
    note = ("Mirror Dungeon choice events for lc-helper, written by tools/sync_maalc.py from maalc's event table "
            f"(client {table['client']}) and unpacked game text. Chinese: {llc_credit(llc)}. Game data (c) Project "
            "Moon.")
    return {"note": note, "client": table["client"], "zh_release": llc.version,
            "gifts": {str(k): v for k, v in sorted(gifts.items())}, "events": rows}, missing_zh


def main():
    maalc = maalc_dir()
    copy_assets(maalc)
    copy_keyword_icons(maalc)
    llc = llc_source(maalc)
    print(f"Localize Limbus Company {llc.version} from {llc.source}")
    data, missing_zh = build(maalc, llc)
    out = REPO / "assets/events.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    no_name = [i for i, g in data["gifts"].items() if not g["en"] or not g["zh"]]
    no_cn = [e["id"] for e in data["events"] if any(en and not cn for en, cn in [(e["story"], e["story_cn"])] + [
        pair for o in e["options"] for pair in ((o["text"], o["text_cn"]), (o["hint"], o["hint_cn"]))])]
    print(f"{len(data['events'])} events, {len(data['gifts'])} gifts -> {out} ({out.stat().st_size} bytes)")
    print(f"events without Chinese text: {missing_zh or 'none'}; with English but no Simplified story, option or "
          f"hint: {no_cn or 'none'}; gifts missing a name: {no_name or 'none'}")
    gifts = build_gifts(maalc, llc, [int(i) for i in data["gifts"]])
    out = REPO / "assets/gifts.json"
    out.write_text(json.dumps(gifts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows = gifts["gifts"]
    print(f"{len(rows)} gifts -> {out} ({out.stat().st_size} bytes); without English effect: "
          f"{[i for i, g in rows.items() if not g['desc_en']] or 'none'}; without Chinese effect: "
          f"{[i for i, g in rows.items() if not g['desc_zh']] or 'none'}; without a Simplified name: "
          f"{[i for i, g in rows.items() if not g['cn']] or 'none'}")


if __name__ == "__main__":
    main()
