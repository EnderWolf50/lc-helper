import re
import time

import pytest

from lc_helper import gifts, ocr
from lc_helper.device import Target
from lc_helper.worker import Callbacks, Worker


def read(image, roi, only_rec):
    return [t for t, _ in ocr.lines(image, roi, only_rec=only_rec)]


def test_every_gift_has_its_effect_in_both_languages():
    book = gifts.book()
    assert len(book) >= 400
    assert all(g["desc_en"] and g["desc_zh"] and g["en"] for g in book.values())
    left = re.findall(r"\[[A-Za-z_]+\]", "".join(g["desc_en"] + g["desc_zh"] for g in book.values()))
    assert left == []  # buff ids are named (「Burn」), not left as [Combustion]


def test_gifts_are_found_by_chinese_or_english_name():
    assert gifts.search("地獄蝶")[0]["en"] == "Hellterfly's Dream"
    assert gifts.search("hellterfly")[0]["zh"] == "地獄蝶之夢"
    assert gifts.by_name("Hellterflys Dream")["id"] == 9001  # OCR drops the apostrophe
    assert gifts.by_name("Turn Start: When dealing") is None


# The gifts on each of maalc's gift screens, left to right (the boss trial ids: maalc tests/test_trial_screens.py).
SHOWN = {
    "GiftChoice.png": ("choice", ["Eclipse of Scarlet Moths"]),
    "GiftChoiceNoCount.png": ("choice", ["Clasped Sculpture", "First-aid Kit"]),
    "BossGiftTrials.png": ("choice", ["Broken Revolver", "Twinkling Scrap", "Ashes to Ashes"]),
    "BossGiftTrialsHard.png": ("choice", ["Melted Spring", "Talisman Bundle", "Rusted Muzzle", "Hellterfly's Dream"]),
    "GiftGet.png": ("get", ["Wound Clerid"]),
    "GiftGetOverMap.png": ("get", ["Rusty Commemorative Coin"]),
}


@pytest.mark.parametrize("name", SHOWN)
def test_the_gifts_on_screen_are_read(screen, name):
    image = screen(name)
    page = gifts.gift_page(image, read)
    reading = gifts.read_gifts(image, page, ocr.lines)
    assert (page, [g["en"] for g, _ in reading.gifts]) == SHOWN[name]


@pytest.mark.parametrize("name", ["EventChoices.png", "BattleTurn.png", "MirrorMap.png", "Victory.png"])
def test_other_screens_are_no_gift_screen(screen, name):
    assert gifts.gift_page(screen(name), read) is None


class Still:
    can_hold = True

    def __init__(self, image):
        self.image = image

    def screenshot(self):
        return self.image


def test_auto_read_shows_a_gift_screen_once(screen):
    shown = []
    w = Worker(Callbacks(gifts=shown.append), connect=lambda address, **_: (Still(screen("GiftGet.png")), Target("f", "x")),
               find=lambda: [])
    w.start()
    w.send("set_watch", True)
    end = time.monotonic() + 20
    while not shown and time.monotonic() < end:
        time.sleep(0.05)
    time.sleep(2.2)  # two more looks at the same window
    assert [[g["en"] for g, _ in r.gifts] for r in shown] == [["Wound Clerid"]]
    assert shown[0].source == "x"
