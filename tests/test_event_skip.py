import time

import llc_screen
import pytest

from lc_helper import event_skip, ocr
from lc_helper.device import Target
from lc_helper.event_skip import EVENT_BUTTON, EVENT_CARD, EVENT_NEUTRAL, Skipper
from lc_helper.worker import Callbacks, Worker


def read(image, roi, only_rec):
    return [t for t, _ in ocr.lines(image, roi, only_rec=only_rec)]


# What one look at each of maalc's event captures does: press the lit button, open a lone check card, show the next
# line of text, or leave the screen to the player.
ACTS = {
    "EventStory.png": ("press", EVENT_BUTTON),
    "EventResult.png": ("press", EVENT_BUTTON),  # Continue
    "LuxEventContinue.png": ("press", EVENT_BUTTON),
    "LuxEventPassed.png": ("press", EVENT_BUTTON),
    "LuxEventText.png": ("text", EVENT_NEUTRAL),  # the button grey while the text runs
    "LuxEventCard.png": ("card", EVENT_CARD),
}
LEAVES = ["EventChoices.png", "EventChoicesUsed.png", "EventCheck.png", "LuxEventCheck.png", "LuxEventCommence.png",
          "MapEvent.png", "MirrorMap.png", "BattleTurn.png", "GiftGet.png", "EventNotices.png"]


@pytest.mark.parametrize("name", ACTS)
def test_the_story_is_pushed_on(screen, name):
    assert Skipper(read).step(screen(name), 0.0) == ACTS[name]


@pytest.mark.parametrize("name", LEAVES)
def test_choices_checks_commence_and_other_screens_are_left_alone(screen, name):
    what, point = Skipper(read).step(screen(name), 0.0)
    assert point is None, what


@pytest.mark.parametrize("name", ACTS)
def test_the_story_is_pushed_on_in_llc_chinese(screen, name):
    assert Skipper(read).step(llc_screen.event_page(screen(name)), 0.0) == ACTS[name]


# Why one look at an event capture painted in LLC's Chinese leaves it to the player.
LEAVES_IN_CHINESE = {
    "EventChoices.png": "到選項頁了，請你選",  # 选项
    "EventChoicesUsed.png": "到選項頁了，請你選",
    "EventCheck.png": "判定要選罪人，請你選",  # 选择一位罪人来进行判定：
    "LuxEventCheck.png": "判定要選罪人，請你選",
    "LuxEventCommence.png": "按 Commence 開始判定（請你按）",  # 进行判定, lit
}


@pytest.mark.parametrize("name", LEAVES_IN_CHINESE)
def test_choices_checks_and_commence_in_llc_chinese_are_left_to_the_player(screen, name):
    assert Skipper(read).step(llc_screen.event_page(screen(name)), 0.0) == (LEAVES_IN_CHINESE[name], None)


def test_a_lit_button_is_not_pressed_again_while_its_press_takes(screen):
    skipper, story = Skipper(read), screen("EventStory.png")
    assert skipper.step(story, 0.0)[1] == EVENT_BUTTON
    assert skipper.step(story, 1.0)[1] is None
    assert skipper.step(story, 1.6)[1] == EVENT_BUTTON  # lit 1.5 s on: the press was lost


class Recorder:
    can_hold = True

    def __init__(self, image):
        self.image, self.taps = image, []

    def screenshot(self):
        return self.image

    def tap(self, x, y):
        self.taps.append((x, y))


def test_the_worker_skips_only_while_asked(screen):
    story, choices = Recorder(screen("EventStory.png")), Recorder(screen("EventChoices.png"))
    said = []
    for device in (story, choices):
        w = Worker(Callbacks(skip=said.append), connect=lambda address, d=device, **_: (d, Target("fake", "x")),
                   find=lambda: [])
        w.start()
        w.send("set_skip", True)
        time.sleep(2.5)
        w.send("set_skip", False)
        time.sleep(0.5)
        w.shutdown()
    assert story.taps and set(story.taps) == {EVENT_BUTTON}
    assert choices.taps == []
    assert "到選項頁了，請你選" in said


def lines_shown(image):
    """image with one more line of story text in the story box: what a corner tap on a running text shows."""
    shown = image.copy()
    shown[505:525, 77:560] = 230
    return shown


def test_corner_taps_stop_once_the_screen_stops_answering_them_and_go_on_when_it_changes(screen):
    """An event page the skipper does not recognise (LLC's Choices page before 选项 was known) took a corner tap
    every look for good, and on the PC client each synthetic touch hid the mouse pointer."""
    skipper, text = Skipper(read), screen("LuxEventText.png")
    looks = [skipper.step(text, t) for t in range(5)]
    assert [point for _, point in looks] == [EVENT_NEUTRAL] * 3 + [None] * 2
    assert looks[-1][0] == event_skip.WAITING
    assert skipper.step(lines_shown(text), 5) == ("text", EVENT_NEUTRAL), "the screen changed: tap again"


def test_a_screen_that_answers_each_tap_keeps_getting_taps(screen):
    skipper, image = Skipper(read), screen("LuxEventText.png")
    for t in range(5):
        image = image.copy()
        image[350 + 22 * t:368 + 22 * t, 77:560] = 200 - 20 * t
        assert skipper.step(image, t) == ("text", EVENT_NEUTRAL), t


def test_the_worker_stops_tapping_a_screen_that_never_changes_and_says_so(screen):
    stuck = Recorder(screen("LuxEventText.png"))
    said = []
    w = Worker(Callbacks(skip=said.append), connect=lambda address, **_: (stuck, Target("fake", "x")), find=lambda: [])
    w.start()
    w.send("set_skip", True)
    time.sleep(2.5)
    assert stuck.taps == [EVENT_NEUTRAL] * 3 and said[-1] == event_skip.WAITING
    stuck.image = lines_shown(stuck.image)
    time.sleep(1.0)
    w.shutdown()
    assert stuck.taps[3:4] == [EVENT_NEUTRAL], "taps go on once the screen changes"
