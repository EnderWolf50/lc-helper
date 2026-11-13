import time

import pytest

from lc_helper import ocr
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
