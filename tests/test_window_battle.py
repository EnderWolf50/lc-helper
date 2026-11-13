import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper.battle import FOREVER, Phase, Pick, Plan, Status  # noqa: E402


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
