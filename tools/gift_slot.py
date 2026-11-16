"""The game's E.G.O gift slot for the overlay's cards: its striped plate as assets/gift_slot/plate.png, read from the
client maalc unpacked (its .local/unpack; maalc's folder as tools/maalc_checkout.py finds it), and a check that the slot's
layout is still the one lc_helper.icons draws.

Usage: uv run --group unpack python tools/gift_slot.py

The slot is the prefab EgoGiftIconPrefab (the shop, a Gift GET page and the Gift Search draw a gift with it), found
through the game's own objects, never by sprite name: the GameObject of the MonoBehaviour whose script is
EgoGiftIconPrefabUI, in player data file PREFAB_FILE. Its children, by their RectTransforms:
- img_basePanel fills the slot. Its DUISpriteSetter (a MonoBehaviour holding an Addressables key "<atlas>/<sprite>")
  names the plate, EgoGift_bg1; the plate is cut from that SpriteAtlas of the THEME the game's screens show, in maalc's
  raw/UnityCache, found through out/sprite-index.tsv by its container, through Sprite.m_RenderDataKey and
  SpriteAtlas.m_RenderDataMap.
- img_Icon is the gift's picture, img_keywordIcon1 its keyword's icon in the bottom-right corner and tmp_Tier its tier,
  a TextMeshPro text in the top-left corner.
The script stops when these sizes and places differ from icons.SLOT. Written against client 1.118.1; rerun it after a
client update.
"""

import re
import struct
from pathlib import Path

import UnityPy
from PIL import Image

from lc_helper import icons
from maalc_checkout import REPO, maalc_dir

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"  # bundles carry a stripped one (maalc .local/unpack/NOTES.md)
UNPACK = ".local/unpack"
DATA = "apk-data/assets/bin/Data"
PREFAB_FILE, PREFAB_SCRIPT = "58ee2310d9a9760439abf6e0adf2ded9", "EgoGiftIconPrefabUI"
# A DUISpriteSetter key's atlas, in each of the client's UI themes. The game's screens show the Legacy one's plate,
# brown inside its stripes (maalc tests/screens/GiftGet.png, Shop.png); the Default one's is black inside.
ATLASES = "Assets/Resources_moved/DUI/spriteAtlas/{theme}/{atlas}.spriteatlasv2"
THEME = "Legacy"
# Each child icons.SLOT places, with the RectTransform anchor it is placed from.
CHILDREN = {"img_Icon": (0.5, 0.5), "img_keywordIcon1": (1, 0), "tmp_Tier": (0, 1)}


class Player:
    """The client's player data files, each loaded once (a split one from its split0), and pointers across them."""

    def __init__(self, data: Path):
        self.data, self.files = data, {}

    def load(self, name):
        if name not in self.files:
            path = self.data / name
            env = UnityPy.load(str(path if path.exists() else self.data / f"{name}.split0"))
            externals = [Path(e.path).name for e in next(iter(env.files.values())).externals]
            self.files[name] = ({o.path_id: o for o in env.objects}, externals)
        return self.files[name]

    def resolve(self, name, file_id, path_id):
        """The object a PPtr (file_id, path_id) in file name points at; None for a null one."""
        objects, externals = self.load(name)
        if path_id == 0:
            return None
        return (objects if file_id == 0 else self.load(externals[file_id - 1])[0]).get(path_id)

    def script(self, name, behaviour):
        """A MonoBehaviour's script class, from its m_Script PPtr after m_GameObject and m_Enabled."""
        file_id, path_id = struct.unpack_from("<iq", behaviour.get_raw_data(), 16)
        script = self.resolve(name, file_id, path_id)
        return script.read().m_ClassName if script is not None else None


def prefab(player):
    """The slot prefab's children by name: (RectTransform typetree, DUISpriteSetter keys)."""
    objects, _ = player.load(PREFAB_FILE)
    root = next(struct.unpack_from("<q", o.get_raw_data(), 4)[0] for o in objects.values()
                if o.type.name == "MonoBehaviour" and player.script(PREFAB_FILE, o) == PREFAB_SCRIPT)
    children = {}

    def walk(game_object):
        tree = objects[game_object].read_typetree()
        rect, keys = None, []
        for component in tree["m_Component"]:
            c = objects[component["component"]["m_PathID"]]
            if c.type.name == "RectTransform":
                rect = c.read_typetree()
            elif c.type.name == "MonoBehaviour" and player.script(PREFAB_FILE, c) == "DUISpriteSetter":
                keys += [m.group().decode() for m in re.finditer(rb"[A-Za-z0-9_]+/[A-Za-z0-9_/]+", c.get_raw_data())]
        children[tree["m_Name"]] = (rect, keys)
        for child in rect["m_Children"]:
            walk(objects[child["m_PathID"]].read_typetree()["m_GameObject"]["m_PathID"])

    walk(root)
    return children


def check_layout(children):
    """Stop unless the slot is still laid out as icons.SLOT says, in the prefab's units."""
    size = children["EgoGiftIconPrefab"][0]["m_SizeDelta"]
    found = {"slot": (size["x"], size["y"])}
    for name, anchor in CHILDREN.items():
        rect = children[name][0]
        if (rect["m_AnchorMin"]["x"], rect["m_AnchorMin"]["y"]) != anchor:
            raise SystemExit(f"{name} is anchored at {rect['m_AnchorMin']}, not {anchor}")
        found[name] = (rect["m_SizeDelta"]["x"], rect["m_SizeDelta"]["y"], rect["m_AnchoredPosition"]["x"],
                       rect["m_AnchoredPosition"]["y"])
    want = {"slot": (icons.SLOT["slot"],) * 2,
            "img_Icon": (icons.SLOT["picture"],) * 2 + (0, icons.SLOT["picture_rise"]),
            "img_keywordIcon1": (icons.SLOT["keyword"],) * 2 + (-icons.SLOT["keyword_in"], icons.SLOT["keyword_in"])}
    for name, sizes in want.items():
        if any(abs(a - b) > 0.5 for a, b in zip(found[name], sizes)):
            raise SystemExit(f"the slot's {name} changed: {found[name]}, icons.SLOT has {sizes}")
    print("layout:", found)


def atlas_sprite(unpack: Path, key: str) -> Image.Image:
    """The sprite a DUISpriteSetter key "<atlas path>/<sprite>" names, cut from its atlas page."""
    atlas_path, name = key.rsplit("/", 1)
    container = ATLASES.format(theme=THEME, atlas=atlas_path)
    bundle = next((line.split("\t")[0] for line in (unpack / "out/sprite-index.tsv").read_text("utf-8").splitlines()
                   if line.endswith(f"\tSpriteAtlas\t{container}")), None)
    if bundle is None:
        raise SystemExit(f"no bundle holds {container} (out/sprite-index.tsv)")
    objects = {o.path_id: o for o in UnityPy.load(str(unpack / "raw/UnityCache" / bundle / "__data")).objects}
    atlas = next(t for o in objects.values() if o.type.name == "SpriteAtlas"
                 and (t := o.read_typetree())["m_Name"] == atlas_path.rsplit("/", 1)[-1])
    render = {(tuple(k[0][f"data[{i}]"] for i in range(4)), k[1]): v for k, v in atlas["m_RenderDataMap"]}
    for packed in atlas["m_PackedSprites"]:
        sprite = objects[packed["m_PathID"]]
        if sprite.read().m_Name != name:
            continue
        k = sprite.read_typetree()["m_RenderDataKey"]
        data = render[(tuple(k[0][f"data[{i}]"] for i in range(4)), k[1])]
        page = objects[data["texture"]["m_PathID"]].read().image  # Sprite.image is wrong for an atlas's sprites
        r = data["textureRect"]
        x, y, w, h = (round(r[c]) for c in ("x", "y", "width", "height"))
        return page.crop((x, page.height - y - h, x + w, page.height - y)).convert("RGBA")  # textureRect is y up
    raise SystemExit(f"atlas {atlas_path} has no sprite {name}")


def main():
    unpack = maalc_dir() / UNPACK
    if not (unpack / DATA / f"{PREFAB_FILE}").exists():
        raise SystemExit(f"no unpacked client at {unpack / DATA}: unpack it with maalc's tools first")
    children = prefab(Player(unpack / DATA))
    check_layout(children)
    keys = children["img_basePanel"][1]
    if len(keys) != 1:
        raise SystemExit(f"img_basePanel's sprite keys: {keys}")
    plate = atlas_sprite(unpack, keys[0])
    out = REPO / "assets/gift_slot"
    out.mkdir(parents=True, exist_ok=True)
    plate.save(out / "plate.png")
    print(f"plate: {keys[0]} {plate.width}x{plate.height}")


if __name__ == "__main__":
    main()
