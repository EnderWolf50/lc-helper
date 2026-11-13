import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

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


def test_the_recommended_option_is_starred_in_the_pane_and_on_the_game(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keyword="Charge", overlay=True)
    w.on_event(events.read_screen(screen("EventChoices.png")))
    assert "推薦：判定通過獲得飾品，有充能飾品" in w.detail.toPlainText()
    marks = {item.box[1]: item.mark for item in w.overlay.items}
    assert marks == {217: "", 327: "★"}  # Push the hand away: a Charge gift on a pass
    w.overlay.hide_labels()


def test_no_keyword_no_star_and_a_new_keyword_ranks_again(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keyword=None, overlay=True)
    w.on_event(events.read_screen(screen("EventChoices.png")))
    assert "★" not in w.detail.toPlainText() and all(not item.mark for item in w.overlay.items)
    w.keyword_box.setCurrentIndex(w.keyword_box.findData("Charge"))
    w.set_keyword(w.keyword_box.currentIndex())
    assert "推薦" in w.detail.toPlainText() and any(item.mark for item in w.overlay.items)
    w.overlay.hide_labels()


def test_a_grey_option_is_never_starred(tmp_path, monkeypatch, screen):
    w = window(tmp_path, monkeypatch, keyword="Poise", overlay=True)
    reading = events.read_screen(screen("EventChoicesUsed.png"))
    w.on_event(reading)
    starred = [item for item in w.overlay.items if item.mark]
    assert starred and all(item.box[1] != 197 for item in starred)  # the grey first option
    w.overlay.hide_labels()
