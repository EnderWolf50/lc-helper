"""Render the floating window offscreen in the states a user sees, as PNGs: the evidence for UI changes.

Usage: uv run --group sync python tools/render_window.py [out folder]   (default .local/evidence)

No emulator: a stand-in worker takes the commands; the battle states are fed in as the real worker would, and the
event pane shows what the real reader makes of maalc's EventChoices.png capture (OCR included).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

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


def shot(window, out, name):
    for _ in range(3):
        QApplication.processEvents()
    path = out / name
    window.grab().save(str(path))
    print(path)


def menus(window, out, name):
    """The ⋯ menu with its PC submenu beside it, side by side in one PNG."""
    menu = next(m for m in window.findChildren(QMenu) if m.title() == "")
    sub = next(m for m in window.findChildren(QMenu) if m.title() == "PC 版點擊方式")
    pics = [m.grab() for m in (menu, sub)]
    sheet = QPixmap(sum(p.width() for p in pics) + 8, max(p.height() for p in pics))
    sheet.fill(QColor("#0b0a09"))
    painter = QPainter(sheet)
    painter.drawPixmap(0, 0, pics[0])
    painter.drawPixmap(pics[0].width() + 8, 0, pics[1])
    painter.end()
    path = out / name
    sheet.save(str(path))
    print(path)


def overlay_shot(out, name, capture):
    """The overlay's labels painted over a capture of the game, as the player would see them."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QRegion
    from PySide6.QtWidgets import QWidget

    from lc_helper import overlay

    image = vision.imread(maalc_dir() / "tests/screens" / capture)
    reading = events.read_screen(image)
    o = overlay.Overlay(locate=lambda source: (0, 0, 1280, 720))
    o.resize(1280, 720)
    o.items = overlay.labels(reading)
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
    app = QApplication(sys.argv)
    app.setStyleSheet(ui.STYLE)
    w = ui.Window(worker_factory=StandIn)
    w.show()
    w.on_device("connected", "MuMuPlayer12 127.0.0.1:16384")
    shot(w, out, "window-idle.png")
    found = [Target("MuMuPlayer12", "127.0.0.1:16384"), Target("Limbus PC", PC)]
    w.settings["address"] = PC
    w.on_targets(found)
    w.on_device("connected", "Limbus PC（合成觸控）")
    shot(w, out, "window-pc.png")
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
    w.on_event(events.read_screen(image))
    shot(w, out, "window-event-read.png")
    w.query.setText("螺旋")
    w.run_search()
    shot(w, out, "window-search.png")
    w.on_battle(Status(Phase.STOPPED, Plan(), 4, "連續 3 個回合按 START 都沒開始，自動戰鬥停止"))
    w.toggle_compact()
    shot(w, out, "window-compact.png")
    overlay_shot(out, "overlay-event.png", "EventChoices.png")
    overlay_shot(out, "overlay-event-scrolled.png", "EventChoicesLitTop.png")
    print("commands sent:", w.worker.sent)


if __name__ == "__main__":
    main()
