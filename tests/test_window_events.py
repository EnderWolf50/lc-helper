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
