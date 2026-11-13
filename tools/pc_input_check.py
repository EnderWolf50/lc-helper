"""Check a PC input method's mechanics on a probe window of our own: where taps land, how long a hold stays down,
whether a drag arrives, and whether the user's cursor moved. No game and no emulator is touched.

Usage: uv run python tools/pc_input_check.py [touch|window|cursor|seize]   (default touch; see device.PC_INPUTS)

This proves what MaaFramework does on this machine, not that Limbus Company accepts it: the game reads input its own
way (maalc docs/research/win32-postmessage.md). cursor and seize move the real cursor while they run.
"""

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QEvent, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from lc_helper import device  # noqa: E402
from lc_helper.battle import HOLD_SPOT  # noqa: E402

CLIENT = (960, 540)  # 16:9, so MaaFramework's 1280x720 coordinates land at 3/4 scale
SCALE = CLIENT[0] / 1280


class Probe(QWidget):
    """Logs every touch and mouse press, move and release it gets, in client pixels."""

    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("lc-helper input probe")
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setFixedSize(*CLIENT)
        self.setStyleSheet("background: #203040;")
        self.log = []
        self.t0 = time.perf_counter()

    def note(self, kind, pos):
        self.log.append((round(time.perf_counter() - self.t0, 3), kind, round(pos.x()), round(pos.y())))

    def event(self, e):
        kinds = {QEvent.TouchBegin: "touch down", QEvent.TouchUpdate: "touch move", QEvent.TouchEnd: "touch up"}
        if e.type() in kinds:
            if e.points():
                self.note(kinds[e.type()], e.points()[0].position())
            e.accept()
            return True
        mice = {QEvent.MouseButtonPress: "mouse down", QEvent.MouseMove: "mouse move",
                QEvent.MouseButtonRelease: "mouse up"}
        if e.type() in mice:
            self.note(mice[e.type()], e.position())
        return super().event(e)


def cursor():
    p = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def drive(probe, method, report):
    from maa.controller import Win32Controller
    from maa.define import MaaWin32InputMethodEnum, MaaWin32ScreencapMethodEnum

    device.maa_options()
    name, _, enum_name, can_hold = device.PC_INPUTS[method]
    ctl = Win32Controller(int(probe.winId()), MaaWin32ScreencapMethodEnum.Background,
                          getattr(MaaWin32InputMethodEnum, enum_name), MaaWin32InputMethodEnum.PostMessage)
    ctl.post_connection().wait()
    dev = device.MaaDevice(ctl, can_hold, "探測視窗")
    before = cursor()
    shot = dev.screenshot()
    report.append(f"screenshot {shot.shape[1]}x{shot.shape[0]}; size problem: {device.screen_size_problem(shot)}")
    marks = {}
    marks["tap"] = time.perf_counter() - probe.t0
    dev.tap(640, 360)
    time.sleep(0.5)
    marks["hold"] = time.perf_counter() - probe.t0
    dev.touch_down(*HOLD_SPOT)
    time.sleep(3)
    dev.touch_up()
    time.sleep(0.5)
    marks["drag"] = time.perf_counter() - probe.t0
    dev.touch_down(100, 600)
    for k in range(1, 11):
        dev.touch_move(100 + 100 * k, 600)
        time.sleep(0.03)
    dev.touch_up()
    time.sleep(0.5)
    after = cursor()
    report.append(f"method {method} ({name}, {enum_name}); cursor before {before}, after {after}")
    report.append(f"marks {', '.join(f'{k} at {v:.3f} s' for k, v in marks.items())}")
    report.append(f"expected: tap at {round(640 * SCALE)},{round(360 * SCALE)}; hold at ~1,1 for 3 s; "
                  f"drag {round(100 * SCALE)}..{round(1100 * SCALE)} along y {round(600 * SCALE)}")


def main():
    method = sys.argv[1] if len(sys.argv) > 1 else device.PC_INPUT
    app = QApplication(sys.argv)
    probe = Probe()
    probe.show()
    report, done = [], threading.Event()

    def run():
        try:
            drive(probe, method, report)
        except Exception as e:
            report.append(f"failed: {e!r}")
        done.set()

    QTimer.singleShot(500, lambda: threading.Thread(target=run, daemon=True).start())
    poll = QTimer(interval=100, timeout=lambda: done.is_set() and app.quit())
    poll.start()
    app.exec()
    for line in report:
        print(line)
    moves = [e for e in probe.log if e[1].endswith("move")]
    for e in probe.log:
        if not e[1].endswith("move"):
            print(e)
    if moves:
        print(f"{len(moves)} moves, first {moves[0]}, last {moves[-1]}")


if __name__ == "__main__":
    main()
