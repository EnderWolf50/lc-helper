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

from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper import events, vision  # noqa: E402
from lc_helper.battle import FOREVER, Phase, Pick, Plan, Status  # noqa: E402
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
    print("commands sent:", w.worker.sent)


if __name__ == "__main__":
    main()
