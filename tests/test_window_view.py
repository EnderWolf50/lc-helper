import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402


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
