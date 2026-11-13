import pytest

from lc_helper import gifts, ocr, trials

# maalc's post-boss captures, labelled by eye in maalc's tests/test_trial_screens.py: (card centre x, Enemy Level Up N,
# trial, gift id), and how many cards the page takes (Select 0/n).
CARDS = {
    "BossGiftTrials.png": (1, [(374, 1, "Growth II", 9064), (638, 2, "Resilient II", 9707),
                               (904, 1, "Offense Level Up II", 9003)]),
    "BossGiftTrialsHard.png": (2, [(242, 1, "Defense Level Up", 9054), (506, 1, "Defense Skill Up", 9013),
                                   (771, 2, "Take Less Damage", 9089), (1035, 2, "Growth I", 9001)]),
    "BossGiftTrialsFloor3.png": (1, [(375, 2, "Resilient V", 9003), (638, 1, "Final Power Boost", 9047),
                                     (904, 1, "Keen III", 9066)]),
}
OWNED = {("BossGiftTrialsFloor3.png", 904)}  # Nebulizer's card wears the Owned tag


def test_every_trials_text_in_english_and_in_llcs_chinese_reads_as_its_effects():
    """The game's text is what the effect line shows: each phrase of every trial parses to its own effects."""
    for name, t in trials.book()["trials"].items():
        assert set(trials.parse_effects(t["desc_en"])) == set(t["effects"]), (name, t["desc_en"])
        assert set(trials.parse_effects(t["desc_cn"])) == set(t["effects"]), (name, t["desc_cn"])


def test_every_trial_is_told_from_its_own_name_and_text_among_all_of_them():
    """lc-helper does not know the floor: a card is matched against every pool's trials."""
    table = trials.book()["trials"]
    for name, t in table.items():
        assert trials.read_trial(name, t["desc_en"], table)[0] == name
        assert trials.read_trial(t["cn"], t["desc_cn"], table)[0] == name
        assert trials.read_trial(name, "", table) == (name, "name")
        assert trials.read_trial(t["cn"], "", table) == (name, "name")


def test_a_name_read_with_another_numeral_is_not_taken():
    table = trials.book()["trials"]
    assert trials.read_trial("Growth I", "Max HP +10%", table) == ("Growth II", "effects")
    assert trials.read_trial("Growth", "", table) == (None, None)


@pytest.mark.parametrize("name", CARDS)
def test_each_post_boss_card_is_read_with_its_gift_and_trial(screen, name):
    image = screen(name)
    page = trials.read_page(image, ocr.lines, gifts.read_gifts(image, "choice", ocr.lines))
    picks, want = CARDS[name]
    assert page.picks == picks
    assert [(c.level, c.trial, c.gift["id"]) for c in page.cards] == [(n, t, g) for _, n, t, g in want]
    assert all(abs(c.x - x) <= 3 for c, (x, *_) in zip(page.cards, want))
    assert {c.x for c in page.cards if c.owned} == {x for n, x in OWNED if n == name}


def test_a_fights_gift_choice_has_no_trials(screen):
    image = screen("GiftChoice.png")
    assert trials.read_page(image, ocr.lines, gifts.read_gifts(image, "choice", ocr.lines)) is None


def card(x, gift_id, trial, level, owned=False):
    return trials.Card(x, gifts.book()[gift_id], owned, trial, level)


def test_a_card_is_worth_its_gift_less_its_trial_and_the_page_takes_its_best():
    """BossGiftTrialsHard.png with Charge and Sinking as the team's: Melted Spring (Sinking II) and Hellterfly's
    Dream; Rusted Muzzle's Take Less Damage costs more than any gift is worth (maalc: never take it early)."""
    page = trials.TrialPage((card(242, 9054, "Defense Level Up", 1), card(506, 9013, "Defense Skill Up", 1),
                             card(771, 9089, "Take Less Damage", 2), card(1035, 9001, "Growth I", 2)), picks=2)
    worth = trials.worth(page, ["Charge", "Sinking"])
    assert [w.rank for w in worth] == [1, 3, 4, 2] and [w.pick for w in worth] == [True, False, False, True]
    assert [w.gift for w in worth] == [3.5, 2, 2, 2.5]
    assert worth[0].burden == pytest.approx(0.04 + 0.36) and worth[2].total < 0


def test_a_held_gift_scores_nothing_and_an_unread_trial_costs_the_pools_worst_at_level_two():
    page = trials.TrialPage((card(375, 9003, "Resilient V", 2), card(904, 9066, None, None, owned=True)), picks=1)
    held, unread = trials.worth(page, ["Burn"])
    assert held.gift == 3 and unread.gift == 0
    worst = max(t["score"] for t in trials.book()["trials"].values() if t["pool"] == 3)
    assert unread.burden == pytest.approx(worst + 0.36 * 2)
