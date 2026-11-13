"""Start the real window (Windows platform, real hotkeys) without touching any emulator, and report how long until
the window shows; then, pinned and unpinned, the native window's extended styles, whether a WM_HOTKEY for each hotkey
reaches its action, and a capture of the window as the desktop shows it (.local/evidence/launch-pin-*.png).

Usage: uv run python tools/launch_check.py

The worker gets a device scan and a connect that never reach adb: a second MaaFramework controller on an emulator a
bot is driving can disturb it. The hotkeys are fired by posting WM_HOTKEY to the window's thread, not by pressing
keys, so no key reaches whatever window has the focus. The window runs on its own settings in .local/launch-check/,
with hotkeys a running lc-helper does not hold, and the pin toggles save there, not in your settings.
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
from lc_helper.paths import LOCAL  # noqa: E402
from lc_helper.worker import Worker  # noqa: E402

HOTKEYS = {"battle": "Ctrl+Alt+Shift+F11", "read": "Ctrl+Alt+Shift+F12"}
GWL_EXSTYLE = -20
EX_STYLES = {"WS_EX_TOPMOST": 0x8, "WS_EX_TOOLWINDOW": 0x80}


def no_emulator(address, **_):
    raise RuntimeError("launch_check: no emulator on purpose")


class Watched(Worker):
    def __init__(self, callbacks):
        super().__init__(callbacks, connect=no_emulator, find=lambda: [Target("MuMuPlayer12", "127.0.0.1:16384")])
        self.seen = []

    def send(self, name, *args):
        self.seen.append(name)
        super().send(name, *args)


def styles(window):
    ex = ctypes.windll.user32.GetWindowLongW(int(window.winId()), GWL_EXSTYLE)
    return ", ".join(f"{name} {'yes' if ex & bit else 'no'}" for name, bit in EX_STYLES.items())


def main():
    ui.SETTINGS = LOCAL / "launch-check/settings.json"
    ui.save_settings(ui.DEFAULTS | {"hotkeys": HOTKEYS, "pin": True})
    evidence = LOCAL / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    fired = []
    names = {hid: name for name, hid in ui.HOTKEY_IDS.items()}
    real_show, real_close = ui.Window.show, ui.Window.closeEvent
    started = []

    def show(self):
        real_show(self)
        if not started:
            started.append(time.perf_counter() - T0)
            print(f"window shown {started[0]:.2f} s after start", flush=True)
            count_hotkeys(self)
            QTimer.singleShot(300, lambda: check(self, ["on", "off", "on again"]))

    def count_hotkeys(window):
        window.hotkeys.actions = {hid: (lambda hid=hid, act=act: (fired.append(hid), act()))
                                  for hid, act in window.hotkeys.actions.items()}

    def check(window, states):
        fired.clear()
        thread = ctypes.windll.kernel32.GetCurrentThreadId()
        for hid in ui.HOTKEY_IDS.values():
            ctypes.windll.user32.PostThreadMessageW(thread, ui.WM_HOTKEY, hid, 0)
        QTimer.singleShot(500, lambda: report(window, states))

    def report(window, states):
        g = window.frameGeometry()
        window.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(
            str(evidence / f"launch-pin-{states[0].replace(' ', '-')}.png"))
        print(f"pin {states[0]}: {styles(window)}; hotkeys fired: {', '.join(names[h] for h in fired) or 'none'}",
              flush=True)
        if len(states) > 1:
            window.pin.click()
            QTimer.singleShot(300, lambda: check(window, states[1:]))
        else:
            print(f"commands sent: {window.worker.seen}")
            print(f"hotkeys RegisterHotKey refused: {window.hotkeys_taken or 'none'}")
            print(f"status: {window.status.text()!r}; device dot: {window.dot.property('state')}", flush=True)
            window.close()

    def close_event(self, e):
        real_close(self, e)
        print(f"closed: settings saved with pin {ui.load_settings()['pin']}", flush=True)

    ui.Window.show, ui.Window.closeEvent = show, close_event
    ui.main(worker_factory=Watched)


if __name__ == "__main__":
    main()
