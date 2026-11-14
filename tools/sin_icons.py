"""The game's seven sin icons for the overlay's check cards: assets/sin_icons/<Wrath|Lust|Sloth|Gluttony|Gloom|Pride|
Envy>.png, read from the client maalc unpacked (its .local/unpack; maalc's folder as tools/sync_maalc.py finds it).

Usage: uv run --group unpack python tools/sin_icons.py

They are the emblems the game draws on a Choices page, full colour with a cream outline (sprites "BattleUI_Choice
1_<Crimson|...|Violet>", 120x124 to 120x128), found through the game's own objects, never by sprite name: the
UISpriteDataManager MonoBehaviour of scene level1 holds, in this order, _uiSprites (one PPtr), evilSpriteList,
attributeOutlineList and totalAttributeSpriteList, each a list of {ATTRIBUTE_TYPE key, PPtr<Sprite>}; these are the
last list's, resolved through the scene's externals table. ATTRIBUTE_TYPE 0..6 is CRIMSON SCARLET AMBER SHAMROCK AZURE
INDIGO VIOLET, Wrath Lust Sloth Gluttony Gloom Pride Envy (raw/Localize/en/EN_AttributeText.json), the order of
lc_helper.events.SINS: the script stops when a sprite's name does not end in its key's colour. Written against client
1.118.1; rerun it after a client update.
"""

import struct
from pathlib import Path

import UnityPy
from PIL import Image

from sync_maalc import REPO, maalc_dir

# Bundles carry a stripped Unity version; the client's own (maalc .local/unpack/NOTES.md, from libunity.so).
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"
DATA = ".local/unpack/apk-data/assets/bin/Data"
COLOURS = ["CRIMSON", "SCARLET", "AMBER", "SHAMROCK", "AZURE", "INDIGO", "VIOLET"]  # ATTRIBUTE_TYPE 0..6
SINS = ["Wrath", "Lust", "Sloth", "Gluttony", "Gloom", "Pride", "Envy"]  # the files, in the same order
SCENE, MANAGER = "level1", 1906  # UISpriteDataManager's file and path_id
BEFORE_TOTAL = 2  # evilSpriteList and attributeOutlineList, between _uiSprites and totalAttributeSpriteList

_envs = {}


def load(data: Path, name: str):
    """A player data file by its name (a split one from its split0), each file once."""
    if name not in _envs:
        path = data / name
        _envs[name] = UnityPy.load(str(path if path.exists() else data / f"{name}.split0"))
    return _envs[name]


def obj(env, path_id: int):
    return next(o for o in env.objects if o.path_id == path_id)


def keyed_list(raw: bytes, off: int) -> tuple[dict[int, tuple[int, int]], int]:
    """A serialized List<{int key, PPtr}> at off: {key: (fileID, pathID)}, and the offset after it."""
    count = struct.unpack_from("<i", raw, off)[0]
    if not 0 <= count < 64:
        raise SystemExit(f"not a keyed list at {off}: count {count}")
    found = {}
    for i in range(count):
        key, file_id, path_id = struct.unpack_from("<iiq", raw, off + 4 + 16 * i)
        found[key] = (file_id, path_id)
    return found, off + 4 + 16 * count


def total_list(data: Path) -> dict[int, tuple[int, int]]:
    """UISpriteDataManager's totalAttributeSpriteList, read from its raw bytes: past its header (m_GameObject,
    m_Enabled, m_Script, m_Name) and _uiSprites, then the lists before it."""
    raw = obj(load(data, SCENE), MANAGER).get_raw_data()
    name_len = struct.unpack_from("<i", raw, 28)[0]
    off = 32 + (name_len + 3) // 4 * 4 + 12
    for _ in range(BEFORE_TOTAL):
        _, off = keyed_list(raw, off)
    return keyed_list(raw, off)[0]


def sprite_image(sprite) -> Image.Image:
    """The sprite over its whole rect: a packed sprite's picture placed at its offset (maalc tools/unity_files.py)."""
    image = sprite.image
    w, h = round(sprite.m_Rect.width), round(sprite.m_Rect.height)
    if image.size == (w, h):
        return image.convert("RGBA")
    off = sprite.m_RD.textureRectOffset
    full = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    full.paste(image.convert("RGBA"), (round(off.x), h - round(off.y) - image.height))
    return full


def main():
    data = maalc_dir() / DATA
    if not (data / SCENE).is_file():
        raise SystemExit(f"no unpacked client at {data}: unpack it with maalc's tools first")
    pointers = total_list(data)
    externals = [e.path for e in next(iter(load(data, SCENE).files.values())).externals]
    out = REPO / "assets/sin_icons"
    out.mkdir(parents=True, exist_ok=True)
    for key, (sin, colour) in enumerate(zip(SINS, COLOURS)):
        if key not in pointers:
            raise SystemExit(f"totalAttributeSpriteList has no entry for ATTRIBUTE_TYPE {key}")
        file_id, path_id = pointers[key]
        sprite = obj(load(data, SCENE if file_id == 0 else externals[file_id - 1]), path_id).read()
        if not sprite.m_Name.upper().endswith("_" + colour):
            raise SystemExit(f"ATTRIBUTE_TYPE order broken: the {colour} key holds {sprite.m_Name}")
        image = sprite_image(sprite)
        image.save(out / f"{sin}.png")
        print(f"{sin}: {sprite.m_Name} {image.width}x{image.height}")


if __name__ == "__main__":
    main()
