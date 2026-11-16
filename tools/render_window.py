"""Render the floating window offscreen in the states a user sees, as PNGs: the evidence for UI changes.

Usage: uv run python tools/render_window.py [out folder]   (default .local/evidence)

No emulator: a stand-in worker takes the commands; the battle states are fed in as the real worker would, and the
event pane shows what the real reader makes of maalc's EventChoices.png capture (OCR included).

The states: the main page as it opens (window-main), the settings page at each text size (window-settings-*), a
battle running (window-battle-running), each text size (window-text-*), four recommended keywords at each text size
(window-keywords-four-*), a gift screen's gifts at each text size (window-gifts-*), the ＋ 體系 menu open
(window-keyword-menu), a search list dropped down (window-search, window-gift-search: a list or a menu is a window of
its own, painted where it shows), both sections open on the screen (window-both-open) and every section folded
(window-folded).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
os.environ.setdefault("QT_QPA_FONTDIR", str(FONTS))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events, vision  # noqa: E402
from lc_helper.battle import FOREVER, Phase, Pick, Plan, Status  # noqa: E402
from lc_helper.device import PC, Target  # noqa: E402
from maalc_checkout import maalc_dir  # noqa: E402


class StandIn:
    def __init__(self, callbacks):
        self.sent = []

    def send(self, *command):
        self.sent.append(command)

    def stop_battle(self):
        self.sent.append(("stop_battle",))

    battle_stop = type("E", (), {"set": lambda self: None})()

    def join(self, timeout=None):
        pass


def settle():
    """Let the window lay itself out and fit its detail pane, which takes a few event passes."""
    for _ in range(20):
        QApplication.processEvents()


def shot(window, out, name):
    settle()
    path = out / name
    window.grab().save(str(path))
    print(path)


def on_screen(window, out, name):
    """The window where it is on its screen's available area, drawn dark: whether it ends above the screen's bottom."""
    settle()
    area = window.screen().availableGeometry()
    sheet = QPixmap(area.size())
    sheet.fill(QColor("#0b0a09"))
    painter = QPainter(sheet)
    painter.drawPixmap(window.frameGeometry().topLeft() - area.topLeft(), window.grab())
    painter.end()
    path = out / name
    sheet.save(str(path))
    print(path, f"screen {area.height()} px, window {window.y()}..{window.frameGeometry().bottom()}")


def with_popup(window, box, out, name):
    """The window with a search box's drop-down list painted where it shows: the list is a window of its own. The
    field's clear button fades in over a fraction of a second, so the shot waits for it."""
    QTest.qWait(300)
    settle()
    popup = box.list.popup()
    page, drop = window.grab(), popup.grab()
    at = popup.mapToGlobal(popup.rect().topLeft()) - window.mapToGlobal(window.rect().topLeft())
    sheet = QPixmap(max(page.width(), at.x() + drop.width()), max(page.height(), at.y() + drop.height()))
    sheet.fill(QColor("#0b0a09"))
    painter = QPainter(sheet)
    painter.drawPixmap(0, 0, page)
    painter.drawPixmap(at, drop)
    painter.end()
    path = out / name
    sheet.save(str(path))
    print(path, f"list of {popup.model().rowCount()} rows")


def menu_shot(window, button, out, name):
    """The window with button's menu open under it, painted where it shows: the menu is a window of its own."""
    menu = button.menu()
    menu.popup(button.mapToGlobal(button.rect().bottomLeft()))
    settle()
    page, drop = window.grab(), menu.grab()
    at = menu.mapToGlobal(menu.rect().topLeft()) - window.mapToGlobal(window.rect().topLeft())
    sheet = QPixmap(max(page.width(), at.x() + drop.width()), max(page.height(), at.y() + drop.height()))
    sheet.fill(QColor("#0b0a09"))
    painter = QPainter(sheet)
    painter.drawPixmap(0, 0, page)
    painter.drawPixmap(at, drop)
    painter.end()
    menu.hide()
    path = out / name
    sheet.save(str(path))
    print(path)


def overlay_shot(out, name, capture, keywords=()):
    """The overlay's labels painted over a capture of the game, as the player would see them."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QRegion
    from PySide6.QtWidgets import QWidget

    from lc_helper import overlay

    image = vision.imread(maalc_dir() / "tests/screens" / capture)
    reading = events.read_screen(image)
    o = overlay.Overlay(locate=lambda source: (0, 0, 1280, 720))
    o.resize(1280, 720)
    from lc_helper import recommend
    pick = recommend.best(reading.event, keywords, reading.closed)
    o.items = overlay.labels(reading, lambda option: pick is not None and option is pick[0])
    rgb = image[:, :, ::-1].copy()
    canvas = QImage(rgb.data, 1280, 720, 3 * 1280, QImage.Format_RGB888).copy()
    o.render(canvas, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    path = out / name
    canvas.save(str(path))
    print(path)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / ".local/evidence"
    out.mkdir(parents=True, exist_ok=True)
    ui.SETTINGS = out / "render-settings.json"
    ui.SETTINGS.unlink(missing_ok=True)
    QApplication(sys.argv)
    for name in ("msjh.ttc", "msjhbd.ttc"):  # offscreen Qt finds no system fonts: load the app's own face, or the
        QFontDatabase.addApplicationFont(str(FONTS / name))  # renders show a fallback with other metrics
    w = ui.Window(worker_factory=StandIn)
    w.show()
    shot(w, out, "window-main.png")
    found = [Target("MuMuPlayer12", "127.0.0.1:16384"), Target("MuMuPlayer12", "127.0.0.1:16416"),
             Target("Limbus PC", PC)]
    w.settings["address"] = PC
    w.on_targets(found)
    w.on_device("connected", "PC 版")
    w.gear.setChecked(True)
    shot(w, out, "window-settings-pc.png")
    w.gear.setChecked(False)
    for pinned, name in ((False, "unpinned"), (True, "pinned")):
        w.pin.setChecked(pinned)
        shot(w.header, out, f"window-header-{name}.png")
    sample = out / "render-battles.jsonl"
    sample.unlink(missing_ok=True)
    from lc_helper import fights
    from lc_helper.battle import Fight
    for i, (result, turns, seconds) in enumerate([("victory", 5, 128), ("victory", 7, 171), ("wipe", 4, 96),
                                                  ("victory", 6, 142)]):
        fights.record(Fight(result, turns, seconds), "MuMuPlayer12", sample, now=1_763_000_000 + 600 * i)
    log = ui.FightLog(w, sample)
    log.show()
    shot(log, out, "window-battle-log.png")
    log.close()
    dialog = ui.HotkeyDialog({"battle": "F8", "read": "F8"}, w)
    dialog.show()
    shot(dialog, out, "window-hotkeys-clash.png")
    dialog.edits["read"].setKeySequence("Ctrl+Shift+Q")
    shot(dialog, out, "window-hotkeys.png")
    dialog.close()
    w.settings["address"] = "127.0.0.1:16384"
    w.on_targets(found)
    w.on_device("connected", "MuMu 0")
    w.guard_box.setCurrentIndex(w.guard_box.findData("turns"))
    w.set_guard_mode(w.guard_box.currentIndex())
    w.on_battle(Status(Phase.GUARDING, Plan(Pick.DAMAGE, 2), 3))
    shot(w, out, "window-battle-running.png")
    w.on_battle(Status(Phase.PLAYING, Plan(Pick.WIN_RATE, FOREVER), 7))
    image = vision.imread(maalc_dir() / "tests/screens/EventChoices.png")
    w.set_keywords(["Charge", "Bleed"])
    w.on_event(events.read_screen(image))
    w.overlay.hide_labels()
    shot(w, out, "window-event-read.png")
    w.skip_box.setChecked(True)
    w.say_skip("自動跳過：點了沒反應，等畫面變化")
    shot(w, out, "window-skip.png")
    w.skip_box.setChecked(False)
    for key in ui.TEXT_SIZES:
        w.set_text_size(key)
        shot(w, out, f"window-text-{key}.png")
        w.gear.setChecked(True)
        shot(w, out, f"window-settings-{key}.png")
        w.gear.setChecked(False)
    w.set_keywords(["Charge", "Bleed", "Tremor", "Rupture"])  # four: the widest row, and no ＋ 體系
    for key in ui.TEXT_SIZES:
        w.set_text_size(key)
        shot(w.sections["event"], out, f"window-keywords-four-{key}.png")
    w.set_keywords(["Charge", "Bleed"])
    settle()  # the new chips show on an event pass; the ones they replace stay, hidden, until the event loop deletes
    from PySide6.QtWidgets import QAbstractButton
    add = next(b for b in w.findChildren(QAbstractButton) if b.objectName() == "chipAdd" and b.isVisible())
    menu_shot(w, add, out, "window-keyword-menu.png")
    w.show_event(events.by_id()[971097])  # too long for the pane at every text size: it stops short and scrolls
    area = w.screen().availableGeometry()
    for where, y in (("top", 0), ("low", area.height() // 4)):
        w.move(area.left(), area.top() + y)
        on_screen(w, out, f"window-long-event-{where}.png")
    w.move(area.topLeft())
    w.set_text_size("normal")
    w.event_search.field.setText("hand")
    w.event_search.search()
    with_popup(w, w.event_search, out, "window-search.png")
    w.event_search.list.popup().hide()
    w.event_search.field.clear()
    shot(w, out, "window-search-cleared.png")
    from lc_helper import gifts, ocr
    trials = vision.imread(maalc_dir() / "tests/screens/BossGiftTrials.png")
    w.sections["gift"].head.setChecked(True)
    w.on_gifts(gifts.read_gifts(trials, "choice", ocr.lines))
    shot(w, out, "window-gifts.png")
    for key in ui.TEXT_SIZES:  # each gift's keyword icon beside its name
        w.set_text_size(key)
        shot(w.sections["gift"], out, f"window-gifts-{key}.png")
    w.set_text_size("normal")
    w.gift_search.field.setText("地獄蝶")
    w.gift_search.search()
    with_popup(w, w.gift_search, out, "window-gift-search.png")
    w.gift_search.list.popup().hide()
    w.show_event(events.by_id()[901069])
    on_screen(w, out, "window-both-open.png")
    w.on_battle(Status(Phase.STOPPED, Plan(), 4, "連續 3 個回合按 START 都沒開始，自動戰鬥停止"))
    w.set_watch(True)
    for section in w.sections.values():
        section.head.setChecked(False)
    shot(w, out, "window-folded.png")
    overlay_shot(out, "overlay-event.png", "EventChoices.png", keywords=["Charge"])
    overlay_shot(out, "overlay-event-scrolled.png", "EventChoicesLitTop.png")
    print("commands sent:", w.worker.sent)


if __name__ == "__main__":
    main()
