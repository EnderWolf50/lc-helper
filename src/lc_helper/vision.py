"""What a 1280x720 BGR screenshot of Limbus Company shows. Pure functions: an image in, a reading out.

Ported from maalc (agent/battle.py, agent/actions.py, agent/recovery.py), where every constant was measured live;
the comments keep maalc's evidence. Template matching runs on OpenCV directly, the way MaaFramework's
TemplateMatch does (TM_CCOEFF_NORMED on the colour image), so maalc's thresholds carry over.
"""

from functools import cache

import cv2
import numpy as np

from . import package
from .paths import ASSETS


Box = tuple[int, int, int, int]

# maalc mirror_dungeon.json's nodes: (template files, roi, threshold).
BATTLE_TURN_ROI = (700, 515, 580, 60)  # the Win Rate label, plain or pressed
BATTLE_PAUSE_ROI = (1130, 5, 100, 75)  # a turn playing out: the pause button replaces the top-right controls
BATTLE_MENU_ROIS = ((505, 296, 270, 41), (505, 323, 270, 42))  # the menu's Resume bar: Mirror Dungeon, Luxcavation
CONNECTING_ROI = (995, 45, 250, 60)
DIALOG_BUTTON_ROI = (340, 380, 600, 180)
MATCH = 0.8

# Offsets from the Win Rate label's top-left (maalc actions.py). The Damage label sits under it, one label lower.
WIN_RATE = (20, 14)
DAMAGE = (20, 52)
START_DISC = (-66, 26)
TURN_NUMBER = (55, 57, 45, 30)
SLOT_PORTRAIT_Y = 665  # tapping a slot's portrait swaps its lower skill and its guard skill
LOWER_Y = 577  # a slot's lower skill, at rest

# A battle's end (maalc mirror_dungeon.json Victory and WipeDialog, OCR nodes there; templates here).
VICTORY_ROI = (420, 280, 440, 140)
WIPE_ROI = (330, 360, 270, 50)


def wiped(image):
    """Whether the wipe dialog (every participating sinner killed) is up: its first text line, cut from maalc's
    WipeDialog.png capture by tools/make_templates.py."""
    x, y, w, h = WIPE_ROI
    return find(image, "wipe_text.png", (x - 20, y - 10, w + 40, h + 20)) is not None


def victory(image):
    """Whether the VICTORY banner is up, through the fade that follows it: its word, cut from a PC client capture
    by tools/make_templates.py. The banner is bright for one look at most (0.3 s apart) before the screen darkens,
    which an orange share missed on 2026-11-14; the word still matches 0.997 at the fade's darkest frame
    (LlcVictoryFading.png) and 0.957 on maalc's emulator Victory.png, no other capture above 0.32."""
    return find(image, "victory.png", VICTORY_ROI) is not None


# Event pages (maalc actions.py).
EVENT_STORY = (60, 320, 580, 200)
CHOICES_HEADER = (690, 105, 170, 45)
CHOICE_ROWS = (690, 170, 480, 440)


def imread(path):
    """A PNG as BGR, also from a path with non-ASCII characters (cv2.imread cannot open those on Windows)."""
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


@cache
def template(name):
    """A template by its lc-helper name: the package's image when maalc supplies it (package.TEMPLATES), else the one
    lc-helper cut itself (assets/templates)."""
    return imread(package.path(package.TEMPLATES[name]) if name in package.TEMPLATES else ASSETS / "templates" / name)


def crop(image, roi):
    x, y, w, h = roi
    return image[max(y, 0):y + h, max(x, 0):x + w]


@cache
def green_mask(name):
    """MaaFramework's green_mask: the template's pure green pixels (0, 255, 0) take no part in the match."""
    t = template(name)
    return np.where((t == (0, 255, 0)).all(axis=2, keepdims=True), 0, 255).astype(np.uint8).repeat(3, axis=2)


def find(image, name, roi, threshold=MATCH, masked=False):
    """The best match of template name inside roi as (x, y, w, h), or None under threshold."""
    t = template(name)
    area = crop(image, roi)
    if area.shape[0] < t.shape[0] or area.shape[1] < t.shape[1]:
        return None
    scores = cv2.matchTemplate(area, t, cv2.TM_CCOEFF_NORMED, mask=green_mask(name) if masked else None)
    scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    if best < threshold:
        return None
    return (max(roi[0], 0) + x, max(roi[1], 0) + y, t.shape[1], t.shape[0])


# The Win Rate label's looks, plain, pressed and (LLC) lit by the picks. The LLC client writes 胜率 on the same plate at
# the same place (tools/make_templates.py cuts it so), so every tap offset from the label holds in both languages.
TURN_LABELS = ("battle_turn.png", "battle_turn_pressed.png", "battle_turn_llc.png", "battle_turn_llc_pressed.png",
               "battle_turn_llc_lit.png")
# The plate between the label's text and its triangle, red channel: 55-62 plain in both languages, 115-243 pressed or
# lit (maalc's 17 turn captures, where it agrees with the pressed template on every one, and the LLC probe of
# 2026-11-14). The templates cannot tell it in Chinese: TM_CCOEFF_NORMED evens out brightness, and the plain and pressed
# 胜率 score 0.975 against each other.
PRESSED_PLATE = (44, 6, 6, 16)  # x, y, w, h from the label's top-left
PRESSED_RED = 95


def battle_turn(image):
    """The Win Rate label's box when a turn waits for input, else None."""
    return next(filter(None, (find(image, name, BATTLE_TURN_ROI) for name in TURN_LABELS)), None)


def win_rate_on(image, box):
    """Whether the Win Rate label at box shows pressed: its plate turns bright red."""
    dx, dy, w, h = PRESSED_PLATE
    return float(crop(image, (box[0] + dx, box[1] + dy, w, h))[..., 2].mean()) > PRESSED_RED


def turn_playing(image):
    return find(image, "battle_pause.png", BATTLE_PAUSE_ROI) is not None


def battle_menu(image):
    """Whether the battle menu (Settings, Resume, Retry Stage, Give Up) is open over the turn."""
    return any(find(image, "battle_menu_resume.png", roi) is not None for roi in BATTLE_MENU_ROIS)


def popup(image):
    """Whether a popup sits over the battle: CONNECTING, or a dialog with a button (maalc BATTLE_POPUPS)."""
    return (find(image, "connecting.png", CONNECTING_ROI, masked=True) is not None
            or find(image, "dialog_button.png", DIALOG_BUTTON_ROI) is not None)


def turn_page(image):
    """Whether a turn waits for input with nothing over it: the screen the battle taps are meant for."""
    return battle_turn(image) is not None and not battle_menu(image) and not popup(image)


def start_disc(box):
    return box[0] + START_DISC[0], box[1] + START_DISC[1]


def start_shown(image, disc):
    """Whether the START plaque hangs over the disc: the game shows it only once every slot has a skill.

    maalc #145: the plaque template scored 0.58-1.0 with it and 0.20-0.35 without it on 431 screens.
    """
    x, y = disc
    return find(image, "battle_start.png", (x - 45, y - 75, 95, 45), threshold=0.5) is not None


def disc_lit(image, disc):
    """Whether the START disc is lit: the brightest channel's mean in a 20 px square (unlit 128-142, lit ~254)."""
    x, y = disc
    return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)


def slot_xs(win_rate_x):
    """x of each skill slot's portrait, from the Win Rate label's x.

    maalc live 2026-10-16: the slots are 81 px apart and centred on x 605; each extra slot moves the
    label half a step right (7 slots: x 984, 8: 1020, 9: 1060).
    """
    n = 7 + round((win_rate_x - 984) / 40.5)
    return [round(605 + 81 * (i - (n - 1) / 2)) for i in range(max(n, 0))]


def thumb(image):
    """A grey thumbnail: each 40x40 block's mean brightness."""
    h, w = image.shape[0] // 40 * 40, image.shape[1] // 40 * 40
    return image[:h, :w].reshape(h // 40, 40, w // 40, 40, -1).mean(axis=(1, 3, 4))


def same_screen(a, b, share=0.03):
    """Whether two thumbnails show the same screen: under share of the blocks moved by more than 8 levels."""
    return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 8).mean() < share


def grey(image, roi):
    """roi of image in grey levels."""
    return crop(image, roi).mean(axis=2)


# The share of a grey crop's pixels that may move by over 40 levels while it shows the same thing. maalc captures,
# 2026-11-14: the Choices header moved at most 2.9% between the five Choices pages, 19% to the result page and 29% or
# more to every other capture (tests/test_vision.py).
PATCH_MOVED = 0.05


def same_patch(a, b, share=PATCH_MOVED):
    """Whether two grey crops (grey) show the same thing: under share of their pixels moved by more than 40 levels."""
    return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 40).mean() < share


# The share of hud_band's blocks that may move on a turn screen at rest. maalc live 2026-10-21 (#229): at most 6.9%
# over 319 pairs of a swarm battle, 62-94% as each turn started.
HUD_MOVED = 0.2


def hud_band(box):
    """(x, y, w, h) of the HUD that rests on a turn screen: from the left gear to the Win Rate label's right edge."""
    x, _, w, _ = box
    left = (slot_xs(x) or [605])[0] - 86 - 40
    return left, 560, -(-(x + w - left) // 40) * 40, 160


def hud_still(before, after, box):
    """Whether the turn HUD looks the same in two screenshots taken ~0.2 s apart."""
    band = hud_band(box)
    return same_screen(thumb(crop(before, band)), thumb(crop(after, band)), HUD_MOVED)


def lower_x(x):
    """x of a slot's lower skill: the skill rows lean in towards the middle (x ~604) by about 6%."""
    return round(x + (604 - x) * 0.06)


def guard_chain(xs, staggered=None):
    """The points of the drag that picks every slot's lower skill, left to right.

    maalc live 2026-10-16: the chain starts only on the left gear, 90 px left of the first slot at y 557.
    Once the finger is down the panel tilts and the lower skills sit at y ~665, so the drag runs along y 665.
    A staggered slot has no skill to pick: it is no point of the drag.
    """
    staggered = staggered or [False] * len(xs)
    return [(xs[0] - 90, 557)] + [(x, 665) for x, s in zip(xs, staggered) if not s]


def guard_score(image, x):
    """(brown, texture) at a lower skill; guard icons are flat brown (~(150, 100, 50) RGB)."""
    p = image[LOWER_Y - 14:LOWER_Y + 14, x - 14:x + 14].astype(int)
    b, g, r = p[..., 0], p[..., 1], p[..., 2]
    v = p.sum(axis=2)
    texture = np.abs(np.diff(v, axis=0)).mean() + np.abs(np.diff(v, axis=1)).mean()
    return float(((r > 90) & (r - g > 20) & (g - b > 10)).mean()), float(texture)


def guard_shown(before, after):
    """Per slot, whether its lower skill shows the guard skill after a portrait tap swapped it; None when unsure.

    Texture decides (maalc live: the guard side is 11-65% flatter); brown only breaks a tie.
    """
    shown = []
    for (b0, t0), (b1, t1) in zip(before, after):
        if t1 < t0 * 0.93 or t1 > t0 * 1.07:
            shown.append(t1 < t0)
        elif abs(b1 - b0) >= 0.1:
            shown.append(b1 > b0)
        else:
            shown.append(None)
    return shown


STAGGER_AT, STAGGER_SLIDE = (-23, 649), (12, 4)
STAGGER_MATCH = 0.6
BGR_LUMA = np.array([0.114, 0.587, 0.299])


@cache
def stagger_word():
    word = template("stagger_word.png") @ BGR_LUMA
    return word - word.mean()


def stagger_score(image, x):
    """The best normalised cross-correlation of the greyscale word STAGGER round where it sits on slot x's plate."""
    word = stagger_word()
    (dx, top), (sx, sy) = STAGGER_AT, STAGGER_SLIDE
    left = x + dx
    roi = image[top - sy:top + word.shape[0] + sy, left - sx:left + word.shape[1] + sx] @ BGR_LUMA
    windows = np.lib.stride_tricks.sliding_window_view(roi, word.shape)
    dot = np.einsum("ijkl,kl->ij", windows, word)
    spread = (windows ** 2).sum(axis=(2, 3)) - windows.sum(axis=(2, 3)) ** 2 / word.size
    flat = spread < word.size
    return float(np.where(flat, 0, dot / np.sqrt(np.where(flat, 1, spread) * (word ** 2).sum())).max())


def staggered(image, xs):
    """Per slot, whether its unit is staggered (acts no skill this turn).

    maalc: 0.86-1.00 on its 10 plates, 0.42 at most on 4544 other slot positions of 198 screens.
    """
    return [stagger_score(image, x) > STAGGER_MATCH for x in xs]


RING_ANGLES = np.linspace(0, 2 * np.pi, 72, endpoint=False)


def gear_hollow(image, box):
    """Whether the left gear shows the hollow ring of a focused encounter, where no guard chain can start.

    maalc live 2026-10-18 (#127): the ring 0.79-0.83, the gear 0.06-0.14 (glowing once chained 0.29).
    """
    x, y = slot_xs(box[0])[0] - 86, 576
    v = image.astype(float).mean(axis=2)
    r = np.arange(6, 31)[:, None]
    best = 0.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            circles = v[np.round(y + dy + r * np.sin(RING_ANGLES)).astype(int),
                        np.round(x + dx + r * np.cos(RING_ANGLES)).astype(int)]
            best = max(best, circles.mean(axis=1).var() / (circles.var(axis=1).mean() + 1))
    return bool(best > 0.5)


# The shop's fuse page: its centre slot (maalc FUSE_CENTRE taps it at 365, 340) shows the gift a fixed recipe makes, its
# picture centred at (367, 347) on ShopFuseRecipe.png and ShopFuseRecipeTwo.png. Each fusion gift's picture (the
# package's data/gift_icons) squeezed to 78 px square, its alpha over 128 the mask, matched within 20 px of there: the
# right gift scores 0.889 and 0.801, the next gift 0.34 at most; with no recipe met (ShopFuse.png, ShopFuseAvailable.png,
# ShopFuseLocked.png) and under the Fusion Recipes popup (ShopFusionRecipes.png) the best gift scores 0.455. At 76 and
# 80 px the second capture drops to 0.734 and 0.722, at 84 to 0.446 (2026-11-19).
FUSE_PICTURE, FUSE_SIDE, FUSE_SLACK = (367, 347), 78, 20
FUSE_MATCH, FUSE_LEAD = 0.6, 0.1  # the best's floor and its lead over the next: maalc gift_cells' ICON_MIN, ICON_MARGIN


@cache
def gift_template(gift_id):
    """Gift gift_id's picture as the fuse page's centre shows it, FUSE_SIDE px square: (BGR, mask)."""
    picture = cv2.imdecode(np.fromfile(str(package.path(f"data/gift_icons/{gift_id}.webp")), np.uint8),
                           cv2.IMREAD_UNCHANGED)
    picture = cv2.resize(picture, (FUSE_SIDE, FUSE_SIDE), interpolation=cv2.INTER_AREA)
    mask = np.where(picture[..., 3:] > 128, 255, 0).astype(np.uint8).repeat(3, axis=2)
    return np.ascontiguousarray(picture[..., :3]), mask


def fused_gift(image, gift_ids) -> tuple[int, Box] | None:
    """(id, picture box) of the gift among gift_ids that the fuse page's centre slot shows, or None: the best match
    when it reaches FUSE_MATCH and leads the next by FUSE_LEAD (a tie is two lookalikes, not a gift)."""
    x, y = FUSE_PICTURE[0] - FUSE_SIDE // 2 - FUSE_SLACK, FUSE_PICTURE[1] - FUSE_SIDE // 2 - FUSE_SLACK
    area = crop(image, (x, y, FUSE_SIDE + 2 * FUSE_SLACK, FUSE_SIDE + 2 * FUSE_SLACK))
    ranked = []
    for gift_id in gift_ids:
        picture, mask = gift_template(gift_id)
        scores = cv2.matchTemplate(area, picture, cv2.TM_CCOEFF_NORMED, mask=mask)
        _, best, _, at = cv2.minMaxLoc(np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0))
        ranked.append((best, gift_id, at))
    ranked.sort(reverse=True)
    if not ranked or ranked[0][0] < FUSE_MATCH or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < FUSE_LEAD):
        return None
    _, gift_id, (dx, dy) = ranked[0]
    return gift_id, (x + dx, y + dy, FUSE_SIDE, FUSE_SIDE)
