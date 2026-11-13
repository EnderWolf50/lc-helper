"""Render the floating window offscreen in the states a user sees, as PNGs: the evidence for UI changes.

Usage: uv run --group sync python tools/render_window.py [out folder]   (default .local/evidence)

No emulator: a stand-in worker takes the commands; the battle states are fed in as the real worker would, and the
event pane shows what the real reader makes of maalc's EventChoices.png capture (OCR included).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
os.environ.setdefault("QT_QPA_FONTDIR", str(FONTS))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events, vision  # noqa: E402
from lc_helper.battle import FOREVER, Phase, Pick, Plan, Status  # noqa: E402
from lc_helper.device import PC, Target  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402


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


def menus(window, out, name):
    """The ⋯ menu with its submenus beside it, side by side in one PNG."""
    menu = window.more.menu()
    pics = []
    for m in (menu, *(a.menu() for a in menu.actions() if a.menu())):
        # A hidden menu keeps the size it had before the text size changed. A popup takes its size hint; adjustSize
        # would cap it at 2/3 of the 800 px offscreen screen.
        m.resize(m.sizeHint())
        pics.append(m.grab())
    sheet = QPixmap(sum(p.width() + 8 for p in pics), max(p.height() for p in pics))
    sheet.fill(QColor("#0b0a09"))
    painter = QPainter(sheet)
    x = 0
    for pic in pics:
        painter.drawPixmap(x, 0, pic)
        x += pic.width() + 8
    painter.end()
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
    w.on_device("connected", "MuMuPlayer12 127.0.0.1:16384")
    shot(w, out, "window-idle.png")
    found = [Target("MuMuPlayer12", "127.0.0.1:16384"), Target("Limbus PC", PC)]
    w.settings["address"] = PC
    w.on_targets(found)
    w.on_device("connected", "Limbus PC（合成觸控）")
    shot(w, out, "window-pc.png")
    for pinned, name in ((False, "unpinned"), (True, "pinned")):
        w.pin.setChecked(pinned)
        shot(w.header, out, f"window-header-{name}.png")
    menus(w, out, "window-menu.png")
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
    w.on_device("connected", "MuMuPlayer12 127.0.0.1:16384")
    w.on_battle(Status(Phase.GUARDING, Plan(Pick.DAMAGE, 2), 3))
    shot(w, out, "window-guarding.png")
    w.on_battle(Status(Phase.PLAYING, Plan(Pick.WIN_RATE, FOREVER), 7))
    image = vision.imread(maalc_dir() / "tests/screens/EventChoices.png")
    w.settings["keywords"] = ["Charge"]
    w.keyword_box.setCurrentIndex(w.keyword_box.findData("Charge"))
    w.on_event(events.read_screen(image))
    w.overlay.hide_labels()
    shot(w, out, "window-event-read.png")
    w.skip_box.setChecked(True)
    w.say_skip("自動跳過：到選項頁了，請你選")
    shot(w, out, "window-skip.png")
    w.skip_box.setChecked(False)
    for key in ui.TEXT_SIZES:
        w.set_text_size(key)
        shot(w, out, f"window-text-{key}.png")
        menus(w, out, f"window-menu-{key}.png")
    w.show_event(events.by_id()[971097])  # too long for the pane at every text size: it stops short and scrolls
    area = w.screen().availableGeometry()
    for where, y in (("top", 0), ("low", area.height() // 4)):
        w.move(area.left(), area.top() + y)
        on_screen(w, out, f"window-long-event-{where}.png")
    w.move(area.topLeft())
    w.set_text_size("normal")
    w.query.setText("螺旋")
    w.run_search()
    shot(w, out, "window-search.png")
    from lc_helper import gifts, ocr
    trials = vision.imread(maalc_dir() / "tests/screens/BossGiftTrials.png")
    w.query.setText("")
    w.on_gifts(gifts.read_gifts(trials, "choice", ocr.lines))
    shot(w, out, "window-gifts.png")
    w.query.setText("地獄蝶")
    w.run_search()
    shot(w, out, "window-gift-search.png")
    w.query.setText("")
    w.on_battle(Status(Phase.STOPPED, Plan(), 4, "連續 3 個回合按 START 都沒開始，自動戰鬥停止"))
    w.toggle_compact()
    shot(w, out, "window-compact.png")
    overlay_shot(out, "overlay-event.png", "EventChoices.png", keywords=["Charge"])
    overlay_shot(out, "overlay-event-scrolled.png", "EventChoicesLitTop.png")
    print("commands sent:", w.worker.sent)


if __name__ == "__main__":
    main()
