import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events  # noqa: E402


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
    w.keyword_box.setCurrentIndex(w.keyword_box.findData("Charge"))
    w.set_keyword(w.keyword_box.currentIndex())
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


def test_query_and_enter_search_at_once_and_enter_on_the_list_picks_the_first_hit(tmp_path, monkeypatch):
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
    box.go.click()
    assert len(searches) == 2 and rows(box)[0] == ui.result_text(first), "查詢 searches"


def test_clearing_the_event_search_empties_the_pane(tmp_path, monkeypatch, screen):
    w = shown(tmp_path, monkeypatch)
    placeholder = w.detail.toPlainText()
    box = w.event_search
    box.field.setText("hand")
    box.go.click()
    click_row(box, 0)
    assert w.detail.toPlainText() != placeholder
    box.field.findChild(QToolButton).click()
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
    box.go.click()
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
        box.go.click()
        found = gifts.search(query, limit=8)
        assert rows(box)[0].startswith(gifts.label(found[0])), query
    click_row(box, 0)
    assert w.gift_detail.toPlainText().startswith(gifts.label(found[0])) and w.detail.toPlainText() == event_text
    w.sections["gift"].head.click()
    assert w.sections["gift"].summary.text() == f"最近：{found[0]['zh']}"


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
