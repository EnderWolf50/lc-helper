import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QRegion, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from lc_helper import events, overlay  # noqa: E402
from lc_helper.overlay import Win  # noqa: E402

# The first line of each option visible on maalc's Choices captures (y of its OCR box); scrolled-out options have none.
VISIBLE = {
    "EventChoices.png": {"Shake hands.": 217, "Push the hand away.": 327},
    "EventChoicesLitBottom.png": {"West, to where the broken hand points.": 300, "Turn back.": 431},
    "EventChoicesLitTop.png": {"North, to where the burst-open arm points.": 206,
                               "East, to where the warning hand points.": 329,
                               "West, to where the broken hand points.": 477},
    "EventChoicesScrolledBack.png": {"North, to where the burst-open arm points.": 178,
                                     "East, to where the warning hand points.": 299,
                                     "West, to where the broken hand points.": 449},
    "EventChoicesUsed.png": {"What if you do feel like what you did was wrong?": 197,
                             "You're running away from something.": 354},
}


@pytest.mark.parametrize("name", VISIBLE)
def test_each_visible_option_is_found_at_its_first_line(screen, name):
    reading = events.read_screen(screen(name))
    rows = events.option_rows(reading.event, reading.lines)
    assert {option["text"]: box[1] for option, box in rows} == VISIBLE[name]


def test_a_label_is_centred_on_its_options_text_and_says_what_it_does(screen):
    reading = events.read_screen(screen("EventChoices.png"))
    found = {label.box[1]: label for label in overlay.labels(reading)}
    assert "護腕" in found[327].text and "判定" in found[327].text and found[217].text
    assert 340 < found[327].want < 370, "between the option's first line (327) and its hint's last"
    assert abs(found[217].want - (217 + found[217].box[3] / 2)) < 2, "a one-line option: that line's middle"


def test_an_answered_option_is_a_closed_label(screen):
    reading = events.read_screen(screen("EventChoicesUsed.png"))
    assert [label.closed for label in overlay.labels(reading)] == [True, False]


def test_a_card_says_the_checks_sins_the_gift_and_what_failing_costs(qt):
    push = events.by_id()[901069]["options"][1]
    font, small = overlay.Overlay().fonts()
    card = overlay.card_html(overlay.Label((730, 327, 191, 22), push), font, small, 600, 1)
    document = QTextDocument()
    document.setHtml(card)
    text = document.toPlainText()
    for said in ("傲慢", "嫉妒", "優勢判定", "成功", "護腕", "充能 I", "失敗", "HP", "−11", "SP", "判定的罪人"):
        assert said in text, said
    assert "回合開始時" in text, "the start of the gift's effect"
    bare = QTextDocument()
    bare.setHtml(overlay.card_html(overlay.Label((730, 327, 191, 22), push), font, small, 600, 0))
    assert "回合開始時" not in bare.toPlainText(), "no effect line when there is no room"


def test_a_card_with_nothing_recorded_is_one_line(qt):
    font, small = overlay.Overlay().fonts()
    turn_back = events.by_id()[901095]["options"][3]
    document = QTextDocument()
    document.setHtml(overlay.card_html(overlay.Label((730, 400, 100, 22), turn_back), font, small, 600, 2))
    assert document.toPlainText() == "沒有記錄效果"


def test_cards_are_centred_on_their_options_when_there_is_room_and_never_overlap():
    assert overlay.stack([230, 356], [60, 80]) == [200, 316]
    tops = overlay.stack([230, 260, 600], [100, 100, 100])
    assert tops[1] >= tops[0] + 100 + overlay.CARD_GAP, "pushed down past the one above"
    assert tops[2] + 100 <= overlay.CARD_BOTTOM, "pushed up off the party's portraits"
    assert overlay.stack([120], [100]) == [overlay.CARD_TOP], "kept under the story panel's top"


def test_the_busiest_options_fit_three_to_a_page_inside_the_game(qt):
    """The options with the most to say, on EventChoicesLitTop.png's three rows: cards inside the game's picture,
    none over another, each card's pointer reaching its option."""
    def weight(o):
        found = events.outcomes(o)
        return len(found) + sum(len(f.gifts) + len(f.gets) for f in found)
    busiest = sorted((o for e in events.book()["events"] for o in e["options"] if o["text"]), key=weight)[-3:]
    rows = [(733, 217, 300, 22), (733, 343, 300, 22), (733, 470, 300, 22)]
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    o.items = [overlay.Label(box, option) for box, option in zip(rows, busiest)]
    rects = [rect for _, _, rect in o.cards()]
    assert all(0 <= r.top() and r.bottom() <= 720 and r.right() < overlay.OPTION_FRAME for r in rects)
    assert all(a.bottom() < b.top() for a, b in zip(rects, rects[1:]))
    o.close()


def test_the_picture_is_the_16_by_9_middle_of_the_render_area():
    assert overlay.fit_16_9((0, 0, 2000, 1000)) == (111, 0, 1778, 1000)
    assert overlay.fit_16_9((10, 20, 1600, 1000)) == (10, 70, 1600, 900)
    assert overlay.fit_16_9((732, 381, 2490, 1401)) == (732, 381, 2490, 1401)  # MuMu on this machine, 2026-11-13


def test_mumu_instances_follow_their_adb_port():
    assert overlay.mumu_index("127.0.0.1:16384") == 0
    assert overlay.mumu_index("127.0.0.1:16416") == 1
    for other in ("127.0.0.1:5555", "127.0.0.1:16400", "emulator-5554", "pc", None):
        assert overlay.mumu_index(other) is None


def device_window(pid, index, display):
    top = Win(pid * 10, pid, "Qt5156QWindowIcon", "Android Device", True)
    shell = Win(pid * 10 + 1, pid, "Static", f"ShellWindowReveiceMessageWndMuMuPlayerGlobal-12.0-{index}", False)
    return [top, shell], {top.hwnd: [Win(display, pid, "nemuwin", "nemudisplay", True)]}


def test_the_display_of_the_instance_read_from_is_picked():
    tops0, kids0 = device_window(1, 0, display=100)
    tops1, kids1 = device_window(2, 1, display=200)
    tops, kids = tops0 + tops1, kids0 | kids1
    children = lambda hwnd: kids.get(hwnd, [])  # noqa: E731
    assert overlay.pick_mumu_display(tops, children, 1) == 200
    assert overlay.pick_mumu_display(tops, children, 0) == 100
    assert overlay.pick_mumu_display(tops, children, None) is None  # two displays and no way to tell
    assert overlay.pick_mumu_display(tops0, children, None) == 100  # the only one


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def test_a_drawn_gold_star_marks_the_recommended_label_and_no_other(qt):
    o = overlay.Overlay(locate=lambda source: (0, 0, 1280, 720))
    o.resize(1280, 720)
    push = events.by_id()[901069]["options"][1]
    o.items = [overlay.Label((730, 200, 191, 22), push, recommended=True), overlay.Label((730, 400, 191, 22), push)]
    rects = [rect for _, _, rect in o.cards()]
    canvas = QImage(1280, 720, QImage.Format_ARGB32)
    canvas.fill(QColor("#000000"))
    o.render(canvas, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    gold = QColor("#f0c674")

    def star_pixels(rect):
        return sum(canvas.pixelColor(x, y) == gold for x in range(int(rect.left()), int(rect.right()))
                   for y in range(int(rect.top()), int(rect.bottom())))

    assert star_pixels(rects[0]) > 20 and star_pixels(rects[1]) == 0
    o.close()


def test_the_overlay_shows_only_while_the_game_is_on_screen(qt):
    where = {"rect": (0, 0, 1280, 720)}
    o = overlay.Overlay(locate=lambda source: where["rect"])
    push = events.by_id()[901069]["options"][1]
    o.show_labels([overlay.Label((730, 327, 191, 22), push)], "127.0.0.1:16384")
    assert o.isVisible()
    where["rect"] = None  # minimised, or closed
    o.place()
    assert not o.isVisible()
    o.show_labels([overlay.Label((730, 327, 191, 22), push)], "127.0.0.1:16384")
    assert not o.isVisible()
    where["rect"] = (0, 0, 1280, 720)
    o.show_labels([], "127.0.0.1:16384")  # a page with no option found
    assert not o.isVisible()
    o.close()


def test_the_overlay_is_kept_just_above_the_game_and_never_always_on_top(qt, monkeypatch):
    """Over the game while it is in front, under any window in front of it (follow.place_above)."""
    placed = []
    monkeypatch.setattr(overlay, "lifts", lambda: True)
    monkeypatch.setattr(overlay.follow, "place_above", lambda hwnd, game: placed.append((hwnd, game)))
    o = overlay.Overlay(locate=lambda source: (0, 0, 1280, 720), window_of={"127.0.0.1:16384": 42}.get)
    assert not o.windowFlags() & Qt.WindowStaysOnTopHint
    o.show_labels([overlay.Label((730, 327, 191, 22), events.by_id()[901069]["options"][1])], "127.0.0.1:16384")
    assert placed == [(int(o.winId()), 42)]
    o.place()  # the follow timer's look
    assert len(placed) == 2
    o.close()


def test_each_post_boss_cards_worth_sits_over_its_trial_and_fits(qt):
    from lc_helper import gifts, trials

    def card(x, gift_id, trial, level):
        return trials.Card(x, gifts.book()[gift_id], False, trial, level)
    page = trials.TrialPage((card(242, 9054, "Defense Level Up", 1), card(506, 9013, "Defense Skill Up", 1),
                             card(771, 9089, "Take Less Damage", 2), card(1035, 9001, "Growth I", 2)), 2)
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    o.trials = trials.worth(page, ["Charge"])
    laid = o.trial_cards()
    assert all(abs(rect.center().x() - w.card.x) < 2 and rect.top() >= 470 and rect.bottom() <= 548
               for w, _, rect in laid), "over the trial's effect box, clear of Refuse Gift and Select (y 548)"
    assert all(a.right() < b.left() for (_, _, a), (_, _, b) in zip(laid, laid[1:]))
    assert all(doc.size().height() <= rect.height() for _, doc, rect in laid)
    o.close()
