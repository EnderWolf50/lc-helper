import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QApplication, QCheckBox, QLabel, QToolButton, QWidget  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events, icons  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)


def settled(w):
    """w once it has laid itself out and fitted the detail pane, which takes a few event passes."""
    for _ in range(20):
        QApplication.processEvents()
    return w


def window(tmp_path, monkeypatch, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    if settings:
        ui.save_settings(ui.DEFAULTS | settings)
    w = ui.Window(StandIn)
    w.show()
    return settled(w)


def button(parent, text):
    return next(b for b in parent.findChildren(QAbstractButton) if b.text() == text)


def test_a_bigger_text_size_grows_the_text_and_the_window_and_is_kept(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert w.detail.font().pointSizeF() == 12
    width, pane = w.width(), w.detail.height()
    w.gear.click()
    button(w.settings_page, "大").click()
    w.gear.click()
    settled(w)
    assert QApplication.font().pointSizeF() == 13.5, "dialogs grow too"
    assert w.detail.font().pointSizeF() == 13.5
    assert w.width() > width and w.detail.height() > pane
    assert ui.load_settings()["text_size"] == "large"


def test_the_text_size_kept_is_the_one_a_new_window_opens_with(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small")
    assert w.detail.font().pointSizeF() == 10.5 and QApplication.font().pointSizeF() == 10.5
    assert button(w.settings_page, "小").isChecked() and not button(w.settings_page, "標準").isChecked()


def test_a_settings_file_with_unknown_choices_still_opens_the_window(tmp_path, monkeypatch):
    """settings.json is the user's to edit, and an older or newer lc-helper may have written it."""
    w = window(tmp_path, monkeypatch, text_size="huge", pc_input="laser", keywords=["Fire"], pin="yes",
               guard_mode="sometimes", guard=-2, open_sections="all")
    assert (w.settings["text_size"], w.settings["pc_input"], w.settings["keywords"], w.settings["pin"]) == \
        ("normal", "window", [], True)
    assert (w.settings["guard_mode"], w.settings["guard"], w.settings["open_sections"]) == ("none", 1, ["event"])
    assert w.detail.font().pointSizeF() == 12


def on_top(w):
    return bool(w.windowFlags() & Qt.WindowStaysOnTopHint)


def test_unpinning_makes_a_normal_window_where_it_was_and_is_kept(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.move(200, 150)
    assert w.pin.isChecked() and on_top(w) and w.windowType() == Qt.Tool
    pinned_tip = w.pin.toolTip()
    w.pin.click()
    assert not on_top(w) and w.windowType() == Qt.Window, "a taskbar entry finds it behind the game"
    assert w.isVisible() and w.pos().toTuple() == (200, 150)
    assert w.pin.toolTip() != pinned_tip
    assert ui.load_settings()["pin"] is False
    w.pin.click()
    assert on_top(w) and w.windowType() == Qt.Tool and w.isVisible()
    assert ui.load_settings()["pin"] is True


def test_a_window_left_unpinned_opens_unpinned(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, pin=False)
    assert not w.pin.isChecked() and not on_top(w) and w.windowType() == Qt.Window


def test_the_title_bar_holds_the_device_and_three_drawn_buttons_a_screen_reader_can_name(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    buttons = w.header.findChildren(QToolButton)
    assert [b.accessibleName() for b in buttons] == ["設定", "置頂", "關閉"]
    for b in buttons:
        assert b.text() == "" and not b.icon().isNull() and b.toolTip(), b.accessibleName()
    assert w.dot.text() == "" and not w.dot.pixmap().isNull() and w.dot.accessibleName()
    names = [label.text() for label in w.header.findChildren(QLabel)]
    assert names == ["LC Helper", "", "未連線"], "the title, the dot, the device"


def test_the_gear_shows_the_settings_in_place_of_the_main_page_and_takes_them_away_again(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    main_height = w.height()
    off = w.gear.icon().pixmap(16, 16).toImage()
    w.gear.click()
    settled(w)
    assert w.gear.isChecked() and w.settings_page.isVisible() and not w.main_page.isVisible()
    assert not w.start.isVisible() and not w.detail.isVisible()
    assert w.gear.icon().pixmap(16, 16).toImage() != off, "the gear is lit while the settings show"
    w.gear.click()
    settled(w)
    assert not w.settings_page.isVisible() and w.main_page.isVisible() and w.height() == main_height


def test_an_icon_is_drawn_with_the_pixels_of_a_150_percent_screen():
    QApplication.instance() or QApplication([])
    for name in icons.DRAW:
        pix = icons.pixmap(name, "#ffffff", 18, 1.5)
        assert (pix.width(), pix.height(), pix.devicePixelRatio()) == (27, 27, 1.5), name
        image = pix.toImage()
        assert any(image.pixelColor(x, y).alpha() for x in range(27) for y in range(27)), f"{name} draws nothing"


def test_every_keyword_a_team_is_built_on_has_the_games_icon_with_the_pixels_of_a_150_percent_screen():
    QApplication.instance() or QApplication([])
    for keyword in ui.recommend.CHOICES:
        pix = icons.keyword(keyword, 18, 1.5)
        assert (pix.width(), pix.height(), pix.devicePixelRatio()) == (27, 27, 1.5), keyword
        image = pix.toImage()
        inked = {image.pixelColor(x, y).rgb() for x in range(27) for y in range(27) if image.pixelColor(x, y).alpha()}
        assert len(inked) > 20, f"{keyword}: the game's picture, not a flat mark"


GLYPHS = set("★∞•")  # text characters that once stood in for drawn icons


def test_the_buttons_and_the_event_pane_draw_their_icons_instead_of_text_glyphs(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert not any(GLYPHS & set(b.text()) for b in w.findChildren(QAbstractButton))
    event = events.by_id()[SHORT]
    option = next(o for o in event["options"] if events.effects(o))
    page = ui.event_html(event, pick=(option, "有充能飾品"))
    assert not GLYPHS & set(page)
    assert page.count("icon:star") == 1 and "icon:bullet" in page


def test_the_pane_icons_are_drawn_at_the_text_size_with_the_pixels_of_the_screen(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small")
    doc = w.detail.document()

    def drawn(name):
        pix = doc.resource(QTextDocument.ImageResource, QUrl(f"icon:{name}"))
        return pix.width(), pix.devicePixelRatio()

    small = drawn("star")[0]
    assert drawn("star") == drawn("bullet") == (small, 1)
    w.set_text_size("large")
    large = drawn("star")[0]
    assert large > small, "they grow with the text"
    monkeypatch.setattr(w, "devicePixelRatioF", lambda: 1.5)
    QApplication.sendEvent(w, QEvent(QEvent.DevicePixelRatioChange))
    assert drawn("star") == drawn("bullet") == (round(large * 1.5), 1.5), "moved to a 150% screen"


def test_a_new_window_draws_the_pane_icons_at_its_text_size_from_the_start(tmp_path, monkeypatch):
    """Until the window shows, a widget holds Qt's default font: icons sized by it came out about half size."""
    w = window(tmp_path, monkeypatch, text_size="large")
    star = lambda: w.detail.document().resource(QTextDocument.ImageResource, QUrl("icon:star")).width()  # noqa: E731
    first = star()
    w.set_text_size("large")
    assert star() == first


def painted(w, widget, x, y):
    """The colour the window shows at (x, y) inside widget."""
    QApplication.processEvents()
    at = widget.mapTo(w, QPoint(x, y))
    return w.grab().toImage().pixelColor(at.x(), at.y())


def test_search_read_and_auto_read_share_one_row_and_the_helpers_are_pills_that_show_on_and_off_at_a_glance(
        tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, watch=False, skip=False, overlay=True)
    top = lambda widget: widget.mapTo(w, QPoint()).y()  # noqa: E731
    left = lambda widget: widget.mapTo(w, QPoint()).x()  # noqa: E731
    row = (w.event_search.field, w.read_button, w.watch)
    assert left(row[0]) < left(row[1]) < left(row[2]), "the search field, then 讀取, then 自動"
    assert len({top(x) for x in row}) == 1 and len({x.height() for x in row}) == 1, "one row"
    assert w.watch.text() == "自動" and w.read_button.text() == "讀取  F9" and "F9" in w.read_button.toolTip()
    assert not any(b.text() == "查詢" for b in w.findChildren(QAbstractButton)), "the icon in the field searches"
    pills = {"跳過劇情": w.skip_box, "遊戲內提示": w.overlay_box}
    assert [p.text() for p in pills.values()] == list(pills)
    assert not any("疊加" in b.text() + b.toolTip() for b in w.findChildren(QAbstractButton)), "the old name is gone"
    assert len({top(p) for p in pills.values()}) == 1, "one row"
    assert "畫面出現事件選項" in w.watch.toolTip()
    assert "一路推進到選項頁（不替你選）" in w.skip_box.toolTip()
    assert "把選項效果直接標在遊戲畫面上" in w.overlay_box.toolTip()
    inside = lambda p: painted(w, p, p.width() // 2, 3)  # noqa: E731  between the border and the text
    pane = QColor("#17130f")
    assert inside(w.watch) == pane and inside(w.overlay_box) == QColor("#6b4a1f"), "off is an outline, on is filled"
    assert painted(w, w.overlay_box, 1, 1) == pane, "round ends"
    w.watch.click()
    assert inside(w.watch) == QColor("#6b4a1f") and w.worker.sent[-1] == ("set_watch", True)
    w.skip_box.click()
    w.say_skip("自動跳過：等選項頁")
    QApplication.processEvents()
    assert w.skip_state.isVisible() and w.skip_state.mapTo(w, QPoint()).y() > w.skip_box.mapTo(w, QPoint()).y()


def test_a_folded_section_sums_itself_up_in_its_head_and_a_new_window_opens_it_folded(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, watch=True, skip=False, keywords=["Charge", "Bleed"])
    section = w.sections["event"]
    assert section.head.isChecked() and w.detail.isVisible() and section.summary.text() == ""
    height = w.height()
    section.head.click()
    settled(w)
    assert not w.detail.isVisible() and w.height() < height
    assert section.summary.text() == "自動讀取開 · 推薦 充能 › 流血"
    assert ui.load_settings()["open_sections"] == []
    w.set_watch(False)
    w.set_skip(True)
    assert section.summary.text() == "跳過劇情開 · 推薦 充能 › 流血", "the summary follows the switches"
    again = ui.Window(StandIn)
    again.show()
    settled(again)
    assert not again.sections["event"].head.isChecked() and not again.detail.isVisible()
    again.sections["event"].head.click()
    assert again.detail.isVisible() and ui.load_settings()["open_sections"] == ["event"]


def test_a_summary_too_long_for_the_head_stays_inside_it(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, watch=True, skip=True, keywords=["Charge", "Bleed", "Burn", "Tremor"],
               open_sections=[])
    head, summary = w.sections["event"].head, w.sections["event"].summary
    assert summary.width() < summary.fontMetrics().horizontalAdvance(summary.text()), "longer than its room"
    assert summary.mapTo(w, QPoint(summary.width(), 0)).x() <= head.mapTo(w, QPoint(head.width(), 0)).x()
    assert w.root.width() == ui.scaled(380, 12), "the window keeps its width"


def page_parts(page):
    """[(group title, [check box, link, row label and button texts])] as the settings page shows them, top down."""
    groups = []
    widgets = sorted((w for w in page.findChildren(QWidget)
                      if isinstance(w, (QLabel, QAbstractButton)) and w.isVisibleTo(page)),
                     key=lambda w: (w.mapTo(page, QPoint()).y(), w.mapTo(page, QPoint()).x()))
    for widget in widgets:
        if widget.objectName() == "section":
            groups.append((widget.text(), []))
        elif widget.text():
            groups[-1][1].append(widget.text())
    return groups


def test_the_settings_page_holds_the_battle_device_display_and_hotkey_settings_in_groups(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.gear.click()
    settled(w)
    assert page_parts(w.settings_page) == [
        ("戰鬥", ["回合播放時按住畫面（加快 E.G.O 動畫）", "勝利後停止自動戰鬥", "戰鬥結束時跳出 Windows 通知", "戰鬥紀錄…"]),
        ("裝置", ["重新尋找", "PC 點擊", "觸控", "移視窗", "借游標", "前景"]),
        ("顯示", ["字級", "小", "標準", "大"]),
        ("熱鍵", ["開始／停止  F8　　讀取畫面  F9", "修改…"]),
    ]
    assert w.device_box.currentText() == "自動偵測"


def test_every_battle_and_device_setting_still_does_what_it_did(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, hold=True, stop_after_victory=False, notify=True)
    opened = []
    monkeypatch.setattr(ui.FightLog, "exec", lambda self: opened.append("戰鬥紀錄"))
    monkeypatch.setattr(ui.HotkeyDialog, "exec", lambda self: opened.append("熱鍵設定"))
    checks = {box.text(): box for box in w.settings_page.findChildren(QCheckBox)}
    assert [box.isChecked() for box in checks.values()] == [True, False, True]
    for box in checks.values():
        box.click()
    for text in ("戰鬥紀錄…", "重新尋找", "修改…"):
        button(w.settings_page, text).click()
    assert w.worker.sent == [("set_hold", False), ("set_stop_after_victory", True), ("scan",)]
    assert (w.settings["hold"], w.settings["stop_after_victory"], w.settings["notify"]) == (False, True, False)
    assert opened == ["戰鬥紀錄", "熱鍵設定"]


def test_the_pc_click_and_text_size_rows_show_the_current_choice_and_explain_each(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small", pc_input="cursor")
    page = w.settings_page
    on = lambda texts: [t for t in texts if button(page, t).isChecked()]  # noqa: E731
    assert on(["觸控", "移視窗", "借游標", "前景"]) == ["借游標"] and on(["小", "標準", "大"]) == ["小"]
    assert button(page, "觸控").toolTip() == "合成觸控（不動滑鼠，遊戲要露出來）"
    assert button(page, "移視窗").toolTip() == "移動視窗（不動滑鼠，遊戲可在背景；點擊時視窗瞬間移到游標下再移回，回合播放時不按住）"
    button(page, "移視窗").click()
    assert on(["觸控", "移視窗", "借游標", "前景"]) == ["移視窗"]
    assert w.worker.sent[-1] == ("set_pc_input", "window") and w.settings["pc_input"] == "window"
    w.set_text_size("large")
    assert on(["小", "標準", "大"]) == ["大"]


def test_the_settings_rows_start_at_one_left_edge_and_their_controls_share_one_height(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.gear.click()
    settled(w)
    page = w.settings_page
    left = lambda widget: widget.mapTo(page, QPoint()).x()  # noqa: E731
    assert left(button(page, "觸控")) == left(button(page, "小")), "the choices line up after their labels"
    assert len({left(widget) for widget in (w.device_box, button(page, "回合播放時按住畫面（加快 E.G.O 動畫）"),
                                            w.hotkey_text, *page.findChildren(QLabel, "section"))}) == 1
    heights = {widget.height() for widget in (w.device_box, button(page, "重新尋找"), button(page, "觸控"),
                                              button(page, "大"), button(page, "修改…"))}
    assert len(heights) == 1, heights


SHORT, LONG = 901101, 971097  # an event whose effects fit the pane at the large size, and one that scrolls in it


def test_the_pane_takes_its_text_up_to_the_preferred_height_and_the_room_on_screen_but_never_under_the_floor():
    def one(content, room):
        return ui.pane_heights([content], preferred=360, room=room, floor=80)[0]

    assert one(content=200, room=500) == 200
    assert one(content=600, room=500) == 360, "the rest scrolls"
    assert one(content=600, room=250) == 250, "the window ends on the screen"
    assert one(content=30, room=500) == 80, "a short text gets the floor"
    assert one(content=600, room=20) == 80, "a window placed low keeps a few lines"


def test_two_panes_share_the_room_and_the_taller_gives_way_first():
    def two(contents, room):
        return ui.pane_heights(contents, preferred=360, room=room, floor=80)

    assert two([600, 150], room=900) == [360, 150], "room for both"
    assert two([600, 150], room=400) == [250, 150], "the long one scrolls, the short one shows whole"
    assert two([150, 600], room=400) == [150, 250], "whichever comes first"
    assert two([600, 500], room=400) == [200, 200], "both long: an even share"
    assert two([600, 500], room=100) == [80, 80], "a window placed low keeps a few lines in each"
    assert two([30, 30], room=500) == [80, 80]


def test_the_empty_pane_is_a_few_lines_and_an_event_gets_the_height_its_text_needs(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="large")
    w.move(w.screen().availableGeometry().topLeft())
    settled(w)
    empty, line = w.detail.height(), w.detail.fontMetrics().lineSpacing()
    assert 2 * line < empty < 5 * line, "about three lines"
    w.show_event(events.by_id()[SHORT])
    settled(w)
    short = w.detail.height()
    assert short > empty and w.detail.verticalScrollBar().maximum() == 0, "a short event shows whole"
    w.show_event(events.by_id()[LONG])
    settled(w)
    assert short < w.detail.height() <= ui.scaled(300, 13.5) and w.detail.verticalScrollBar().maximum() > 0


def test_a_long_event_at_the_large_text_size_keeps_the_window_on_a_short_screen(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="large")
    screen = w.screen().availableGeometry()
    w.move(screen.left(), screen.bottom() - 700)  # less room than a large window with a long event takes
    w.show_event(events.by_id()[LONG])
    settled(w)
    assert w.frameGeometry().bottom() <= screen.bottom()
    assert w.detail.verticalScrollBar().maximum() > 0, "the rest scrolls"


def test_moving_the_window_down_shrinks_the_pane_and_moving_it_back_up_restores_it(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    screen = w.screen().availableGeometry()
    w.move(screen.topLeft())
    w.show_event(events.by_id()[LONG])
    settled(w)
    high = w.detail.height()
    w.move(screen.left(), screen.top() + 250)
    settled(w)
    assert w.detail.height() < high and w.frameGeometry().bottom() <= screen.bottom()
    w.move(screen.topLeft())
    settled(w)
    assert w.detail.height() == high


def test_a_dragged_window_keeps_its_bottom_on_the_screen_at_every_step_while_it_is_held(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    screen = w.screen().availableGeometry()
    w.move(screen.topLeft())
    w.show_event(events.by_id()[LONG])
    settled(w)
    high = w.detail.height()
    free = screen.bottom() - ui.SCREEN_GAP - w.frameGeometry().bottom()  # px the window can go down untouched

    def mouse(kind, at):
        button = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        QApplication.sendEvent(w, QMouseEvent(kind, QPointF(w.mapFromGlobal(at)), QPointF(at), Qt.LeftButton, button,
                                              Qt.NoModifier))

    grab = w.header.mapToGlobal(QPoint(20, 10))
    mouse(QEvent.MouseButtonPress, grab)
    heights = []
    for down in (free + 50, free + 150, free + 250, free + 150, 0):
        mouse(QEvent.MouseMove, grab + QPoint(0, down))
        settled(w)
        assert w.y() == screen.top() + down, "the window stays under the hand"
        assert w.frameGeometry().bottom() <= screen.bottom(), f"{down} px down, still held"
        heights.append(w.detail.height())
    assert high > heights[0] > heights[1] > heights[2], "the pane shrinks as the window goes down"
    assert heights[2] < heights[3] < heights[4] == high, "and grows back on the way up"
    mouse(QEvent.MouseButtonRelease, grab)
    settled(w)
    assert w.y() == screen.top() and w.detail.height() == high, "letting go changes nothing"


def test_a_fit_that_runs_before_the_window_has_caught_up_with_the_last_one_lands_on_the_same_height(tmp_path,
                                                                                                    monkeypatch):
    """The fit timer can fire while a new pane height is still on its way up the layouts: a fit that read the
    window's bottom then chased the one before it, and the pane and the window never settled."""
    w = window(tmp_path, monkeypatch)
    screen = w.screen().availableGeometry()
    w.move(screen.topLeft())
    w.show_event(events.by_id()[LONG])
    settled(w)
    w.move(screen.left(), screen.top() + 250)
    w.fit_panes()
    fitted = w.detail.height()
    w.fit_panes()
    assert w.detail.height() == fitted
    settled(w)
    assert w.detail.height() == fitted and w.frameGeometry().bottom() <= screen.bottom()


def test_a_long_event_and_a_screen_of_gifts_together_keep_the_window_on_the_screen(tmp_path, monkeypatch):
    from lc_helper import gifts

    w = window(tmp_path, monkeypatch, open_sections=["event", "gift"])
    screen = w.screen().availableGeometry()
    w.move(screen.topLeft())
    w.show_event(events.by_id()[LONG])
    w.show_gifts(gifts.search("burn", limit=4))
    settled(w)
    assert w.detail.isVisible() and w.gift_detail.isVisible()
    assert w.frameGeometry().bottom() <= screen.bottom()
    assert w.detail.verticalScrollBar().maximum() > 0, "the rest scrolls"
    w.sections["gift"].head.click()
    settled(w)
    assert not w.gift_detail.isVisible() and w.frameGeometry().bottom() <= screen.bottom()
    taller = w.detail.height()
    w.sections["gift"].head.click()
    settled(w)
    assert w.detail.height() < taller, "the event pane gives back the room the gift pane takes"
