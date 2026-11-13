import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QAction, QColor, QMouseEvent, QTextDocument  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QStyleFactory, QToolButton,  # noqa: E402
                               QWidgetAction)

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


def menu_action(w, text):
    return next(a for a in w.findChildren(QAction) if a.text() == text)


def test_a_bigger_text_size_grows_the_text_and_the_window_and_is_kept(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert w.detail.font().pointSizeF() == 12
    width, pane = w.width(), w.detail.height()
    menu_action(w, "大").trigger()
    settled(w)
    assert QApplication.font().pointSizeF() == 13.5, "menus and dialogs grow too"
    assert w.detail.font().pointSizeF() == 13.5
    assert w.width() > width and w.detail.height() > pane
    assert ui.load_settings()["text_size"] == "large"


def test_the_text_size_kept_is_the_one_a_new_window_opens_with(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small")
    assert w.detail.font().pointSizeF() == 10.5 and QApplication.font().pointSizeF() == 10.5
    assert menu_action(w, "小").isChecked()


def test_a_settings_file_with_unknown_choices_still_opens_the_window(tmp_path, monkeypatch):
    """settings.json is the user's to edit, and an older or newer lc-helper may have written it."""
    w = window(tmp_path, monkeypatch, text_size="huge", pc_input="laser", keyword="Fire", pin="yes")
    assert (w.settings["text_size"], w.settings["pc_input"], w.settings["keyword"], w.settings["pin"]) == \
        ("normal", "touch", None, True)
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


def test_the_header_buttons_are_drawn_icons_a_screen_reader_can_name(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    buttons = w.header.findChildren(QToolButton)
    assert len(buttons) == 4
    for b in buttons:
        assert b.text() == "" and not b.icon().isNull() and b.accessibleName() and b.toolTip(), b.accessibleName()
    assert w.dot.text() == "" and not w.dot.pixmap().isNull() and w.dot.accessibleName()
    assert w.fold.toolTip() == "收合事件查詢"
    w.fold.click()
    assert w.fold.toolTip() == "展開事件查詢"


def test_an_icon_is_drawn_with_the_pixels_of_a_150_percent_screen():
    QApplication.instance() or QApplication([])
    for name in icons.DRAW:
        pix = icons.pixmap(name, "#ffffff", 18, 1.5)
        assert (pix.width(), pix.height(), pix.devicePixelRatio()) == (27, 27, 1.5), name
        image = pix.toImage()
        assert any(image.pixelColor(x, y).alpha() for x in range(27) for y in range(27)), f"{name} draws nothing"


GLYPHS = set("★∞•")  # text characters that once stood in for drawn icons


def test_the_buttons_and_the_event_pane_draw_their_icons_instead_of_text_glyphs(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert w.forever.text() == "無限防禦" and not w.forever.icon().isNull()
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


def painted(w, widget, x, y):
    """The colour the window shows at (x, y) inside widget."""
    QApplication.processEvents()
    at = widget.mapTo(w, QPoint(x, y))
    return w.grab().toImage().pixelColor(at.x(), at.y())


def test_the_event_switches_are_one_row_of_short_pills_that_show_on_and_off_at_a_glance(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, watch=False, skip=False, overlay=True)
    pills = {"自動讀取": w.watch, "跳過劇情": w.skip_box, "疊加顯示": w.overlay_box}
    assert [p.text() for p in pills.values()] == list(pills)
    assert len({p.mapTo(w, QPoint()).y() for p in pills.values()}) == 1, "one row"
    assert "畫面出現事件選項就顯示" in w.watch.toolTip()
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


def menu_sections(menu):
    """[(section title, [item texts])] as the menu shows them: a submenu by its title, items before any title under ""."""
    sections = [("", [])]
    for a in menu.actions():
        if isinstance(a, QWidgetAction):
            sections.append((a.defaultWidget().text(), []))
        elif not a.isSeparator():
            sections[-1][1].append(a.text())
    return [s for s in sections if s != ("", [])]


def test_the_more_menu_groups_its_settings_into_three_titled_sections(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    menu = w.more.menu()
    assert menu_sections(menu) == [
        ("戰鬥", ["回合播放時按住畫面（加快 E.G.O 動畫）", "勝利後停止自動戰鬥", "戰鬥結束時跳出 Windows 通知", "戰鬥紀錄…"]),
        ("裝置", ["重新尋找模擬器與 PC 版", "PC 版點擊方式：合成觸控"]),
        ("顯示與操作", ["字級：標準", "熱鍵設定…"]),
    ]
    actions = menu.actions()
    heads = [i for i, a in enumerate(actions) if isinstance(a, QWidgetAction)]
    assert all(actions[i - 1].isSeparator() and not actions[i - 1].text() for i in heads[1:]), "a line between groups"


@pytest.mark.parametrize("style", ["windows11", "windowsvista", "Fusion"])
def test_the_arrow_keys_and_the_mouse_pass_over_the_section_titles(tmp_path, monkeypatch, style):
    w = window(tmp_path, monkeypatch)
    menu = w.more.menu()
    look = QStyleFactory.create(style)
    look.setParent(menu)  # the menu keeps the style alive after the test
    menu.setStyle(look)
    heads = [a for a in menu.actions() if isinstance(a, QWidgetAction)]
    items = [a for a in menu.actions() if a not in heads and not a.isSeparator()]
    assert len(heads) == 3 and not any(h.isEnabled() for h in heads)
    menu.popup(QPoint())
    QApplication.processEvents()
    seen = []
    for _ in menu.actions():
        QTest.keyClick(menu, Qt.Key_Down)
        seen.append(menu.activeAction())
    assert not set(seen) & set(heads), "Down never stops on a title"
    assert set(seen) == set(items), "Down reaches every item"
    fired = []
    menu.triggered.connect(fired.append)
    for h in heads:
        QTest.mouseClick(h.defaultWidget(), Qt.LeftButton)
    assert menu.isVisible() and fired == [], "a click on a title does nothing"
    menu.hide()


def test_a_submenu_title_names_the_current_choice(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small", pc_input="cursor")
    menu = w.more.menu()
    titles = lambda: [a.text() for a in menu.actions() if a.menu()]  # noqa: E731

    def checked(title):
        submenu = next(a.menu() for a in menu.actions() if a.text() == title)
        return [a.text() for a in submenu.actions() if a.isChecked()]

    assert titles() == ["PC 版點擊方式：借用游標", "字級：小"]
    w.set_text_size("large")
    w.set_pc_input("window")
    assert titles() == ["PC 版點擊方式：移動視窗", "字級：大"]
    assert checked("字級：大") == ["大"] and checked("PC 版點擊方式：移動視窗")[0].startswith("移動視窗（")
    menu_action(w, "標準").trigger()
    next(a for a in w.findChildren(QAction) if a.text().startswith("合成觸控（")).trigger()
    assert titles() == ["PC 版點擊方式：合成觸控", "字級：標準"]
    assert w.worker.sent[-1] == ("set_pc_input", "touch") and ui.load_settings()["text_size"] == "normal"


def test_every_menu_item_still_does_what_it_did(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, hold=True, stop_after_victory=False, notify=True)
    opened = []
    monkeypatch.setattr(ui.FightLog, "exec", lambda self: opened.append("戰鬥紀錄"))
    monkeypatch.setattr(ui.HotkeyDialog, "exec", lambda self: opened.append("熱鍵設定"))
    for text in ("回合播放時按住畫面（加快 E.G.O 動畫）", "勝利後停止自動戰鬥", "戰鬥結束時跳出 Windows 通知",
                 "戰鬥紀錄…", "重新尋找模擬器與 PC 版", "熱鍵設定…"):
        menu_action(w, text).trigger()
    assert w.worker.sent == [("set_hold", False), ("set_stop_after_victory", True), ("scan",)]
    assert (w.settings["hold"], w.settings["stop_after_victory"], w.settings["notify"]) == (False, True, False)
    assert opened == ["戰鬥紀錄", "熱鍵設定"]


SHORT, LONG = 901101, 971097  # an event whose effects fit the pane at the large size, and one that scrolls in it


def test_the_pane_takes_its_text_up_to_the_preferred_height_and_the_room_on_screen_but_never_under_the_floor():
    assert ui.pane_height(content=200, preferred=360, room=500, floor=80) == 200
    assert ui.pane_height(content=600, preferred=360, room=500, floor=80) == 360, "the rest scrolls"
    assert ui.pane_height(content=600, preferred=360, room=250, floor=80) == 250, "the window ends on the screen"
    assert ui.pane_height(content=30, preferred=360, room=500, floor=80) == 80, "a short text gets the floor"
    assert ui.pane_height(content=600, preferred=360, room=20, floor=80) == 80, "a window placed low keeps a few lines"


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

    def mouse(kind, at):
        button = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        QApplication.sendEvent(w, QMouseEvent(kind, QPointF(w.mapFromGlobal(at)), QPointF(at), Qt.LeftButton, button,
                                              Qt.NoModifier))

    grab = w.header.mapToGlobal(QPoint(20, 10))
    mouse(QEvent.MouseButtonPress, grab)
    heights = []
    for down in (100, 200, 300, 200, 0):
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
    w.fit_detail()
    fitted = w.detail.height()
    w.fit_detail()
    assert w.detail.height() == fitted
    settled(w)
    assert w.detail.height() == fitted and w.frameGeometry().bottom() <= screen.bottom()
