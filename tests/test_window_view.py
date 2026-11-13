import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QAction, QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyleFactory, QToolButton, QWidgetAction  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import icons  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)


def window(tmp_path, monkeypatch, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    if settings:
        ui.save_settings(ui.DEFAULTS | settings)
    w = ui.Window(StandIn)
    w.show()
    QApplication.processEvents()
    return w


def menu_action(w, text):
    return next(a for a in w.findChildren(QAction) if a.text() == text)


def test_a_bigger_text_size_grows_the_text_and_the_window_and_is_kept(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert w.detail.font().pointSizeF() == 12
    width, pane = w.width(), w.detail.height()
    menu_action(w, "大").trigger()
    QApplication.processEvents()
    assert QApplication.font().pointSizeF() == 13.5, "menus and dialogs grow too"
    assert w.detail.font().pointSizeF() == 13.5
    assert w.width() > width and w.detail.height() > pane
    assert ui.load_settings()["text_size"] == "large"


def test_the_text_size_kept_is_the_one_a_new_window_opens_with(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, text_size="small")
    assert w.detail.font().pointSizeF() == 10.5 and QApplication.font().pointSizeF() == 10.5
    assert menu_action(w, "小").isChecked()


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
