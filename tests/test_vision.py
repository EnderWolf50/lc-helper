from pathlib import Path

import pytest

from lc_helper import vision
from sweep_screens import sweep

# Every capture in maalc's tests/screens that shows a turn waiting for input (with the battle menu over it for the
# three *Menu* ones, and the Luxcavation defeat field, which keeps the HUD up).
TURN_SCREENS = {
    "BattleMenu.png", "BattleMenuClosing.png", "BattleTurn.png", "BattleTurnEven.png", "BattleTurnFocused.png",
    "BattleTurnLit.png", "BattleTurnSolo.png", "BattleTurnStagger.png", "BattleTurnStaggerLast.png",
    "BattleTurnStaggerPlus.png", "BattleTurnStaggerPlusPlus.png", "BattleTurnSwarm.png", "BattleTurnSwarmNext.png",
    "LuxBattleMenu.png", "LuxBattleTurn.png", "LuxBattleTurnFocused.png", "LuxDefeatField.png",
}
STAGGERED = {"BattleTurnStagger.png": [2, 3, 4, 5, 6, 7], "BattleTurnStaggerLast.png": [9],
             "BattleTurnStaggerPlus.png": [7, 8], "BattleTurnStaggerPlusPlus.png": [3]}


@pytest.fixture(scope="module")
def readings(screens):
    rows = sweep(screens)
    assert len(rows) > 200, "the sweep covers maalc's whole screen set"
    return rows


def test_the_turn_hud_is_found_on_turn_screens_only(readings):
    assert {name for name, r in readings.items() if r["turn"]} == TURN_SCREENS


def test_the_pause_button_shows_on_the_playing_turn_only(readings):
    assert {name for name, r in readings.items() if r["playing"]} == {"BattlePause.png"}


def test_staggered_slots_are_the_plates_on_screen(readings):
    assert {name: r["staggered"] for name, r in readings.items() if r.get("staggered")} == STAGGERED


def test_the_battle_menu_is_told_from_the_turn(screen):
    from lc_helper import vision
    assert vision.battle_menu(screen("BattleMenu.png"))
    assert not vision.battle_menu(screen("BattleTurn.png"))


def test_menus_and_popups_are_told_apart_from_turns(readings):
    assert {n for n, r in readings.items() if r["menu"]} == {"BattleMenu.png", "BattleMenuClosing.png", "LuxBattleMenu.png"}
    popups = {n for n, r in readings.items() if r["popup"]}
    assert popups and not popups & (TURN_SCREENS | {"BattlePause.png"})


def test_the_end_of_a_battle_shows_on_its_own_captures_only(readings):
    assert {n for n, r in readings.items() if r["victory"]} == {"Victory.png"}
    assert {n for n, r in readings.items() if r["wiped"]} == {"WipeDialog.png"}


LLC_SCREENS = Path(__file__).resolve().parent / "screens_llc"


def llc(name):
    return vision.imread(LLC_SCREENS / name)


def test_the_victory_banner_is_seen_through_its_fade_on_the_pc_client():
    """Live probe 2026-11-14: the banner bright for one look, darkened 0.53 s later, gone after another 0.36 s."""
    assert vision.victory(llc("LlcVictory.png")) and vision.victory(llc("LlcVictoryFading.png"))
    assert not vision.victory(llc("LlcVictoryGone.png"))


def test_an_llc_client_turn_is_found_where_its_chinese_label_sits():
    """The PC client with LLC writes 胜率 where maalc's template reads Win Rate; with 6 and 8 slots the label moves."""
    assert vision.battle_turn(llc("LlcBattleTurn6.png")) == (946, 531, 40, 29)
    assert vision.battle_turn(llc("LlcBattleTurn8.png")) == (1022, 531, 40, 29)
    for name in ("LlcBattleTurn6.png", "LlcBattleTurn8.png"):
        assert vision.turn_page(llc(name)), name


def test_an_llc_client_mid_turn_is_no_turn_to_play():
    assert vision.battle_turn(llc("LlcBattlePlaying.png")) is None and vision.turn_playing(llc("LlcBattlePlaying.png"))
    assert vision.battle_turn(llc("LlcBattleMoves.png")) is None


def test_the_slots_of_an_llc_turn_are_where_their_portraits_are():
    """The slot count follows the label's x as on maalc's captures: 6 and 8 portraits on these two."""
    assert len(vision.slot_xs(vision.battle_turn(llc("LlcBattleTurn6.png"))[0])) == 6
    assert len(vision.slot_xs(vision.battle_turn(llc("LlcBattleTurn8.png"))[0])) == 8


def test_an_llc_label_pressed_or_lit_is_still_the_turn_and_reads_pressed():
    """Live probe 2026-11-14: 胜率 tapped, then the picks lighting START (its plaque's arm over the label's end)."""
    for name in ("LlcBattleTurnPressed.png", "LlcBattleTurnLit.png"):
        box = vision.battle_turn(llc(name))
        assert box == (946, 531, 40, 29), name
        assert vision.win_rate_on(llc(name), box), name
    plain = llc("LlcBattleTurnProbe.png")
    assert not vision.win_rate_on(plain, vision.battle_turn(plain))
