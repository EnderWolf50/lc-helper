"""The game's screen and touch: the Device the battle and event readers drive, and its MaaFramework adapter.

maa is imported inside connect(): loading MaaFramework's DLLs takes ~2 s, and the window shows before that.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent


class Device(Protocol):
    """A 1280x720 game screen: screenshots in BGR, input in the same pixels."""

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
    """An emulator MaaFramework found: what the device picker lists."""

    name: str
    address: str


class MaaDevice:
    def __init__(self, controller):
        self.ctl = controller

    def screenshot(self):
        job = self.ctl.post_screencap().wait()
        image = job.get() if job.succeeded else None
        if image is None or image.size == 0:
            raise RuntimeError("模擬器截圖失敗，可能已關閉或斷線")
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

    Toolkit.init_option(str(ROOT / ".local/maa"))
    return Toolkit


def targets() -> list[Target]:
    return [Target(d.name, d.address) for d in _maa().find_adb_devices()]


def connect(address: str | None = None) -> tuple[MaaDevice, Target]:
    """The emulator at address (the first one found when None), connected; RuntimeError when none answers."""
    from maa.controller import AdbController

    devices = _maa().find_adb_devices()
    found = [d for d in devices if address in (None, d.address)]
    if not found:
        raise RuntimeError(f"找不到模擬器 {address or ''}（找到：{', '.join(d.address for d in devices) or '無'}）")
    d = found[0]
    ctl = AdbController(d.adb_path, d.address, d.screencap_methods, d.input_methods, d.config)
    ctl.post_connection().wait()
    if not ctl.connected:
        raise RuntimeError(f"連不上 {d.address}")
    return MaaDevice(ctl), Target(d.name, d.address)
