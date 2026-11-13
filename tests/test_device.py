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
