import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import fights  # noqa: E402
from lc_helper.battle import Fight  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)


class Tray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text):
        self.messages.append((title, text))


def window(tmp_path, monkeypatch, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(fights, "LOG", tmp_path / "battles.jsonl")
    w = ui.Window(StandIn)
    w.settings.update(settings)
    w.tray = Tray()
    return w


def test_a_battle_end_is_logged_and_notified(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, notify=True, stop_after_victory=True)
    w.on_fight(Fight("victory", 6, 95.0), "MuMuPlayer12")
    assert w.tray.messages == [("戰鬥勝利", "6 回合，1:35；自動戰鬥已停止")]
    assert [r["device"] for r in fights.load()] == ["MuMuPlayer12"]


def test_no_notification_when_turned_off(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch, notify=False)
    w.on_fight(Fight("wipe", 2, 30.0), "x")
    assert w.tray.messages == [] and len(fights.load()) == 1


def test_the_stop_after_victory_switch_reaches_the_worker(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.set_flag("stop_after_victory", True)
    assert ("set_stop_after_victory", True) in w.worker.sent and w.settings["stop_after_victory"]
