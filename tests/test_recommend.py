from lc_helper import events, recommend


def opt(text, hint, kind, *gifts):
    return {"text": text, "hint": hint, "kind": kind, "gift_keywords": [list(g) for g in gifts]}


# maalc tests/test_rewards.py RANKED: AALC's order, best last.
RANKED = [
    opt("Leave.", "", "other"),
    opt("Read it.", "Run a Wrath check to gain an E.G.O Gift.", "check_fail_gift", ("Burn", "check_fail")),
    opt("Fight.", "Win the battle to earn a Burn E.G.O Gift", "battle", ("Burn", "win_battle")),
    opt("Wait.", "Then, maybe gain a Bleed E.G.O Gift depending on the subsequent choice", "followup", ("Bleed", "later_direct")),
    opt("Open it.", "Lust check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass")),
    opt("Take it.", "Select to gain a Bleed E.G.O Gift", "direct", ("Bleed", "direct")),
    opt("Hold it.", "Select to gain a Burn E.G.O Gift", "direct", ("Burn", "direct")),
    opt("Insert the coin.", "???", "random", ("Keywordless", "direct_random")),
]


def pick(event_options, keyword, closed=()):
    found = recommend.best({"options": event_options}, keyword, closed)
    return event_options.index(found[0]) if found else None


def test_options_rank_as_maalc_ranks_them():
    # maalc test_pick_choice_ranks_by_the_event_table, case by case
    texts = [o["text"] for o in RANKED]
    for best in range(len(RANKED) - 1, 2, -1):
        assert pick(RANKED, "Burn", texts[best + 1:]) == best
    assert pick(RANKED, "Burn", texts[3:]) == 0  # a battle or a gift only a failed check gives: the rest
    assert pick(RANKED, "Bleed") == 7  # the main keyword never lifts an option across tiers
    assert pick(RANKED, "Burn", {texts[7]}) == 6
    assert pick(RANKED, "Bleed", {texts[7]}) == 5
    assert pick(RANKED, "Burn", set(texts[5:])) == 4


def test_a_check_whose_hint_says_depending_on_ranks_with_the_follow_ups():
    depending = opt("Alert it.", "Gain a Bleed E.G.O Gift depending on the result of the following choice", "check",
                    ("Bleed", "check_pass"))
    plain = opt("Pull.", "Wrath check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass"))
    assert pick([depending, plain], "Bleed") == 1
    assert pick([plain, depending], "Bleed") == 0


def test_no_keyword_no_recommendation_and_why_is_told():
    assert recommend.best({"options": RANKED}, None) is None
    option, why = recommend.best({"options": RANKED}, "Burn", {"Insert the coin."})
    assert option["text"] == "Hold it." and why == "直接獲得飾品，有燒傷飾品"


def test_every_event_in_the_table_gets_a_pick():
    for event in events.book()["events"]:
        if any(o["text"] for o in event["options"]):
            assert recommend.best(event, "Burn") is not None, event["id"]


def test_a_grey_option_on_screen_is_closed(screen):
    reading = events.read_screen(screen("EventChoicesUsed.png"))
    assert reading.closed == ("What if you do feel like what you did was wrong?",)
    assert events.read_screen(screen("EventChoices.png")).closed == ()
