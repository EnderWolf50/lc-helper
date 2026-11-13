import llc_screen
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


def test_every_event_is_found_from_its_own_simplified_text_and_twins_come_together():
    for e in events.book()["events"]:
        if e["page"]:
            continue
        found = events.candidates(e["story_cn"], [o["text_cn"] for o in e["options"]])
        assert e in found, e["id"]
        for other in found:
            assert [o["text_cn"] for o in other["options"]] == [o["text_cn"] for o in e["options"]], (e["id"],
                                                                                                    other["id"])
    for a, b in [(971098, 971099), (971105, 971107)]:  # read the same in English and in LLC's Chinese
        twin = events.by_id()[a]
        assert {e["id"] for e in events.candidates(twin["story_cn"], [o["text_cn"] for o in twin["options"]])} == {a, b}


def test_a_story_end_read_in_simplified_finds_its_event_and_options_alone_do_too():
    story = "本以为是手掌，但那实际上是黑色的石头 手掌的指尖，又伸出新的手掌与手指 它用那指尖的手，朝向我。"
    assert events.match_screen(story)["id"] == 901069
    assert events.match_screen("", ["和它握手。", "推开手。"])["id"] == 901069


def test_a_chinese_character_slipped_into_an_english_read_keeps_it_english():
    story = "What looked like palms are made of black rocks. It reaches out with the hand of the hand. 口"
    assert events.match_screen(story, ["Shake hands.", "Push the hand away."])["id"] == 901069


def test_each_simplified_option_is_found_at_its_own_line():
    for e in events.book()["events"]:
        options = [o for o in e["options"] if o["text_cn"]]
        lines = [line for i, o in enumerate(options) for line in [(o["text_cn"], (733, 200 + 100 * i, 300, 24))] + (
            [(o["hint_cn"], (733, 230 + 100 * i, 300, 20))] if o["hint_cn"] else [])]
        rows = events.option_rows(e, lines)
        assert [(o, box[1]) for o, box in rows] == [(o, 200 + 100 * i) for i, o in enumerate(options)], e["id"]


@pytest.mark.parametrize("name", CHOICES_PAGES)
def test_every_choices_page_painted_in_llc_chinese_reads_as_its_english_capture(screen, name):
    image = screen(name)
    english = events.read_screen(image)
    painted = llc_screen.choices_page(image)
    assert events.on_choices_page(painted)
    reading = events.read_screen(painted)
    assert reading.event == english.event, reading
    rows = [(o["text"], box[1]) for o, box in events.option_rows(reading.event, reading.lines)]
    want = [(o["text"], box[1]) for o, box in events.option_rows(english.event, english.lines)]
    assert [text for text, _ in rows] == [text for text, _ in want]
    assert all(abs(y - wy) <= 5 for (_, y), (_, wy) in zip(rows, want)), (rows, want)
    assert reading.closed == english.closed


def test_a_gift_a_branch_names_gets_no_second_line_that_contradicts_it():
    take = events.by_id()[971105]["options"][0]
    assert [(e.when, e.what) for e in events.effects(take)] == [
        ("判定失敗", "開始戰鬥、戰鬥勝利獲得 「萬物的骨架」（流血 II）")]


def test_a_simplified_query_finds_events_by_their_llc_text():
    """A player on an LLC client types what the game shows: Simplified text, which today's Traditional-only search
    can miss outright (镜像迷宫里见过的 found nothing)."""
    assert events.search("镜像迷宫里见过的")[0]["id"] == 130802
    assert events.search("交織而成的蜘蛛巢")[0]["id"] == 901028
