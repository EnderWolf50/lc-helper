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

    @property
    def label(self):
        """What the window calls it: PC 版, MuMu 0 for MuMu's first instance, else the name MaaFramework gives."""
        if self.address == PC:
            return "PC 版"
        port = self.address.rsplit(":", 1)[-1]
        instance, step = divmod(int(port) - MUMU_PORT, MUMU_STEP) if port.isdigit() else (-1, 1)
        return f"MuMu {instance}" if self.name.startswith("MuMu") and instance >= 0 and not step else self.name


PC = "pc"
MUMU_PORT, MUMU_STEP = 16384, 32  # MuMu 12's instance n listens on adb port 16384 + 32 n
PC_NAME = "Limbus PC"
# AALC, LixAssistantLimbusCompany and sairaisaika/MaaLimbus all find the client by this class and title.
PC_CLASS, PC_TITLE = "UnityWndClass", "LimbusCompany"

# How taps reach the PC client: (name, what it costs the user, MaaWin32InputMethodEnum name, can_hold).
# maalc docs/research/win32-postmessage.md: Limbus reads the real cursor, so plain PostMessage clicks land under it.
# - window: moves the game window so the target sits under the cursor (AALC's WindowMoveInput), posts the click to
#   the game's window, and moves it back. Tested 2026-11-14 on the LLC client behind Discord, not in front: 胜率
#   toggled twice, the cursor never moved.
# - touch: synthetic touch points (InjectSyntheticPointerInput) at the screen point, so a window over the game
#   there takes them; lc-helper then refuses the tap (Covered).
# - cursor: moves the cursor to the target for each message, then back (sairaisaika/MaaLimbus's default).
# - seize: real mouse input; the game takes the mouse.
PC_INPUTS = {
    "touch": ("合成觸控", "不動滑鼠，遊戲要露出來", "AnchoredTouch", True),
    "window": ("移動視窗", "不動滑鼠，遊戲可在背景；點擊時視窗瞬間移到游標下再移回", "PostMessageWithWindowPos", False),
    "cursor": ("借用游標", "每次點擊游標會閃過去", "SendMessageWithCursorPos", False),
    "seize": ("前景操作", "戰鬥時佔用滑鼠", "Seize", True),
}
PC_INPUT = "window"
# The game's client size while lc-helper's auto battle runs, put back when it stops: (name, (w, h) or None to leave).
# All 16:9: every reading is measured on a 16:9 screen (screen_size_problem).
PC_SIZES = {
    "keep": ("不調整", None),
    "720": ("1280×720", (1280, 720)),
    "900": ("1600×900", (1600, 900)),
    "1080": ("1920×1080", (1920, 1080)),
    "1440": ("2560×1440", (2560, 1440)),
}
PC_SIZE = "1440"
WINDOW_BACK_AFTER = 0.05  # s from the lift to moving the window back; AALC waits 0.02 (input.py, WindowMoveInput)


class Covered(RuntimeError):
    """A tap's point on the PC client is under another window: a synthetic touch lands on whatever is on top there."""


class MaaDevice:
    def __init__(self, controller, can_hold=True, what="模擬器", cover=None, moves_window=False, hwnd=None):
        self.ctl = controller
        self.hwnd = hwnd  # the PC client's window; None on an emulator
        self.can_hold = can_hold
        self.what = what
        self.cover = cover  # (x, y) -> the program whose window covers that game point, or None when the game shows
        self.moves_window = moves_window  # MaaFramework leaves the window moved after a touch until inactive

    def screenshot(self):
        job = self.ctl.post_screencap().wait()
        image = job.get() if job.succeeded else None
        if image is None or image.size == 0:
            raise RuntimeError(f"{self.what}截圖失敗，可能已關閉、斷線或縮到最小")
        return image

    def uncovered(self, x, y):
        """Raise Covered rather than touch a point another window hides: the touch would go to that window."""
        if self.cover and (program := self.cover(x, y)):
            raise Covered(f"遊戲視窗在點擊位置被「{program}」蓋住，沒有點下去，請讓遊戲露出來")

    def window_back(self):
        if self.moves_window:
            time.sleep(WINDOW_BACK_AFTER)
            self.ctl.post_inactive().wait()

    def tap(self, x, y):
        self.uncovered(x, y)
        self.ctl.post_click(x, y).wait()
        self.window_back()

    def touch_down(self, x, y):
        self.uncovered(x, y)
        self.ctl.post_touch_down(x, y).wait()

    def touch_move(self, x, y):
        self.ctl.post_touch_move(x, y).wait()

    def touch_up(self):
        self.ctl.post_touch_up().wait()
        self.window_back()

    def resized(self, size):
        """The PC client's game area made size (w, h): a function that puts the window back as it was. RuntimeError,
        with the reason, when there is no window to size."""
        if self.hwnd is None:
            raise RuntimeError("模擬器不調整解析度")
        return resize_client(self.hwnd, size)


def _maa():
    from maa.toolkit import Toolkit

    Toolkit.init_option(str(LOCAL / "maa"))
    return Toolkit


def pc_window(windows):
    """The PC client's window among MaaFramework's desktop windows, or None."""
    return next((w for w in windows if w.class_name == PC_CLASS and w.window_name == PC_TITLE), None)


def covering(hwnd):
    """(x, y) in the game's 1280x720 -> the name of the program whose window is on top at that screen point, or None
    when it is the game's own."""
    import ctypes
    from ctypes import wintypes
    from pathlib import PureWindowsPath

    user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
    user32.WindowFromPoint.restype = user32.GetAncestor.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    def program(top):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(top, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
        ok = handle and kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if handle:
            kernel32.CloseHandle(handle)
        return PureWindowsPath(buf.value).stem if ok else "另一個視窗"

    def cover(x, y):
        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        point = wintypes.POINT(origin.x + round(x * rect.right / 1280), origin.y + round(y * rect.bottom / 720))
        top = user32.GetAncestor(user32.WindowFromPoint(point), 2)  # GA_ROOT
        return None if top == hwnd else program(top)
    return cover


def resize_client(hwnd, size):
    """Make hwnd's client area size (w, h), its top-left corner kept (AALC's adjust_win_size): a function that puts
    the window back where and how big it was. RuntimeError when the game fills its screen: full screen or maximized,
    a size it would not keep."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    flags = 0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    def physical(call):  # the game's own pixels, whatever DPI awareness Qt gave this process
        old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        try:
            return call()
        finally:
            user32.SetThreadDpiAwarenessContext(old)

    def rects():
        window, client = wintypes.RECT(), wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(window))
        user32.GetClientRect(hwnd, ctypes.byref(client))
        info = MonitorInfo(ctypes.sizeof(MonitorInfo))
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # MONITOR_DEFAULTTONEAREST
        return window, client, info.rcMonitor

    window, client, monitor = physical(rects)
    fills = all(getattr(window, k) == getattr(monitor, k) for k in ("left", "top", "right", "bottom"))
    if user32.IsZoomed(hwnd) or fills:
        raise RuntimeError("遊戲是全螢幕或最大化，沒有調整解析度，請先切成視窗模式（Alt+Enter）")
    old = (window.left, window.top, window.right - window.left, window.bottom - window.top)
    w, h = size
    frame_w, frame_h = old[2] - client.right, old[3] - client.bottom
    physical(lambda: user32.SetWindowPos(hwnd, None, 0, 0, w + frame_w, h + frame_h, flags | 0x0002))  # SWP_NOMOVE

    def put_back():
        physical(lambda: user32.SetWindowPos(hwnd, None, *old, flags))
    return put_back


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
    # Touch and seized input land on the screen point: a window over the game there takes them (seen 2026-11-14:
    # the user's Discord window over 胜率 swallowed 16 taps). Window and cursor inputs post to the game's window.
    cover = covering(window.hwnd) if method in ("AnchoredTouch", "Seize") else None
    device = MaaDevice(ctl, can_hold, "PC 版遊戲", cover, method.endswith("WithWindowPos"), window.hwnd)
    if problem := screen_size_problem(device.screenshot()):
        raise RuntimeError(problem)
    return device, Target(f"{PC_NAME}（{name}）", PC)
