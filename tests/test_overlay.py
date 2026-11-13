import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lc_helper import events, overlay  # noqa: E402
from lc_helper.overlay import Win  # noqa: E402

# The first line of each option visible on maalc's Choices captures (y of its OCR box); scrolled-out options have none.
VISIBLE = {
    "EventChoices.png": {"Shake hands.": 217, "Push the hand away.": 327},
    "EventChoicesLitBottom.png": {"West, to where the broken hand points.": 300, "Turn back.": 431},
    "EventChoicesLitTop.png": {"North, to where the burst-open arm points.": 206,
                               "East, to where the warning hand points.": 329,
                               "West, to where the broken hand points.": 477},
    "EventChoicesScrolledBack.png": {"North, to where the burst-open arm points.": 178,
                                     "East, to where the warning hand points.": 299,
                                     "West, to where the broken hand points.": 449},
    "EventChoicesUsed.png": {"What if you do feel like what you did was wrong?": 197,
                             "You're running away from something.": 354},
}


@pytest.mark.parametrize("name", VISIBLE)
def test_each_visible_option_is_found_at_its_first_line(screen, name):
    reading = events.read_screen(screen(name))
    rows = events.option_rows(reading.event, reading.lines)
    assert {option["text"]: box[1] for option, box in rows} == VISIBLE[name]


def test_a_label_says_what_the_option_does(screen):
    reading = events.read_screen(screen("EventChoices.png"))
    found = {label.box[1]: label.text for label in overlay.labels(reading)}
    assert "護腕" in found[327] and "判定" in found[327]
    assert found[217]


def test_the_picture_is_the_16_by_9_middle_of_the_render_area():
    assert overlay.fit_16_9((0, 0, 2000, 1000)) == (111, 0, 1778, 1000)
    assert overlay.fit_16_9((10, 20, 1600, 1000)) == (10, 70, 1600, 900)
    assert overlay.fit_16_9((732, 381, 2490, 1401)) == (732, 381, 2490, 1401)  # MuMu on this machine, 2026-11-13


def test_mumu_instances_follow_their_adb_port():
    assert overlay.mumu_index("127.0.0.1:16384") == 0
    assert overlay.mumu_index("127.0.0.1:16416") == 1
    for other in ("127.0.0.1:5555", "127.0.0.1:16400", "emulator-5554", "pc", None):
        assert overlay.mumu_index(other) is None


def device_window(pid, index, display):
    top = Win(pid * 10, pid, "Qt5156QWindowIcon", "Android Device", True)
    shell = Win(pid * 10 + 1, pid, "Static", f"ShellWindowReveiceMessageWndMuMuPlayerGlobal-12.0-{index}", False)
    return [top, shell], {top.hwnd: [Win(display, pid, "nemuwin", "nemudisplay", True)]}


def test_the_display_of_the_instance_read_from_is_picked():
    tops0, kids0 = device_window(1, 0, display=100)
    tops1, kids1 = device_window(2, 1, display=200)
    tops, kids = tops0 + tops1, kids0 | kids1
    children = lambda hwnd: kids.get(hwnd, [])  # noqa: E731
    assert overlay.pick_mumu_display(tops, children, 1) == 200
    assert overlay.pick_mumu_display(tops, children, 0) == 100
    assert overlay.pick_mumu_display(tops, children, None) is None  # two displays and no way to tell
    assert overlay.pick_mumu_display(tops0, children, None) == 100  # the only one


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def test_the_overlay_shows_only_while_the_game_is_on_screen(qt):
    where = {"rect": (0, 0, 1280, 720)}
    o = overlay.Overlay(locate=lambda source: where["rect"])
    o.show_labels([overlay.Label((730, 327, 191, 22), "判定成功獲得「護腕」")], "127.0.0.1:16384")
    assert o.isVisible()
    where["rect"] = None  # minimised, or closed
    o.place()
    assert not o.isVisible()
    o.show_labels([overlay.Label((730, 327, 191, 22), "x")], "127.0.0.1:16384")
    assert not o.isVisible()
    where["rect"] = (0, 0, 1280, 720)
    o.show_labels([], "127.0.0.1:16384")  # a page with no option found
    assert not o.isVisible()
    o.close()
