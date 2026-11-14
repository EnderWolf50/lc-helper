import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontInfo, QImage, QPainter, QRegion,  # noqa: E402
                           QTextDocument)
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from lc_helper import events, gifts, icons, overlay, palette  # noqa: E402
from lc_helper.overlay import Win  # noqa: E402
from lc_helper.palette import INK  # noqa: E402

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


def test_a_card_says_the_checks_sins_and_each_outcome_at_a_glance_and_the_gift_in_full_when_opened(qt):
    push = overlay.Label((730, 327, 191, 22), events.by_id()[901069]["options"][1])
    font, small = overlay.Overlay().fonts()
    brief, full = QTextDocument(), QTextDocument()
    brief.setHtml(overlay.brief_html(push, small))
    full.setHtml(overlay.full_html(push, font, small, 30))
    for said in ("傲慢", "嫉妒", "優勢判定", "成功", "失敗", "HP", "−11", "SP", "判定的罪人"):
        assert said in brief.toPlainText() and said in full.toPlainText(), said
    assert "gift:9069" in brief.toHtml() and "護腕" not in brief.toPlainText(), "the gift's picture, not its name"
    assert "護腕" in full.toPlainText() and "充能 I" in full.toPlainText()
    assert "若該友方單位擁有傲慢攻擊技能" in full.toPlainText(), "the gift's whole effect, to its last sentence"


def test_a_card_with_nothing_recorded_is_one_line(qt):
    font, small = overlay.Overlay().fonts()
    turn_back = overlay.Label((730, 400, 100, 22), events.by_id()[901095]["options"][3])
    for card in (overlay.brief_html(turn_back, small), overlay.full_html(turn_back, font, small, 30)):
        document = QTextDocument()
        document.setHtml(card)
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
    laid = o.cards()
    rects = [rect for _, _, rect in laid]
    assert all(0 <= r.top() and r.bottom() <= 720 and r.right() < overlay.OPTION_FRAME for r in rects)
    assert all(a.bottom() < b.top() for a, b in zip(rects, rects[1:]))
    assert all(r.top() + overlay.POINTER_END <= label.want <= r.bottom() - overlay.POINTER_END
               for label, _, r in laid), "each card's pointer meets its option's middle"
    font, small = o.fonts()
    sides = gift_sides(laid)
    assert len(sides) == 1, "one size of gift picture on the page"
    assert sides.pop() >= overlay.picture_side(font, small, 1) - 1, "never as small as one line"
    o.close()


def gift_sides(laid):
    """The sides of the gift pictures on laid-out cards, in overlay px."""
    sides = set()
    for _, doc, _ in laid:
        for gid in set(re.findall(r"gift:(\d+)", doc.toHtml())):
            picture = doc.resource(QTextDocument.ImageResource, QUrl(f"gift:{gid}"))
            sides.add(round(picture.width() / picture.devicePixelRatio()))
    return sides


def test_a_page_with_room_shows_its_gifts_pictures_three_lines_tall(screen, qt):
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1920, 1080)
    o.items = overlay.labels(events.read_screen(screen("EventChoices.png")))
    font, small = o.fonts()
    laid = o.cards()
    sides = gift_sides(laid)
    assert len(sides) == 1 and abs(sides.pop() - overlay.picture_side(font, small, 2)) <= 1, "a line and two small"
    assert all(rect.right() == overlay.CARD_RIGHT * 1.5 and rect.width() < 0.8 * (overlay.CARD_RIGHT - overlay.CARD_LEFT)
               * 1.5 for _, _, rect in laid), "as wide as they need, against the options"
    o.close()


def test_a_brief_card_has_a_block_per_outcome_with_its_gifts_pictures_marked_with_their_tier(qt):
    two = next(o for e in events.book()["events"] for o in e["options"]
               if any(len(f.gifts) == 2 for f in events.outcomes(o)))
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    label = overlay.Label((730, 327, 191, 22), two)
    doc = o.document(label, 600, 2)
    found = events.outcomes(two)
    font, small = o.fonts()
    assert overlay.brief_html(label, small).count(f"bgcolor='{overlay.BLOCK_FILL}'") == len(found)
    ids = [gid for f in found for gid, _ in f.gifts]
    assert all(gifts.book()[gid]["zh"] not in doc.toPlainText() for gid in ids)
    side, ratio = overlay.picture_side(font, small, 2), o.devicePixelRatioF()
    for gid in ids:
        g = gifts.book()[gid]
        marked = doc.resource(QTextDocument.ImageResource, QUrl(f"gift:{gid}")).toImage()
        plain = icons.game_gift(gid, g["keyword"], side, ratio).toImage()
        tier_ink = QColor(icons.TIER_FILL).rgb()
        assert marked != plain and any(marked.pixel(x, y) == tier_ink for x in range(marked.width() // 2)
                                       for y in range(marked.height() // 2)), "the tier in the top-left corner"
    o.close()


def test_a_check_cards_head_shows_the_games_sin_icons_not_coloured_chips(qt):
    push = overlay.Label((730, 327, 191, 22), events.by_id()[901069]["options"][1])  # a 傲慢 and 嫉妒 check
    head = overlay.head_html(push)
    assert re.findall(r"<img src='sin:(\w+)'", head) == ["Pride", "Envy"]
    assert "background-color" not in head
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    doc = o.document(push, 600, 2)
    for name in ("Pride", "Envy"):
        assert not doc.resource(QTextDocument.ImageResource, QUrl(f"sin:{name}")).isNull(), name
    o.close()


def test_every_sin_has_the_games_icon(qt):
    assert set(icons.SIN_ICONS) == set(events.SINS)
    for sin in events.SINS:
        image = icons.sin(sin, 24, 1).toImage()
        coloured = sum(image.pixelColor(x, y).alpha() > 200 and image.pixelColor(x, y).hsvSaturation() > 120
                       for x in range(image.width()) for y in range(image.height()))
        assert not image.isNull() and coloured > 50, sin


def ink_box(image, inked):
    """The box (left, top, right, bottom) of image's pixels for which inked(x, y) holds; None when there are none."""
    hits = [(x, y) for y in range(image.height()) for x in range(image.width()) if inked(x, y)]
    if not hits:
        return None
    return min(x for x, _ in hits), min(y for _, y in hits), max(x for x, _ in hits), max(y for _, y in hits)


def test_a_gifts_slot_has_its_tier_and_keyword_where_the_games_has_them(qt):
    """Wound Clerid (9005, Bleed, II) as the game's Gift GET page draws it, 144 px: its II's yellow from x 352 to
    368, y 234 to 271 on the slot at 338, 225 (maalc tests/screens/GiftGet.png); its keyword's icon a 100 box 5 in from
    the slot's bottom-right corner, of the slot's 350 (EgoGiftIconPrefab, tools/gift_slot.py)."""
    slot = icons.game_gift(9005, "Bleed", 144, 1, "II").toImage()
    yellow = ink_box(slot, lambda x, y: (c := slot.pixelColor(x, y)).red() > 215 and 150 < c.green() < 215
                     and c.blue() < 70)
    assert all(abs(a - b) <= 1.5 for a, b in zip(yellow, (352 - 338, 234 - 225, 368 - 338, 271 - 225))), yellow
    keywordless = icons.game_gift(9005, "Keywordless", 144, 1, "II").toImage()
    badge = ink_box(slot, lambda x, y: slot.pixel(x, y) != keywordless.pixel(x, y))
    unit = 144 / icons.SLOT["slot"]
    corner = 144 - icons.SLOT["keyword_in"] * unit
    assert badge and badge[0] >= corner - icons.SLOT["keyword"] * unit - 1 and badge[1] >= corner - icons.SLOT[
        "keyword"] * unit - 1 and badge[2] <= corner and badge[3] <= corner, badge


def test_a_tiles_keyword_badge_reaches_its_corner_on_a_scaled_screen(qt):
    """At two device pixels to a logical one, the badge is drawn in device pixels, not shrunk to half."""
    gid = next(gid for gid, g in gifts.book().items() if not icons.gift_picture(gid).isNull()
               and g.get("keyword") == "Bleed")
    marked, plain = (icons.gift(gid, "Bleed", 40, 2, badge=b).toImage() for b in (True, False))
    badge = ink_box(marked, lambda x, y: marked.pixel(x, y) != plain.pixel(x, y))
    tall = badge[3] - badge[1] + 1  # Bleed's icon is taller than wide: it fills the badge's height
    assert badge[3] >= marked.height() - 3 and tall >= (icons.BADGE - 0.05) * marked.height(), badge


@pytest.mark.parametrize("height", [720, 1440])
def test_a_heads_sin_icon_is_centred_on_its_text(qt, height):
    """The icon's drawing and the CJK text beside it share a middle (the user, 2026-11-15: the icons sat low)."""
    push = overlay.Label((730, 327, 191, 22), events.by_id()[901069]["options"][1])  # a 傲慢 and 嫉妒 check
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(height * 16 // 9, height)
    font, _ = o.fonts()
    doc = o.document(push, 900, 2)
    doc.setHtml(overlay.head_html(push))
    overlay.on_baseline(doc)
    image = QImage(round(doc.idealWidth()) + 2, round(doc.size().height()) + 2, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    doc.drawContents(painter)
    painter.end()

    def middle(x0, x1):
        rows = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() > 128 for x in range(x0, x1))]
        return (rows[0] + rows[-1]) / 2

    icon = round(font.pixelSize() * overlay.SIN_SIDE)
    assert abs(middle(0, icon) - middle(icon + 2, icon + 2 + 2 * font.pixelSize())) <= 1.5
    o.close()


def test_effects_have_a_dot_between_them_and_their_sinners_before_each_run_of_them(qt):
    gets = [("hp", 30, "ChosenPersonality"), ("sp", 30, "ChosenPersonality"), ("hp", 12, "NotAffectedAlly"),
            ("sp", 12, "NotAffectedAlly"), ("battle",)]
    doc = QTextDocument()
    doc.setHtml(overlay.gets_html(gets, 13))
    words = " ".join(doc.toPlainText().replace("\xa0", " ").split())
    assert words == "判定的罪人 HP +30 · SP +30 · 其餘罪人 HP +12 · SP +12 · 開始戰鬥"


def test_the_numerals_are_in_maalcs_barlow_condensed(qt):
    assert palette.display_family() == "Barlow Condensed"
    for weight in palette.DISPLAY:
        family = palette.display_family(weight)
        assert QFontInfo(QFont(family)).family() == family, "loaded, not a stand-in"


def test_a_click_opens_a_card_in_full_over_the_others_and_another_click_closes_it(qt):
    o = overlay.Overlay(locate=lambda source: (0, 0, 1280, 720), window_of=lambda source: None)
    assert not o.windowFlags() & Qt.WindowTransparentForInput, "its cards take clicks"
    assert o.windowFlags() & Qt.WindowDoesNotAcceptFocus, "WS_EX_NOACTIVATE: a click leaves the game in front"
    o.resize(1280, 720)
    shake, push = events.by_id()[901069]["options"]
    items = [overlay.Label((730, 217, 191, 22), shake), overlay.Label((730, 327, 191, 22), push)]
    o.show_labels(items, "127.0.0.1:16384")
    rect = next(r for label, _, r in o.cards() if label.option is push)
    mask = o.mask()
    assert mask.contains(rect.center().toPoint()), "a card takes clicks"
    for elsewhere in (QPoint(100, 300), QPoint(300, 680), QPoint(1000, 400)):  # the story, the party, the options
        assert not mask.contains(elsewhere), elsewhere
    QTest.mouseClick(o, Qt.LeftButton, pos=rect.center().toPoint())
    assert o.opened == push["text"]
    label, doc, opened = o.opened_card(o.cards())
    assert label.option is push and "若該友方單位擁有傲慢攻擊技能" in doc.toPlainText()
    assert opened.width() > rect.width() and o.mask().contains(QPoint(100, round(opened.center().y())))
    o.show_labels(items, "127.0.0.1:16384")  # the page read again: still open
    assert o.opened == push["text"]
    QTest.mouseClick(o, Qt.LeftButton, pos=QPoint(100, round(opened.center().y())))
    assert o.opened is None and not o.mask().contains(QPoint(100, round(opened.center().y())))
    QTest.mouseClick(o, Qt.LeftButton, pos=rect.center().toPoint())
    o.show_labels(items[:1], "127.0.0.1:16384")  # a page without that option
    assert o.opened is None
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


@pytest.fixture(autouse=True)
def faces(qt):
    """The cards' faces registered before the test, as the app has them: the offscreen platform has no fonts of its
    own, so a card's text would measure in whichever face was registered last, maalc's numerals face once a card
    has drawn one (conftest.no_application_fonts)."""
    for name in ("msjh.ttc", "msjhbd.ttc"):  # Microsoft JhengHei UI, the text's face, and its bold
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    palette.display_family()


def drawn(width, height, items):
    """An overlay of width x height with items drawn on black: (the overlay, its cards, the picture)."""
    o = overlay.Overlay(locate=lambda source: (0, 0, width, height))
    o.resize(width, height)
    o.items = items
    canvas = QImage(width, height, QImage.Format_ARGB32)
    canvas.fill(QColor("#000000"))
    o.render(canvas, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return o, o.cards(), canvas


def test_a_drawn_amber_star_marks_the_recommended_label_and_no_other(qt):
    push = events.by_id()[901069]["options"][1]
    o, laid, canvas = drawn(1280, 720, [overlay.Label((730, 200, 191, 22), push, recommended=True),
                                        overlay.Label((730, 400, 191, 22), push)])
    amber = QColor(INK["accent"])

    def star_pixels(rect):
        inside = rect.adjusted(4, 4, -4, -4)  # within the recommended card's amber frame
        return sum(canvas.pixelColor(x, y) == amber for x in range(int(inside.left()), int(inside.right()))
                   for y in range(int(inside.top()), int(inside.bottom())))

    assert [label.recommended for label, _, _ in laid] == [True, False]
    assert star_pixels(laid[0][2]) > 20 and star_pixels(laid[1][2]) == 0
    o.close()


def test_a_cards_frame_is_maalcs_bronze_and_the_recommended_ones_amber(qt):
    """At 2560 wide every frame is 2 px or more, so a pixel across its top edge is wholly its colour."""
    push = events.by_id()[901069]["options"][1]
    o, laid, canvas = drawn(2560, 1440, [overlay.Label((730, 200, 191, 22), push, recommended=True),
                                         overlay.Label((730, 400, 191, 22), push)])
    for label, _, rect in laid:
        x = round(rect.center().x())
        edge = {canvas.pixelColor(x, y).name() for y in range(int(rect.top()) - 3, int(rect.top()) + 4)}
        frame, other = (INK["accent"], INK["line-2"]) if label.recommended else (INK["line-2"], INK["accent"])
        assert frame in edge and other not in edge, (label.recommended, edge)
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


def test_each_post_boss_cards_worth_sits_above_its_card_and_fits(qt):
    from lc_helper import gifts, trials

    def card(x, gift_id, trial, level):
        return trials.Card(x, gifts.book()[gift_id], False, trial, level)
    page = trials.TrialPage((card(242, 9054, "Defense Level Up", 1), card(506, 9013, "Defense Skill Up", 1),
                             card(771, 9089, "Take Less Damage", 2), card(1035, 9001, "Growth I", 2)), 2)
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    o.trials = trials.worth(page, ["Charge"])
    laid = o.trial_cards()
    assert all(abs(rect.center().x() - w.card.x) < 2 and rect.top() >= 80 and rect.bottom() <= 150
               for w, _, rect in laid), "above the card (its tags from y 152), under the top bar's buttons"
    assert all(a.right() < b.left() for (_, _, a), (_, _, b) in zip(laid, laid[1:]))
    assert all(doc.size().height() <= rect.height() for _, doc, rect in laid)
    o.close()


def test_a_gift_on_an_opened_card_leads_with_its_picture(qt):
    push = events.by_id()[901069]["options"][1]
    o = overlay.Overlay(locate=lambda source: None, window_of=lambda source: None)
    o.resize(1280, 720)
    doc = o.document(overlay.Label((730, 327, 191, 22), push), 600, 2, full=True)
    assert doc.toHtml().index("gift:9069") < doc.toHtml().index("護腕")
    picture = doc.resource(QTextDocument.ImageResource, QUrl("gift:9069"))
    font, small = o.fonts()
    side = picture.width() / picture.devicePixelRatio()
    assert not picture.isNull() and abs(side - overlay.picture_side(font, small, 2)) <= 1, "a line and two small"
    o.close()
