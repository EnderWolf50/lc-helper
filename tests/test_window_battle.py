import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper.battle import FOREVER, Phase, Pick, Plan, Status  # noqa: E402
from lc_helper.device import PC, Target  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)

    def stop_battle(self):
        self.sent.append(("stop_battle",))


def window(tmp_path, monkeypatch, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    if settings:
        ui.save_settings(ui.DEFAULTS | settings)
    w = ui.Window(StandIn)
    w.show()
    for _ in range(5):
        QApplication.processEvents()
    return w


def painted(w, widget, x, y):
    """The colour the window shows at (x, y) inside widget."""
    QApplication.processEvents()
    at = widget.mapTo(w, QPoint(x, y))
    return w.grab().toImage().pixelColor(at.x(), at.y())


def test_start_is_green_with_a_play_icon_and_a_red_stop_while_the_battle_runs(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, guard_mode="forever", hold=False)
    inside = lambda: painted(w, w.start, 8, w.start.height() // 2)  # noqa: E731  left of the text
    icon = lambda: w.start.icon().pixmap(16, 16).toImage()  # noqa: E731
    assert w.start.text() == "開始自動戰鬥  F8" and inside() == QColor("#2f6b3a")
    play = icon()
    w.start.click()
    assert w.worker.sent[-1] == ("start_battle", Plan(Pick.WIN_RATE, FOREVER), False)
    assert w.start.text() == "停止  F8" and inside() == QColor("#9e2b22") and icon() != play
    w.start.click()
    assert w.worker.sent[-1] == ("stop_battle",)
    w.on_battle(Status(Phase.STOPPED, Plan(), 0))
    assert w.start.text() == "開始自動戰鬥  F8" and inside() == QColor("#2f6b3a") and icon() == play


def test_the_status_line_shows_a_running_battle_and_why_one_stopped_and_takes_no_room_otherwise(tmp_path,
                                                                                               monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert not w.status.isVisible()
    w.on_battle(Status(Phase.PLAYING, Plan(Pick.DAMAGE, 0), 2))
    assert w.status.isVisible() and w.status.text() == "回合進行中 · 傷害 · 已打 2 回合"
    w.on_battle(Status(Phase.STOPPED, Plan(), 2))
    assert not w.status.isVisible(), "stopped by the user: nothing to say"
    w.on_battle(Status(Phase.STOPPED, Plan(), 4, "連續 3 個回合按 START 都沒開始，自動戰鬥停止"))
    assert w.status.isVisible() and w.status.text().endswith("連續 3 個回合按 START 都沒開始，自動戰鬥停止")


def test_the_skill_pick_is_two_chinese_choices_that_reach_the_battle(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    win_rate, damage = w.picks.buttons.values()
    assert (win_rate.text(), damage.text()) == ("勝率", "傷害") and win_rate.isChecked()
    assert "Win Rate" in win_rate.toolTip() and "Damage" in damage.toolTip(), "the game's own words, in the tooltip"
    damage.click()
    assert damage.isChecked() and not win_rate.isChecked()
    assert w.worker.sent[-1] == ("set_pick", Pick.DAMAGE) and w.plan().pick is Pick.DAMAGE


def test_the_battle_bar_lines_up_on_one_left_edge_with_one_height_for_its_row(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, guard_mode="turns")
    row = [*w.picks.buttons.values(), w.guard_box, w.guard_spin]
    assert len({widget.height() for widget in row}) == 1
    assert len({widget.mapTo(w, QPoint()).y() for widget in row}) == 1
    left = lambda widget: widget.mapTo(w, QPoint()).x()  # noqa: E731
    w.on_battle(Status(Phase.PLAYING, Plan(), 1))
    assert left(w.picks) == left(w.start) == left(w.status)
    right = lambda widget: widget.mapTo(w, QPoint(widget.width(), 0)).x()  # noqa: E731
    assert right(w.guard_spin) == right(w.start)


def test_the_title_bar_names_the_device_and_a_failed_connection_says_why(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.on_device("connecting", "自動")
    assert w.device_name.text() == "連線中" and w.dot.property("state") == "connecting"
    w.on_device("error", "找不到模擬器 （找到：無）")
    assert w.device_name.text() == "連線失敗" and w.dot.property("state") == "error"
    assert w.status.isVisible() and w.status.text() == "找不到模擬器 （找到：無）"
    w.on_device("connected", "MuMu 0")
    assert w.device_name.text() == "MuMu 0" and w.dot.property("state") == "connected"
    assert not w.status.isVisible(), "the connection is in the title bar, not repeated below"


def test_the_device_list_names_each_device_by_its_short_name_and_port(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, address="127.0.0.1:16416")
    w.on_targets([Target("MuMuPlayer12", "127.0.0.1:16384"), Target("MuMuPlayer12", "127.0.0.1:16416"),
                  Target("Limbus PC", PC)])
    assert [w.device_box.itemText(i) for i in range(w.device_box.count())] == \
        ["自動偵測", "MuMu 0（16384）", "MuMu 1（16416）", "PC 版"]
    assert w.device_box.currentText() == "MuMu 1（16416）"
    w.device_box.activated.emit(3)
    assert w.worker.sent[-1] == ("connect", PC)


def choose_guard(w, name):
    index = w.guard_box.findText(name)
    w.guard_box.setCurrentIndex(index)
    w.guard_box.activated.emit(index)


def test_the_guard_list_names_the_three_ways_and_only_the_first_turns_take_a_count(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, guard_mode="none", guard=3)
    assert [w.guard_box.itemText(i) for i in range(w.guard_box.count())] == ["不防禦", "防禦前幾回合", "全程防禦"]
    assert w.guard_box.currentText() == "不防禦" and not w.guard_spin.isVisible()
    choose_guard(w, "防禦前幾回合")
    assert w.guard_spin.isVisible() and w.guard_spin.value() == 3
    choose_guard(w, "全程防禦")
    assert not w.guard_spin.isVisible()


@pytest.mark.parametrize("name, mode, guard", [("不防禦", "none", 0), ("防禦前幾回合", "turns", 3),
                                               ("全程防禦", "forever", FOREVER)])
def test_each_guard_reaches_the_battle_and_is_kept(tmp_path, monkeypatch, name, mode, guard):
    w = window(tmp_path, monkeypatch, guard_mode="turns" if mode != "turns" else "none", guard=3)
    choose_guard(w, name)
    assert w.worker.sent[-1] == ("set_guard", guard)
    assert w.plan() == Plan(Pick.WIN_RATE, guard)
    assert w.settings["guard_mode"] == mode


def test_a_new_count_reaches_the_battle(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, guard_mode="turns", guard=3)
    w.guard_spin.setValue(5)
    assert w.worker.sent[-1] == ("set_guard", 5) and w.settings["guard"] == 5


def test_the_count_goes_down_with_the_battle_to_0_and_back_to_the_setting_once_it_stops(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, guard_mode="turns", guard=2)
    for left in (2, 1, 0):
        w.on_battle(Status(Phase.PLAYING, Plan(Pick.WIN_RATE, left), 3 - left))
        assert w.guard_spin.value() == left
    assert w.worker.sent == [], "the count going down is not the user's change"
    w.on_battle(Status(Phase.STOPPED, Plan(Pick.WIN_RATE, 0), 3))
    assert w.guard_spin.value() == 2 and w.settings["guard"] == 2
