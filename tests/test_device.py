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
