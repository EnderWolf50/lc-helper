from lc_helper.battle import FOREVER, AutoBattle, Phase, Pick, Plan
from fake_game import DAMAGE_AT, WIN_RATE_AT, FakeBattle, VirtualClock


def play(screen, plan, hold=True, **game):
    clock = VirtualClock()
    fake = FakeBattle(screen, clock, **game)
    statuses = []
    bot = AutoBattle(fake, plan, fake.stop, statuses.append, clock=clock, hold=hold)
    bot.run()
    return fake, statuses


def test_win_rate_plays_every_turn_until_the_battle_ends(screen):
    fake, statuses = play(screen, Plan(Pick.WIN_RATE), turns=3)
    assert fake.starts() == ["win_rate"] * 3
    assert statuses[-1].phase is Phase.STOPPED and statuses[-1].turns == 3


def test_damage_taps_the_damage_label(screen):
    fake, _ = play(screen, Plan(Pick.DAMAGE), turns=2)
    assert fake.starts() == ["damage"] * 2
    assert WIN_RATE_AT not in fake.taps and DAMAGE_AT in fake.taps


def test_guard_turns_come_first_then_the_pick_takes_over(screen):
    fake, statuses = play(screen, Plan(Pick.DAMAGE, guard=2), turns=4)
    assert fake.starts() == ["guard", "guard", "damage", "damage"]
    assert statuses[-1].plan.guard == 0


def test_guard_forever_guards_every_turn(screen):
    fake, statuses = play(screen, Plan(Pick.WIN_RATE, guard=FOREVER), turns=3)
    assert fake.starts() == ["guard"] * 3
    assert statuses[-1].plan.guard == FOREVER


def test_a_focused_encounter_keeps_its_guard_turns_for_a_later_battle(screen):
    fake, statuses = play(screen, Plan(Pick.WIN_RATE, guard=2), turns=2, turn_image="BattleTurnFocused.png")
    assert fake.starts() == ["win_rate"] * 2
    assert statuses[-1].plan.guard == 2
    assert any("專注戰鬥" in s.note for s in statuses)


def test_a_finger_holds_each_turn_only_when_asked(screen):
    held, _ = play(screen, Plan(), turns=2)
    not_held, _ = play(screen, Plan(), hold=False, turns=2)
    assert held.log.count("hold") == 2
    assert "hold" not in not_held.log


def test_the_battle_menu_is_never_tapped(screen):
    fake, statuses = play(screen, Plan(), turns=1, turn_image="BattleMenu.png", max_shots=40)
    assert fake.taps == [] and fake.starts() == []
    assert Phase.MENU in [s.phase for s in statuses]


def test_the_luxcavation_battle_menu_is_never_tapped(screen):
    fake, statuses = play(screen, Plan(Pick.WIN_RATE, guard=2), turns=1, turn_image="LuxBattleMenu.png", max_shots=40)
    assert fake.taps == [] and fake.log == []
    assert Phase.MENU in [s.phase for s in statuses]


def test_taps_stop_when_the_menu_opens_mid_turn(screen):
    fake, _ = play(screen, Plan(), turns=1, menu_after_pick=True, max_shots=60)
    assert fake.taps == [WIN_RATE_AT]


def test_the_finger_lifts_when_a_popup_covers_the_playing_turn(screen):
    fake, _ = play(screen, Plan(), turns=1, play_s=5.0, popup_while_playing=True, max_shots=200)
    assert fake.holds and all(up - down < 1.0 for down, up in fake.holds)


def test_it_stops_when_start_starts_no_turn(screen):
    fake, statuses = play(screen, Plan(), turns=5, start_works=False, max_shots=10_000)
    assert fake.starts() == []
    assert statuses[-1].phase is Phase.STOPPED and "START" in statuses[-1].note
