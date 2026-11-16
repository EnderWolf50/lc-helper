"""The pictures lc-helper reads out of the fetched resource package: keyword icons, gift icons, templates."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from lc_helper import gifts, icons, package, vision  # noqa: E402

KEYWORDS = ["Bleed", "Blunt", "Burn", "Charge", "Pierce", "Poise", "Rupture", "Sinking", "Slash", "Tremor"]


@pytest.fixture(scope="module", autouse=True)
def qt():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.mark.parametrize("name", KEYWORDS)
def test_every_keyword_has_the_games_icon(name):
    assert not icons.game_icon(name).isNull()


def test_a_keywordless_gift_has_no_game_icon_and_gets_the_ring():
    assert icons.game_icon("Keywordless").isNull()


def test_every_gift_has_its_picture():
    missing = [i for i in gifts.book() if icons.gift_picture(i).isNull()]
    assert missing == []


def test_a_template_of_the_package_and_one_lc_helper_cut_itself_both_load():
    assert vision.template("battle_turn.png").shape[2] == 3  # image/Battle/BattleTurn.png of the package
    assert vision.template("wipe_text.png").shape[2] == 3  # assets/templates, cut from a capture
    assert vision.template("stagger_word.png").size  # data/stagger_word.png of the package


def test_every_template_name_the_package_supplies_is_a_file_of_it():
    for relative in package.TEMPLATES.values():
        assert package.path(relative).is_file()
