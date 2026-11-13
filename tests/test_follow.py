from lc_helper.follow import HWND_NOTOPMOST, HWND_TOPMOST, place_above


class Z:
    """A z-order, top first, kept as SetWindowPos documents it: topmost windows above the rest; HWND_TOPMOST puts a
    window on top of all, HWND_NOTOPMOST a topmost one on top of the rest (no effect on any other), a window handle
    right after (under) that window."""

    def __init__(self, order, topmost=()):
        self.order, self.top, self.calls = list(order), set(topmost), []

    def above(self, hwnd):
        i = self.order.index(hwnd)
        return self.order[i - 1] if i else None

    def topmost(self, hwnd):
        return hwnd in self.top

    def put(self, hwnd, after):
        self.calls.append(after)
        if after == HWND_NOTOPMOST:
            if hwnd in self.top:
                self.top.discard(hwnd)
                self.order.remove(hwnd)
                self.order.insert(sum(h in self.top for h in self.order), hwnd)
            return
        self.order.remove(hwnd)
        if after == HWND_TOPMOST:
            self.top.add(hwnd)
            self.order.insert(0, hwnd)
        else:
            self.order.insert(self.order.index(after) + 1, hwnd)


def test_the_game_in_front_gets_the_window_on_top_of_it_and_not_on_top_of_everything():
    z = Z(["taskbar", "game", "browser", "helper"], topmost={"taskbar"})
    place_above("helper", "game", z=z)
    assert z.order == ["taskbar", "helper", "game", "browser"] and not z.topmost("helper")


def test_the_game_behind_another_window_gets_the_window_right_above_it_still_behind_that_window():
    z = Z(["browser", "game", "helper"])
    place_above("helper", "game", z=z)
    assert z.order == ["browser", "helper", "game"] and z.calls == ["browser"]


def test_a_window_already_above_the_game_or_above_lc_helpers_hints_is_left_alone():
    z = Z(["browser", "helper", "hints", "game"])
    place_above("helper", "game", ours=("hints",), z=z)
    place_above("hints", "game", z=z)
    assert z.calls == []


def test_the_hints_go_between_the_game_and_the_window_above_it():
    z = Z(["helper", "game", "hints"])
    place_above("hints", "game", z=z)
    assert z.order == ["helper", "hints", "game"]
    place_above("helper", "game", ours=("hints",), z=z)
    assert z.order == ["helper", "hints", "game"], "stays: the hints between are lc-helper's"
