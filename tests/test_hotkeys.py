import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from lc_helper import app as ui  # noqa: E402


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def test_a_hotkey_is_one_key_with_optional_modifiers():
    assert ui.parse_hotkey("F8") == (0, 0x77)
    assert ui.parse_hotkey("Ctrl+Shift+F8") == (0x2 | 0x4, 0x77)
    assert ui.parse_hotkey("Alt+Q") == (0x1, ord("Q"))
    assert ui.parse_hotkey("F24") == (0, 0x87)
    for not_one_key in ("", "Ctrl", "Ctrl+", "F8, F9", "Hyper+F8"):
        assert ui.parse_hotkey(not_one_key) is None, not_one_key


def test_the_dialog_takes_two_distinct_hotkeys(qt):
    dialog = ui.HotkeyDialog({"battle": "F8", "read": "F9"})
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert ok.isEnabled()
    dialog.edits["read"].setKeySequence(QKeySequence("F8"))
    assert not ok.isEnabled() and "同一個" in dialog.problem.text()
    dialog.edits["read"].setKeySequence(QKeySequence("Ctrl+Shift+Q"))
    assert ok.isEnabled()
    assert dialog.keys() == {"battle": "F8", "read": "Ctrl+Shift+Q"}


class Refusing:
    """Hotkeys that Windows refuses for the keys in held, as when another program registered them."""

    def __init__(self, held):
        self.held, self.registered = held, {}

    def add(self, hid, text, action):
        if text in self.held:
            return False
        self.registered[hid] = text
        return True

    def clear(self):
        self.registered = {}


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)


def test_new_hotkeys_are_registered_again_and_shown(qt, tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    hotkeys = Refusing(held={"F9"})
    window = ui.Window(StandIn, hotkeys)
    assert window.apply_hotkeys() == ["F9"]
    assert "F9" in window.status.text()
    window.settings["hotkeys"] = {"battle": "Ctrl+F8", "read": "Ctrl+F9"}
    assert window.apply_hotkeys() == []
    assert hotkeys.registered == {ui.HOTKEY_IDS["battle"]: "Ctrl+F8", ui.HOTKEY_IDS["read"]: "Ctrl+F9"}
    assert "Ctrl+F8" in window.start.text() and "Ctrl+F9" in window.read_button.text()
