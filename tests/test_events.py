import pytest

from lc_helper import events

CHOICES_PAGES = ["EventChoices.png", "EventChoicesLitBottom.png", "EventChoicesLitTop.png",
                 "EventChoicesScrolledBack.png", "EventChoicesUsed.png"]


def test_typed_text_finds_the_event_in_english_or_chinese():
    assert events.search("Push the hand away")[0]["id"] == 901069
    assert events.search("palms are made of black rocks")[0]["id"] == 901069
    assert events.search("螺旋")[0]["id"] == 901002


def test_a_story_end_finds_its_event_and_options_alone_do_too():
    story = ("What looked like palms are made of black rocks. At the tip of the fingers attached to the palms are "
             "smaller palms and smaller fingers. It reaches out with the hand of the hand.")
    assert events.match_screen(story)["id"] == 901069
    assert events.match_screen("", ["Shake hands.", "Push the hand away."])["id"] == 901069
    assert events.match_screen("", ["Nothing on this page matches any option"]) is None


def test_every_option_of_the_table_says_what_it_does():
    for e in events.book()["events"]:
        for o in e["options"]:
            for line in events.effects(o):
                assert line.when and line.what


def test_a_check_says_what_passing_gives_and_failing_costs():
    push = events.by_id()[901069]["options"][1]
    lines = {(e.when, e.what) for e in events.effects(push)}
    assert ("判定成功獲得", "「護腕」（充能 I）") in lines
    assert ("判定失敗", "HP -11（判定的罪人）、SP -11（判定的罪人）") in lines


@pytest.mark.parametrize("name", CHOICES_PAGES)
def test_every_choices_page_capture_is_read_to_an_event(screen, name):
    image = screen(name)
    assert events.on_choices_page(image)
    reading = events.read_screen(image)
    assert reading.event is not None, reading
    on_screen = {events.key(o["text"]) for o in reading.event["options"]}
    assert any(events.key(t) in on_screen for t in reading.options)


@pytest.mark.parametrize("name", ["BattleTurn.png", "MirrorMap.png", "EventStory.png", "EventCheck.png"])
def test_other_screens_are_no_choices_page(screen, name):
    assert not events.on_choices_page(screen(name))


def test_every_event_is_found_from_its_own_text_and_twins_come_together():
    for e in events.book()["events"]:
        if e["page"]:
            continue
        found = events.candidates(e["story"], [o["text"] for o in e["options"]])
        assert e in found, e["id"]
        for other in found:
            assert [o["text"] for o in other["options"]] == [o["text"] for o in e["options"]], (e["id"], other["id"])


def test_a_gift_a_branch_names_gets_no_second_line_that_contradicts_it():
    take = events.by_id()[971105]["options"][0]
    assert [(e.when, e.what) for e in events.effects(take)] == [
        ("判定失敗", "開始戰鬥、戰鬥勝利獲得 「萬物的骨架」（流血 II）")]
