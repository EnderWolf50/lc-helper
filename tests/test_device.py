import pytest

from types import SimpleNamespace

import numpy as np

from lc_helper import device


def window(class_name, title):
    return SimpleNamespace(hwnd=1, class_name=class_name, window_name=title)


def test_the_pc_client_is_the_unity_window_titled_limbuscompany():
    other_unity_game = window("UnityWndClass", "SomeOtherGame")
    a_browser_tab = window("Chrome_WidgetWin_1", "LimbusCompany - YouTube")
    game = window("UnityWndClass", "LimbusCompany")
    assert device.pc_window([other_unity_game, a_browser_tab, game]) is game
    assert device.pc_window([other_unity_game, a_browser_tab]) is None


def test_only_a_16_by_9_client_is_readable():
    assert device.screen_size_problem(np.zeros((720, 1280, 3), np.uint8)) is None
    problem = device.screen_size_problem(np.zeros((720, 1152, 3), np.uint8))  # a 1600x1000 client, scaled
    assert problem and "1152×720" in problem


def shows(image):
    """A MaaFramework controller whose screenshot is image."""
    job = SimpleNamespace(succeeded=True, get=lambda: image)
    return SimpleNamespace(post_screencap=lambda: SimpleNamespace(wait=lambda: job))


def test_a_pc_screenshot_off_16_by_9_is_refused_and_says_why_but_the_capture_still_works():
    """2026-11-15: the game reopened at 2904x1677 (1247x720 scaled). Connecting must not care; reading must refuse."""
    off = np.zeros((720, 1247, 3), np.uint8)
    pc = device.MaaDevice(shows(off), what="PC 版遊戲", hwnd=1)
    with pytest.raises(RuntimeError, match="1247×720"):
        pc.screenshot()
    assert pc.capture() is off, "connecting only checks the capture works"
    assert device.MaaDevice(shows(np.zeros((720, 1280, 3), np.uint8)), hwnd=1).screenshot().shape == (720, 1280, 3)


def test_every_pc_input_names_a_maafw_input_method():
    from maa.define import MaaWin32InputMethodEnum

    for _, _, method, _ in device.PC_INPUTS.values():
        assert getattr(MaaWin32InputMethodEnum, method)
    assert device.PC_INPUT in device.PC_INPUTS


def test_a_device_is_called_by_a_short_name():
    assert device.Target("MuMuPlayer12", "127.0.0.1:16384").label == "MuMu 0"
    assert device.Target("MuMuPlayer12", "127.0.0.1:16416").label == "MuMu 1", "MuMu's instance n: 16384 + 32 n"
    assert device.Target("Limbus PC（合成觸控）", device.PC).label == "PC 版"
    assert device.Target("LDPlayer", "emulator-5554").label == "LDPlayer"
    assert device.Target("MuMuPlayer12", "127.0.0.1:5555").label == "MuMuPlayer12", "not one of MuMu's own ports"
    assert device.Target("BlueStacks", "127.0.0.1:16384").label == "BlueStacks"


class Clicks:
    """A MaaFramework controller stand-in that records what was posted."""

    def __init__(self):
        self.posted = []

    def __getattr__(self, name):
        def post(*args):
            self.posted.append((name, args))
            return SimpleNamespace(wait=lambda: None)
        return post


def test_a_covered_point_of_the_pc_client_is_never_touched():
    """2026-11-14: the user's browser over 胜率 took 16 synthetic touches meant for the game."""
    ctl = Clicks()
    covered = device.MaaDevice(ctl, cover=lambda x, y: "brave" if x > 900 else None)
    covered.tap(312, 557)
    with pytest.raises(device.Covered, match="brave"):
        covered.tap(966, 545)
    with pytest.raises(device.Covered):
        covered.touch_down(966, 545)
    assert ctl.posted == [("post_click", (312, 557))]


def test_without_a_cover_check_every_tap_goes_through():
    ctl = Clicks()
    device.MaaDevice(ctl).tap(966, 545)
    assert ctl.posted == [("post_click", (966, 545))]


def test_a_window_moving_input_puts_the_game_window_back_after_every_touch():
    """MaaFramework 5.14.3 keeps the game window where WithWindowPos moved it until the controller goes inactive
    (MessageInput::touch_up)."""
    ctl = Clicks()
    moved = device.MaaDevice(ctl, can_hold=False, moves_window=True)
    moved.tap(966, 545)
    moved.touch_down(1, 1)
    moved.touch_up()
    assert [name for name, _ in ctl.posted] == ["post_click", "post_inactive", "post_touch_down", "post_touch_up",
                                                 "post_inactive"]
