"""The game's screen and touch: the Device the battle and event readers drive, and its MaaFramework adapters for the
emulator (ADB) and the Windows PC client (Win32).

maa is imported inside connect(): loading MaaFramework's DLLs takes ~2 s, and the window shows before that.
"""

import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .paths import LOCAL



class Device(Protocol):
    """A 1280x720 game screen: screenshots in BGR, input in the same pixels.

    can_hold: whether a touch may stay down for seconds without taking the user's mouse along.
    """

    can_hold: bool

    def screenshot(self) -> np.ndarray: ...
    def tap(self, x: int, y: int) -> None: ...
    def touch_down(self, x: int, y: int) -> None: ...
    def touch_move(self, x: int, y: int) -> None: ...
    def touch_up(self) -> None: ...


class Clock:
    """Wall time for the engine; tests pass one that only moves when slept."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, s: float) -> None:
        if s > 0:
            time.sleep(s)


@dataclass(frozen=True)
class Target:
    """An emulator or the PC client MaaFramework found: what the device picker lists."""

    name: str
    address: str  # an adb address, or PC for the PC client (its window handle changes each launch)


PC = "pc"
PC_NAME = "Limbus PC"
# AALC, LixAssistantLimbusCompany and sairaisaika/MaaLimbus all find the client by this class and title.
PC_CLASS, PC_TITLE = "UnityWndClass", "LimbusCompany"

# How taps reach the PC client: (name, what it costs the user, MaaWin32InputMethodEnum name, can_hold).
# None is tested on Limbus yet.
# - touch: synthetic touch points (InjectSyntheticPointerInput); never moves the cursor or the focus. When another
#   window covers the touched point, the game window is raised (nearly transparent) until the touch lifts.
# - window: moves the game window so the target sits under the cursor (AALC's WindowMoveInput); the cursor stays.
#   MaaFramework 5.14.3 leaves the window moved after the touch lifts, and a long touch drifts if the mouse moves.
# - cursor: moves the cursor to the target for each message, then back (sairaisaika/MaaLimbus's default).
# - seize: real mouse input; the game takes the mouse.
# maalc docs/research/win32-postmessage.md: Limbus reads the real cursor, so plain PostMessage clicks land under it.
PC_INPUTS = {
    "touch": ("合成觸控", "不動滑鼠", "AnchoredTouch", True),
    "window": ("移動視窗", "不動滑鼠，遊戲視窗會跳到游標下", "PostMessageWithWindowPos", False),
    "cursor": ("借用游標", "每次點擊游標會閃過去", "SendMessageWithCursorPos", False),
    "seize": ("前景操作", "戰鬥時佔用滑鼠", "Seize", True),
}
PC_INPUT = "touch"


class MaaDevice:
    def __init__(self, controller, can_hold=True, what="模擬器"):
        self.ctl = controller
        self.can_hold = can_hold
        self.what = what

    def screenshot(self):
        job = self.ctl.post_screencap().wait()
        image = job.get() if job.succeeded else None
        if image is None or image.size == 0:
            raise RuntimeError(f"{self.what}截圖失敗，可能已關閉、斷線或縮到最小")
        return image

    def tap(self, x, y):
        self.ctl.post_click(x, y).wait()

    def touch_down(self, x, y):
        self.ctl.post_touch_down(x, y).wait()

    def touch_move(self, x, y):
        self.ctl.post_touch_move(x, y).wait()

    def touch_up(self):
        self.ctl.post_touch_up().wait()


def _maa():
    from maa.toolkit import Toolkit

    Toolkit.init_option(str(LOCAL / "maa"))
    return Toolkit


def pc_window(windows):
    """The PC client's window among MaaFramework's desktop windows, or None."""
    return next((w for w in windows if w.class_name == PC_CLASS and w.window_name == PC_TITLE), None)


def targets() -> list[Target]:
    toolkit = _maa()
    found = [Target(d.name, d.address) for d in toolkit.find_adb_devices()]
    if pc_window(toolkit.find_desktop_windows()):
        found.append(Target(PC_NAME, PC))
    return found


def screen_size_problem(image) -> str | None:
    """Why a screenshot cannot be read, or None: every reading is measured on 1280x720, and MaaFramework scales
    screenshots to a 720 px short side, so only a 16:9 client comes out right."""
    h, w = image.shape[:2]
    if (w, h) == (1280, 720):
        return None
    return f"遊戲畫面比例不是 16:9（縮放後 {w}×{h}），請把 PC 版視窗設成 1280×720 或 1920×1080"


def connect(address: str | None = None, pc_input: str = PC_INPUT) -> tuple[MaaDevice, Target]:
    """The device at address, connected: an emulator, or the PC client for PC. When None, the first emulator found,
    else the PC client. RuntimeError when none answers."""
    from maa.controller import AdbController

    toolkit = _maa()
    if address == PC:
        return _connect_pc(toolkit, pc_input)
    devices = toolkit.find_adb_devices()
    found = [d for d in devices if address in (None, d.address)]
    if not found and address is None and pc_window(toolkit.find_desktop_windows()):
        return _connect_pc(toolkit, pc_input)
    if not found:
        raise RuntimeError(f"找不到模擬器 {address or ''}（找到：{', '.join(d.address for d in devices) or '無'}）")
    d = found[0]
    ctl = AdbController(d.adb_path, d.address, d.screencap_methods, d.input_methods, d.config)
    ctl.post_connection().wait()
    if not ctl.connected:
        raise RuntimeError(f"連不上 {d.address}")
    return MaaDevice(ctl), Target(d.name, d.address)


def _connect_pc(toolkit, pc_input):
    from maa.controller import Win32Controller
    from maa.define import MaaWin32InputMethodEnum, MaaWin32ScreencapMethodEnum

    window = pc_window(toolkit.find_desktop_windows())
    if window is None:
        raise RuntimeError("找不到 PC 版遊戲視窗（LimbusCompany），請先開遊戲")
    name, _, method, can_hold = PC_INPUTS[pc_input]
    # Background capture (FramePool, else PrintWindow) works while other windows cover the game; MaaFramework keeps
    # the fastest that works. Keys are not sent; PostMessage keeps them off the user's focus if they ever are.
    ctl = Win32Controller(window.hwnd, MaaWin32ScreencapMethodEnum.Background,
                          getattr(MaaWin32InputMethodEnum, method), MaaWin32InputMethodEnum.PostMessage)
    ctl.post_connection().wait()
    if not ctl.connected:
        raise RuntimeError("連不上 PC 版遊戲視窗")
    device = MaaDevice(ctl, can_hold, "PC 版遊戲")
    if problem := screen_size_problem(device.screenshot()):
        raise RuntimeError(problem)
    return device, Target(f"{PC_NAME}（{name}）", PC)
