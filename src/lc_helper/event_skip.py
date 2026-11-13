"""Skip an event's story up to the page where the player decides: what to tap on one look at the screen.

A trim of maalc's Event action (agent/actions.py Event.run and Event.advance, spec 03 section 10). It acts only on an
event page, told by the label of its bottom-right button (SKIP, Proceed, Continue, Commence), and never decides for
the player: it stops on the Choices page, on a check's "Choose a character" prompt, and on a lit Commence (the check
starts with the sinner the player picked). LLC's Chinese labels count the same (labels.WORDS): 继续 is pressed,
进行判定 never.

A corner tap that the screen does not answer is on a page the skipper misreads (LLC's Choices page before 选项 was
known was one): after a few, it waits for the screen to change instead. On the PC client each synthetic touch hides
the mouse pointer, so taps that do nothing are not harmless.
"""

from dataclasses import dataclass

from . import labels, vision

EVENT_BUTTON = (1130, 645)  # SKIP / Proceed / Continue / Commence share it; grey while it does nothing
EVENT_BUTTON_LABEL = (1040, 612, 190, 66)  # on most maps the bottom bar's lever reads there (maalc #511)
EVENT_NEUTRAL = (5, 5)  # top-left corner: nothing there on any event page; a tap shows the next line of text
EVENT_CARD = (940, 195)  # a Luxcavation check's card, alone at the right, waits for a tap (maalc card_alone)
CHOICES_HEADER = (690, 105, 170, 45)
CHECK_PROMPT = (850, 295, 300, 50)
PRESS_TAKES = 1.5  # s a press may take to show (maalc EVENT_TAKE): the same lit label is not pressed again before
UNANSWERED_TAPS = 3  # corner taps in a row that left the screen as it was, before the skipper waits for a change
WAITING = "點了沒反應，等畫面變化"
FULL_SCREEN = (0, 0, 1280, 720)


def red_button(image):
    """Whether the event button is lit (maalc red_button)."""
    b, g, r = image[640:650, 1080:1180].reshape(-1, 3).mean(0)
    return r > 150 and r - b > 70


def card_alone(image):
    """A check's card alone at the right, waiting for a tap (maalc card_alone, LuxEventCard.png)."""
    b, g, r = image[230:240, 760:1120].reshape(-1, 3).mean(0)
    return r > 90 and g > 75 and image[290:300, 700:1180].mean() < 10


def compact(text):
    return "".join(c for c in text.lower() if c.isalpha())


LABELS = {compact(w) for name in ("skip", "proceed", "continue", "commence") for w in labels.WORDS[name].values()}
PRESSABLE = LABELS - {compact(w) for w in labels.WORDS["commence"].values()}


@dataclass
class Skipper:
    """One look, one decision. read(image, roi, only_rec) gives the text lines at roi (OCR)."""

    read: callable
    pressed: str | None = None  # the label pressed last, and when
    pressed_at: float = -PRESS_TAKES
    tapped: list | None = None  # thumbnails (story box, whole screen) of the screen the corner taps are made on
    unanswered: int = 0  # corner taps in a row since that screen last changed

    def step(self, image, now):
        """(what, point) to tap on this screen, or (why not, None). what: "press", "card" or "text"."""
        what, point = self.decide(image, now)
        if what != "text":
            self.tapped, self.unanswered = None, 0
            return what, point
        # A new line of story text changes a few blocks of the story box, too few of the whole screen to count.
        screen = [vision.thumb(vision.crop(image, roi)) for roi in (vision.EVENT_STORY, FULL_SCREEN)]
        if self.tapped is not None and all(vision.same_screen(a, b) for a, b in zip(self.tapped, screen)):
            self.unanswered += 1
        else:
            self.tapped, self.unanswered = screen, 0
        return (WAITING, None) if self.unanswered >= UNANSWERED_TAPS else (what, point)

    def decide(self, image, now):
        label = compact(" ".join(self.read(image, EVENT_BUTTON_LABEL, True)))
        if label not in LABELS:
            self.pressed = None
            return "不是事件頁", None
        if labels.shows(self.read(image, CHOICES_HEADER, True), "choices"):
            return "到選項頁了，請你選", None
        if labels.shows(self.read(image, CHECK_PROMPT, False), "check"):
            return "判定要選罪人，請你選", None
        if red_button(image):
            if label not in PRESSABLE:
                return "按 Commence 開始判定（請你按）", None
            if label == self.pressed and now - self.pressed_at < PRESS_TAKES:
                return "上一下還在生效", None  # a press fading out still shows the lit button (maalc #273)
            self.pressed, self.pressed_at = label, now
            return "press", EVENT_BUTTON
        if card_alone(image):
            return "card", EVENT_CARD
        return "text", EVENT_NEUTRAL
