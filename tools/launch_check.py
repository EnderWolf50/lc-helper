"""Start the real window (Windows platform, real hotkeys) without touching any emulator, and report how long until
the window shows, and whether a WM_HOTKEY for each hotkey reaches its action.

Usage: uv run python tools/launch_check.py

The worker gets a device scan and a connect that never reach adb: a second MaaFramework controller on an emulator a
bot is driving can disturb it. The hotkeys are fired by posting WM_HOTKEY to the window's thread, not by pressing
keys, so no key reaches whatever window has the focus.
"""

import ctypes
import sys
import time
from pathlib import Path

T0 = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QTimer  # noqa: E402

from lc_helper import app as ui  # noqa: E402
from lc_helper.device import Target  # noqa: E402
from lc_helper.worker import Worker  # noqa: E402


def no_emulator(address):
    raise RuntimeError("launch_check: no emulator on purpose")


class Watched(Worker):
    def __init__(self, callbacks):
        super().__init__(callbacks, connect=no_emulator, find=lambda: [Target("MuMuPlayer12", "127.0.0.1:16384")])
        self.seen = []

    def send(self, name, *args):
        self.seen.append(name)
        super().send(name, *args)


def main():
    real_show = ui.Window.show

    def show(self):
        real_show(self)
        shown_at = time.perf_counter() - T0
        QTimer.singleShot(300, lambda: probe(self, shown_at))

    def probe(window, shown_at):
        thread = ctypes.windll.kernel32.GetCurrentThreadId()
        for hid in (1, 2):
            ctypes.windll.user32.PostThreadMessageW(thread, ui.WM_HOTKEY, hid, 0)
        QTimer.singleShot(1500, lambda: report(window, shown_at))

    def report(window, shown_at):
        print(f"window shown {shown_at:.2f} s after start")
        print(f"commands sent: {window.worker.seen}")
        print(f"hotkeys RegisterHotKey refused: {window.hotkeys_taken or 'none'}")
        print(f"status: {window.status.text()!r}; device dot: {window.dot.property('state')}", flush=True)
        window.close()

    ui.Window.show = show
    ui.main(worker_factory=Watched)


if __name__ == "__main__":
    main()
