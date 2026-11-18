import os
import re
import time
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QIcon, QTextDocument  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QToolButton  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events, gifts, trials  # noqa: E402
from lc_helper.device import Target  # noqa: E402
from lc_helper.worker import Worker  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)


def window(tmp_path, monkeypatch, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    w = ui.Window(StandIn)
    w.settings.update(settings)
    w.overlay.locate = lambda source: (0, 0, 1280, 720)  # never the real game window
    return w


GLYPHS = set("★∞•")  # text characters that once stood in for drawn icons


def test_the_recommended_option_is_starred_in_the_pane_and_on_the_game(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keywords=["Charge"], overlay=True)
    w.on_event(events.read_screen(screen("EventChoices.png")))
    assert "推薦：判定通過獲得飾品，有充能飾品" in w.detail.toPlainText()
    assert w.detail.toHtml().count("icon:star") == 1, "the drawn star, once"
    assert not GLYPHS & set(w.detail.toPlainText())
    starred = {item.box[1]: item.recommended for item in w.overlay.items}
    assert starred == {217: False, 327: True}  # Push the hand away: a Charge gift on a pass
    assert not GLYPHS & set("".join(item.text for item in w.overlay.items))
    w.overlay.hide_labels()


def test_no_keyword_no_star_and_a_new_keyword_ranks_again(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keywords=[], overlay=True)
    w.on_event(events.read_screen(screen("EventChoices.png")))
    assert "icon:star" not in w.detail.toHtml() and not any(item.recommended for item in w.overlay.items)
    choose(button(w, "＋ 體系"), "充能")
    assert "推薦" in w.detail.toPlainText() and "icon:star" in w.detail.toHtml()
    assert any(item.recommended for item in w.overlay.items)
    w.overlay.hide_labels()


def test_a_grey_option_is_never_starred(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keywords=["Poise"], overlay=True)
    reading = events.read_screen(screen("EventChoicesUsed.png"))
    w.on_event(reading)
    starred = [item for item in w.overlay.items if item.recommended]
    assert starred and all(item.box[1] != 197 for item in starred)  # the grey first option
    w.overlay.hide_labels()


def shown(tmp_path, monkeypatch, **settings):
    """A window shown, built on settings."""
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    ui.save_settings(ui.DEFAULTS | settings)
    w = window(tmp_path, monkeypatch)
    w.show()
    QApplication.processEvents()
    return w


def rows(box):
    """The rows the search box's drop-down list shows, while it shows."""
    view = box.list.popup()
    return [view.model().index(i, 0).data() for i in range(view.model().rowCount())] if view.isVisible() else []


def search_icon(box):
    """The search icon inside box's field: a click on it searches."""
    return next(b for b in box.field.findChildren(QToolButton) if b.defaultAction() is box.go)


def clear_button(box):
    """The clear button inside box's field."""
    return next(b for b in box.field.findChildren(QToolButton) if b.defaultAction() is not box.go)


def click_row(box, row):
    view = box.list.popup()
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(view.model().index(row, 0)).center())
    QApplication.processEvents()


def test_the_event_search_drops_down_events_only_and_closes_once_one_is_picked(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch)
    placeholder = w.detail.toPlainText()
    box = w.event_search
    QTest.keyClicks(box.field, "gift")
    QTest.qWait(400)  # the search runs once the typing pauses
    hits = events.search("gift", limit=8)
    assert rows(box) == [ui.result_text(e) for e in hits] and len(hits) > 1, "events, no gifts"
    assert w.detail.toPlainText() == placeholder, "nothing shows before a pick"
    click_row(box, 1)
    assert not box.list.popup().isVisible(), "picked: the list closes"
    assert w.detail.toPlainText().startswith(f"事件 {hits[1]['id']}")
    assert box.field.text() == "gift", "the words stay in the field"


def test_the_search_icon_and_enter_search_at_once_and_enter_on_the_list_picks_the_first_hit(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch)
    box = w.event_search
    first = events.search("hand", limit=8)[0]
    searches = []
    search = events.search
    monkeypatch.setattr(events, "search", lambda *a, **k: searches.append(a) or search(*a, **k))
    box.field.setText("hand")
    QTest.keyClick(box.field, Qt.Key_Return)
    assert rows(box)[0] == ui.result_text(first) and len(searches) == 1
    QTest.keyClick(box.list.popup(), Qt.Key_Return)
    # The list hands Return to the field before it picks: a search then would refill the list under the pick.
    assert len(searches) == 1, "Enter on the list picks, it does not search again"
    assert not box.list.popup().isVisible() and w.detail.toPlainText().startswith(f"事件 {first['id']}")
    assert not search_icon(box).icon().isNull() and search_icon(box).toolTip() == "查詢"
    search_icon(box).click()
    assert len(searches) == 2 and rows(box)[0] == ui.result_text(first), "the icon searches"


class Slides:
    """A game that shows each screen in turn, one per screenshot, then stays on the last; taps do nothing."""

    can_hold = True

    def __init__(self, images):
        self.images = list(images)

    def screenshot(self):
        return self.images.pop(0) if len(self.images) > 1 else self.images[0]

    def __getattr__(self, name):
        return lambda *a: None


def wait_until(predicate, timeout=20):
    """Let the window take the worker's news until predicate holds."""
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "timed out"
        QTest.qWait(50)


def test_an_event_read_by_hand_leaves_the_pane_and_the_game_once_its_page_goes(tmp_path, monkeypatch, screen):
    """自動 off: F9 reads the Choices page, and the window lets the event go once the game shows the map."""
    game = Slides([screen("EventChoices.png"), screen("EventChoices.png"), screen("MirrorMap.png")])
    worker = lambda callbacks: Worker(callbacks, connect=lambda address, **_: (game, Target("fake", "127.0.0.1:1")),  # noqa: E731
                                      find=lambda: [])
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    ui.save_settings(ui.DEFAULTS | {"watch": False, "overlay": True})
    w = ui.Window(worker)
    w.overlay.locate = lambda source: (0, 0, 1280, 720)  # never the real game window
    w.show()
    placeholder = w.detail.toPlainText()
    w.worker.start()
    try:
        w.read_button.click()
        wait_until(lambda: w.detail.toPlainText().startswith("事件 901069"))
        wait_until(lambda: w.detail.toPlainText() == placeholder)
        assert not w.overlay.isVisible() and not w.overlay.items, "the hints on the game go too"
    finally:
        w.worker.shutdown()
        w.worker.join(3)
        w.overlay.hide_labels()


def test_the_hints_of_a_watched_page_stay_until_it_goes_and_others_go_after_a_minute(tmp_path, monkeypatch, screen):
    """自動 off: F9 on a Choices page is watched, so its hints wait for page_left; a read nothing watches has no
    page_left to wait for."""
    w = window(tmp_path, monkeypatch, keywords=["Charge"], overlay=True, watch=False)
    reading = events.read_screen(screen("EventChoices.png"))
    w.on_event(replace(reading, watched=True))
    assert w.overlay.items and not w.overlay.expire.isActive()
    w.on_event(reading)
    assert w.overlay.items and w.overlay.expire.isActive() and w.overlay.expire.interval() == 60_000
    w.overlay.hide_labels()


def test_an_event_looked_up_stays_when_the_page_read_goes(tmp_path, monkeypatch, screen):
    w = shown(tmp_path, monkeypatch)
    w.on_event(events.read_screen(screen("EventChoices.png")))
    box = w.event_search
    box.field.setText("hand")
    search_icon(box).click()
    click_row(box, 0)
    looked_up = w.detail.toPlainText()
    w.bridge.page_left.emit()
    assert w.detail.toPlainText() == looked_up and not w.overlay.isVisible()


def test_clearing_the_event_search_empties_the_pane(tmp_path, monkeypatch, screen):
    w = shown(tmp_path, monkeypatch)
    placeholder = w.detail.toPlainText()
    box = w.event_search
    box.field.setText("hand")
    search_icon(box).click()
    click_row(box, 0)
    assert w.detail.toPlainText() != placeholder
    clear_button(box).click()
    assert box.field.text() == "" and w.detail.toPlainText() == placeholder, "the clear button"
    w.on_event(events.read_screen(screen("EventChoices.png")))
    w.overlay.hide_labels()
    box.field.setText("x")
    box.field.clear()
    assert w.detail.toPlainText() == placeholder, "emptied by hand"


def test_a_search_with_no_hit_says_so_in_the_list_and_leaves_the_pane_alone(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch)
    w.show_event(events.by_id()[901069])
    before = w.detail.toPlainText()
    box = w.event_search
    box.field.setText("qqzzxxjj")
    search_icon(box).click()
    assert rows(box) == ["找不到符合的事件"]
    click_row(box, 0)
    assert w.detail.toPlainText() == before


def test_the_gift_search_finds_gifts_by_chinese_or_english_name_and_shows_one_in_the_gift_pane(tmp_path, monkeypatch):
    from lc_helper import gifts

    w = shown(tmp_path, monkeypatch, open_sections=["event", "gift"])
    w.show_event(events.by_id()[901069])
    event_text = w.detail.toPlainText()
    box = w.gift_search
    for query in ("地獄蝶", "hellterfly"):
        box.field.setText(query)
        QTest.keyClick(box.field, Qt.Key_Return)
        found = gifts.search(query, limit=8)
        assert rows(box)[0].startswith(gifts.label(found[0])), query
    search_icon(box).click()
    assert rows(box)[0].startswith(gifts.label(found[0])), "the gift field's icon searches too"
    click_row(box, 0)
    first_line = next(line for line in w.gift_detail.toPlainText().splitlines()
                      if line.strip("\ufffc "))  # the picture's cell has no words
    assert gifts.label(found[0]) in first_line and w.detail.toPlainText() == event_text
    w.sections["gift"].head.click()
    assert w.sections["gift"].summary.text() == f"最近：{found[0]['zh']}"


def inked_colours(image):
    """The distinct colours image paints."""
    return {image.pixelColor(x, y).rgb() for x in range(image.width()) for y in range(image.height())
            if image.pixelColor(x, y).alpha()}


def test_a_gift_shows_its_keywords_icon_beside_its_name_and_a_keywordless_one_a_quiet_mark(tmp_path, monkeypatch):
    from lc_helper import gifts

    w = shown(tmp_path, monkeypatch, open_sections=["event", "gift"])
    hellterfly, perversion = gifts.book()[9001], gifts.book()[9002]  # Burn, and no keyword
    w.show_gifts([hellterfly, perversion])
    page = w.gift_detail.toHtml()
    for gift, keyword in ((hellterfly, "Burn"), (perversion, "Keywordless")):
        assert page.index(f"keyword:{keyword}") < page.index(gift["zh"]), "the icon, then the name"
    doc = w.gift_detail.document()
    burn, none = (doc.resource(QTextDocument.ImageResource, QUrl(f"keyword:{k}")) for k in ("Burn", "Keywordless"))
    assert len(inked_colours(burn.toImage())) > 20, "the game's flame"
    assert 0 < len(inked_colours(none.toImage())) <= 20, "a drawn mark in one colour, its edge smoothed"
    side = burn.width() / burn.devicePixelRatio()
    w.set_text_size("large")
    grown = doc.resource(QTextDocument.ImageResource, QUrl("keyword:Burn"))
    assert grown.width() / grown.devicePixelRatio() > side, "it grows with the text"


def test_a_gift_search_row_carries_the_gifts_picture(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch, open_sections=["gift"])
    box = w.gift_search
    box.field.setText("burn")
    QTest.keyClick(box.field, Qt.Key_Return)
    model = box.list.popup().model()
    assert model.rowCount() > 1
    icons = [model.index(i, 0).data(Qt.DecorationRole) for i in range(model.rowCount())]
    assert all(not icon.isNull() for icon in icons)
    size = box.list.popup().iconSize()
    assert size.width() == ui.GIFT_ROW * ui.glyph_side(w.text_font()), "two lines of text tall"
    lit, plain = (icons[0].pixmap(size, mode).toImage() for mode in (QIcon.Selected, QIcon.Normal))
    assert lit == plain, "the lit row keeps the icon's colours"
    assert len(inked_colours(plain)) > 200, "the game's picture of the gift, not a keyword icon alone"


def test_a_gift_screen_read_shows_in_the_gift_pane_and_leaves_the_event_shown(tmp_path, monkeypatch, screen):
    from lc_helper import gifts, ocr

    w = shown(tmp_path, monkeypatch, open_sections=["event", "gift"])
    w.on_event(events.read_screen(screen("EventChoices.png")))
    w.overlay.hide_labels()
    event_text = w.detail.toPlainText()
    reading = gifts.read_gifts(screen("BossGiftTrials.png"), "choice", ocr.lines)
    w.on_gifts(reading)
    assert w.gift_detail.toPlainText().startswith("畫面上可以選的飾品")
    assert all(gifts.label(g) in w.gift_detail.toPlainText() for g, _ in reading.gifts)
    assert w.detail.toPlainText() == event_text


def button(w, text):
    return next(b for b in w.findChildren(QAbstractButton) if b.text() == text)


def choose(chip, text):
    """Pick text from the menu of a chip or of ＋ 體系, and let the window show the new chips."""
    next(a for a in chip.menu().actions() if a.text() == text).trigger()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)  # what the event loop does with the old chips
    QApplication.processEvents()


def row_parts(w):
    """The recommendation row as shown, left to right: its chips, the marks between them and ＋ 體系."""
    body = w.sections["event"].body
    parts = [b for b in body.findChildren(QAbstractButton) if b.objectName() in ("chip", "chipAdd")]
    parts += body.findChildren(QLabel, "then")
    return sorted((p for p in parts if p.isVisibleTo(body)), key=lambda p: p.mapTo(w, QPoint()).x())


def chips(w):
    """The recommendation row as shown: each keyword chip's text, then ＋ 體系 if it shows."""
    return [p.text() for p in row_parts(w) if isinstance(p, QAbstractButton)]


NOT_CHINESE = re.compile("[0-9A-Za-z０-９Ａ-Ｚａ-ｚ]")  # digits and Latin letters, half and full width


def starred(w):
    """The option the event pane stars."""
    return next(line for line in w.detail.toHtml().split("<p") if "icon:star" in line)


DRAW_SWORD = 971014  # a Bleed gift for 做出拔劍的姿勢, a Poise gift for 拔劍後垂在身側, both direct


def test_keywords_show_as_chips_in_their_order_and_the_order_decides_the_star(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch, keywords=["Bleed", "Poise"])
    w.show_event(events.by_id()[DRAW_SWORD])
    assert chips(w) == ["流血", "呼吸", "＋ 體系"]
    assert "做出拔劍的姿勢" in starred(w)
    choose(button(w, "呼吸"), "往前移")
    assert chips(w) == ["呼吸", "流血", "＋ 體系"] and w.settings["keywords"] == ["Poise", "Bleed"]
    assert "拔劍後垂在身側" in starred(w)
    choose(button(w, "呼吸"), "往後移")
    assert w.settings["keywords"] == ["Bleed", "Poise"] and "做出拔劍的姿勢" in starred(w)


def test_a_chip_can_be_removed_and_the_first_and_last_cannot_move_further(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch, keywords=["Bleed", "Poise", "Burn"])
    first, last = button(w, "流血"), button(w, "燒傷")
    enabled = lambda chip: {a.text(): a.isEnabled() for a in chip.menu().actions()}  # noqa: E731
    assert enabled(first) == {"往前移": False, "往後移": True, "移除": True}
    assert enabled(last) == {"往前移": True, "往後移": False, "移除": True}
    choose(button(w, "呼吸"), "移除")
    assert chips(w) == ["流血", "燒傷", "＋ 體系"] and w.settings["keywords"] == ["Bleed", "Burn"]


def test_add_offers_the_keywords_not_chosen_and_goes_away_at_four(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch, keywords=["Bleed"], open_sections=[])
    offered = button(w, "＋ 體系").menu().actions()
    assert [a.text() for a in offered] == [events.KEYWORDS[k] for k in ui.recommend.CHOICES if k != "Bleed"]
    assert all(not a.icon().isNull() for a in offered), "each with the game's icon"
    for text in ("燒傷", "震顫", "破裂"):
        choose(button(w, "＋ 體系"), text)
    assert chips(w) == ["流血", "燒傷", "震顫", "破裂"], "four at most: no ＋ 體系"
    assert w.sections["event"].summary.text() == "推薦 流血 › 燒傷 › 震顫 › 破裂"


def test_a_chip_is_the_keywords_icon_and_chinese_name_and_its_place_is_its_order(tmp_path, monkeypatch):
    """The player read 「1 呼吸」「2 燒傷」 as noise: the order shows by place, a mark between each chip and the next."""
    w = shown(tmp_path, monkeypatch, keywords=["Poise", "Burn", "Charge"])
    parts = row_parts(w)
    assert [p.objectName() for p in parts] == ["chip", "then", "chip", "then", "chip", "chipAdd"]
    for chip in parts[:5:2]:
        assert not chip.icon().isNull() and chip.iconSize().height() > 0, chip.text()
        assert not NOT_CHINESE.search(chip.text() + chip.toolTip()), chip.text()
    assert all(not mark.pixmap().isNull() and not mark.text() for mark in parts[1:5:2]), "a drawn mark, no glyph"
    menus = [a.text() for p in parts if isinstance(p, QAbstractButton) for a in p.menu().actions()]
    assert not NOT_CHINESE.search("".join(menus)), "the chips' menus and ＋ 體系's"


def test_no_keyword_says_what_adding_one_does(tmp_path, monkeypatch):
    w = shown(tmp_path, monkeypatch, keywords=[])
    assert chips(w) == ["＋ 體系"]
    row = w.sections["event"].body.findChildren(QLabel)
    assert any(label.text() == "加入後標出建議的選項" and label.isVisible() for label in row)


def post_boss_page():
    """BossGiftTrialsHard.png's cards: Melted Spring (Sinking II), Talisman Bundle (Rupture I), Rusted Muzzle (Bleed I),
    Hellterfly's Dream (Burn II)."""
    def card(x, gift_id, trial, level):
        return trials.Card(x, gifts.book()[gift_id], False, trial, level)
    return trials.TrialPage((card(242, 9054, "Defense Level Up", 1), card(506, 9013, "Defense Skill Up", 1),
                             card(771, 9089, "Take Less Damage", 2), card(1035, 9001, "Growth I", 2)), 2, "127.0.0.1:1")


def test_each_post_boss_cards_worth_is_drawn_on_the_game_scored_by_the_keywords(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, overlay=True, keywords=["Charge", "Sinking"])
    w.on_trials(post_boss_page())
    assert [x.rank for x in w.overlay.trials] == [1, 3, 4, 2] and w.overlay.isVisible()
    assert not w.overlay.expire.isActive(), "it stays until the worker tells the page went"
    w.set_keywords(["Burn"])
    assert [x.rank for x in w.overlay.trials] == [2, 3, 4, 1], "Hellterfly's Dream is the team's now"
    w.bridge.page_left.emit()
    assert not w.overlay.trials and not w.overlay.isVisible() and w.last_trials is None
    w.settings["overlay"] = False
    w.on_trials(post_boss_page())
    assert not w.overlay.trials, "the worth is drawn on the game only: nothing with the hints off"


def test_a_gift_in_the_gift_pane_leads_with_its_picture_which_grows_with_the_text(tmp_path, monkeypatch):
    from lc_helper import gifts

    w = shown(tmp_path, monkeypatch, open_sections=["event", "gift"])
    w.show_gifts([gifts.book()[9001]])
    page = w.gift_detail.toHtml()
    assert page.index("gift:9001") < page.index("keyword:Burn") < page.index("地獄蝶之夢")
    doc = w.gift_detail.document()
    picture = doc.resource(QTextDocument.ImageResource, QUrl("gift:9001"))
    assert len(inked_colours(picture.toImage())) > 200
    side = picture.width() / picture.devicePixelRatio()
    w.set_text_size("large")
    grown = doc.resource(QTextDocument.ImageResource, QUrl("gift:9001"))
    assert grown.width() / grown.devicePixelRatio() > side and "地獄蝶之夢" in w.gift_detail.toPlainText()
    w.clear_gifts()
    assert w.gift_view is None


def test_a_rule_parts_one_gift_from_the_next_in_the_gift_pane_and_the_search_results(tmp_path, monkeypatch):
    from PySide6.QtGui import QColor

    book = gifts.book()
    assert ui.gift_html([book[9001]]).count("<hr") == 0
    assert ui.gift_html([book[9001], book[9069], book[9002]], "畫面上可以選的飾品").count("<hr") == 2
    w = shown(tmp_path, monkeypatch, open_sections=["gift"])
    box = w.gift_search
    box.field.setText("burn")
    QTest.keyClick(box.field, Qt.Key_Return)
    popup = box.list.popup()
    image = popup.viewport().grab().toImage()
    row = popup.visualRect(popup.model().index(1, 0))  # not the lit row
    ratio = image.devicePixelRatio()
    column = [image.pixelColor(round(row.center().x() * ratio), y).name()
              for y in range(round((row.bottom() - 2) * ratio), round((row.bottom() + 1) * ratio) + 1)]
    assert QColor(ui.GIFT_RULE).name() in column, column


def test_the_fuse_pages_gift_is_listed_and_drawn_beside_the_wheel_until_its_centre_empties(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, overlay=True)
    cask = replace(gifts.read_gifts(screen("ShopFuseRecipe.png"), "fuse", None), source="127.0.0.1:1")
    w.on_gifts(cask)
    assert w.gift_detail.toPlainText().startswith("合成會得到的飾品") and "桶裝烈酒" in w.gift_detail.toPlainText()
    assert w.overlay.fuse[0]["id"] == 9180 and w.overlay.isVisible()
    w.on_gifts(gifts.GiftReading("fuse", (), "127.0.0.1:1"))  # a material taken out: no recipe met
    assert w.overlay.fuse is None and not w.overlay.isVisible()
    assert "桶裝烈酒" in w.gift_detail.toPlainText() and "沒讀到" not in w.gift_detail.toPlainText()
    w.on_gifts(cask)
    w.bridge.page_left.emit()
    assert w.overlay.fuse is None and not w.overlay.isVisible()
    w.settings["overlay"] = False
    w.on_gifts(cask)
    assert w.overlay.fuse is None, "drawn on the game only with the hints on"
