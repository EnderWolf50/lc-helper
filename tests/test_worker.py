import threading
import time

from lc_helper.battle import Phase, Pick, Plan
from lc_helper.device import PC, Clock, Target
from lc_helper.worker import Callbacks, Worker
from fake_game import FakeBattle


class Still:
    """A device that always shows one screen and takes taps without effect."""

    can_hold = True

    def __init__(self, image):
        self.image = image

    def screenshot(self):
        return self.image

    def __getattr__(self, name):
        return lambda *a: None


def started(device, **callbacks):
    w = Worker(Callbacks(**callbacks), connect=lambda address, **_: (device, Target("fake", "127.0.0.1:1")),
               find=lambda: [])
    w.start()
    w.send("connect", None)
    return w


class Sized(Still):
    """The PC client on one screen: it records the sizes asked of its window and their putting back."""

    def __init__(self, image, refuses=None):
        super().__init__(image)
        self.sizes, self.refuses = [], refuses

    def resized(self, size):
        if self.refuses:
            raise RuntimeError(self.refuses)
        self.sizes.append(size)
        return lambda: self.sizes.append("back")


def on_pc(device, **callbacks):
    w = Worker(Callbacks(**callbacks), connect=lambda address, **_: (device, Target("Limbus PC", PC)), find=lambda: [])
    w.start()
    w.send("connect", PC)
    return w


def wait_for(predicate, timeout=20):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.05)


def test_a_battle_runs_until_stopped_and_reports_each_turn(screen):
    fake = FakeBattle(screen, Clock(), turns=2, play_s=1.0)
    statuses = []
    w = started(fake, battle=statuses.append)
    w.send("start_battle", Plan(Pick.DAMAGE), False)
    assert fake.stop.wait(20), "the fake battle reached VICTORY"
    w.stop_battle()
    wait_for(lambda: statuses and statuses[-1].phase is Phase.STOPPED)
    assert fake.starts() == ["damage", "damage"]
    assert statuses[-1].turns == 2
    w.send("quit")
    w.join(3)
    assert not w.is_alive()


def test_a_device_that_cannot_hold_plays_its_turns_without_holding(screen):
    """The PC client with a cursor or window input: a held touch would drag the user's mouse along."""
    fake = FakeBattle(screen, Clock(), turns=2, play_s=1.0)
    fake.can_hold = False
    w = started(fake)
    w.send("start_battle", Plan(), True)
    w.send("set_hold", True)
    assert fake.stop.wait(20), "the fake battle reached VICTORY"
    assert fake.starts() == ["win_rate", "win_rate"]
    assert "hold" not in fake.log


def test_a_new_pc_input_reconnects_the_pc_client_with_it(screen):
    calls, readings, states = [], [], []

    def connect(address, pc_input):
        calls.append((address, pc_input))
        return Still(screen("EventChoices.png")), Target("Limbus PC", address)

    w = Worker(Callbacks(event=readings.append, device=lambda state, text: states.append(state)), connect=connect,
               find=lambda: [])
    w.start()
    w.send("set_address", "pc")
    w.send("read_event")
    wait_for(lambda: len(readings) == 1)
    w.send("set_pc_input", "window")  # unchanged: the connection stays
    w.send("set_pc_input", "touch")
    w.send("read_event")
    wait_for(lambda: len(readings) == 2)
    assert calls == [("pc", "window"), ("pc", "touch")]
    assert "idle" in states


def ocr_watched(monkeypatch, game, **callbacks):
    """A worker on game whose OCR drops after 0.3 s idle; the drops are counted, not done.

    The page a read finds stays watched, its header read once a second, until it goes: give game a screen to go to,
    or this worker keeps dropping and loading the model on every look and counts drops into later tests' lists."""
    from lc_helper import worker as worker_module
    drops = []
    monkeypatch.setattr(worker_module.ocr, "release", lambda: drops.append(time.monotonic()))
    w = Worker(Callbacks(**callbacks), connect=lambda address, **_: (game, Target("fake", "x")),
               find=lambda: [], ocr_idle=0.3)
    w.start()
    return w, drops


def test_the_ocr_model_is_dropped_once_reads_stop(monkeypatch, screen):
    readings = []
    game = Slides([screen("EventChoices.png"), screen("MirrorMap.png")])
    w, drops = ocr_watched(monkeypatch, game, event=readings.append)
    w.send("read_event")
    wait_for(lambda: readings)
    time.sleep(1.0)
    assert len(drops) == 1


def test_auto_read_keeps_the_ocr_model_until_it_is_turned_off(monkeypatch, screen):
    readings, left = [], []
    game = Still(screen("EventChoices.png"))
    w, drops = ocr_watched(monkeypatch, game, event=readings.append, page_left=lambda: left.append(1))
    w.send("set_watch", True)
    wait_for(lambda: readings)
    time.sleep(1.0)
    game.image = screen("MirrorMap.png")  # the page goes first, so nothing is left to watch once auto read is off
    wait_for(lambda: left)
    assert drops == []
    w.send("set_watch", False)
    time.sleep(1.0)
    assert len(drops) == 1


class Slides(Still):
    """Shows each image in turn, one per screenshot, then stays on the last."""

    def __init__(self, images):
        super().__init__(images[0])
        self.images = list(images)

    def screenshot(self):
        return self.images.pop(0) if len(self.images) > 1 else self.images[0]


def test_auto_read_reads_again_when_the_list_scrolls_and_tells_when_the_page_goes(screen):
    readings, left = [], []
    images = [screen("EventChoicesLitTop.png"), screen("EventChoicesScrolledBack.png"), screen("MirrorMap.png")]
    started(Slides(images), event=readings.append, page_left=lambda: left.append(1)).send("set_watch", True)
    wait_for(lambda: left)
    assert [r.event["id"] for r in readings] == [901095, 901095]
    assert [len(r.lines) > 0 for r in readings] == [True, True] and readings[0].source == "127.0.0.1:1"
    assert len(left) == 1


def test_read_event_reads_the_page_on_screen(screen):
    readings = []
    w = started(Still(screen("EventChoices.png")), event=readings.append)
    w.send("read_event")
    wait_for(lambda: readings)
    assert readings[0].event["id"] == 901069


class Counted(Slides):
    """Slides that count the screenshots taken."""

    shots = 0

    def screenshot(self):
        self.shots += 1
        return super().screenshot()


def test_an_event_page_read_by_hand_is_watched_until_it_goes_and_then_left_alone(screen):
    """Auto read off: the page F9 read is looked at about once a second, and its leaving is told once."""
    readings, left = [], []
    game = Counted([screen("EventChoices.png"), screen("EventChoices.png"), screen("MirrorMap.png")])
    started(game, event=readings.append, page_left=lambda: left.append(game.shots)).send("read_event")
    wait_for(lambda: left)
    assert [r.event["id"] for r in readings] == [901069]
    assert left == [3], "told on the look that saw the map, not while the page was still there"
    time.sleep(1.5)
    assert left == [3] and game.shots == 3, "no more looks once it is told"


def test_a_read_that_found_no_event_is_not_watched(screen):
    readings, left = [], []
    game = Counted([screen("MirrorMap.png")])
    started(game, event=readings.append, page_left=lambda: left.append(1)).send("read_event")
    wait_for(lambda: readings)
    time.sleep(1.5)
    assert readings[0].event is None and left == [] and game.shots == 1


def test_auto_read_shows_a_page_once_not_on_every_look(screen):
    readings = []
    w = started(Still(screen("EventChoices.png")), event=readings.append)
    w.send("set_watch", True)
    wait_for(lambda: readings)
    time.sleep(2.5)  # two more looks at the same page
    assert len(readings) == 1


def test_auto_read_ignores_screens_that_are_no_event_page(screen):
    readings, looked = [], threading.Event()

    class Map(Still):
        def screenshot(self):
            looked.set()
            return self.image

    started(Map(screen("MirrorMap.png")), event=readings.append).send("set_watch", True)
    assert looked.wait(5)
    time.sleep(1.5)
    assert readings == []


def test_a_battle_queued_before_closing_never_starts(screen):
    """The hotkey started a battle while the emulator was still connecting, then the window closed."""
    fake = FakeBattle(screen, Clock(), turns=2, play_s=0.3)
    statuses = []

    def slow_connect(address, **_):
        time.sleep(0.5)
        return fake, Target("fake", "x")

    w = Worker(Callbacks(battle=statuses.append), connect=slow_connect, find=lambda: [])
    w.start()
    w.send("connect", None)
    w.send("start_battle", Plan(), False)
    time.sleep(0.1)
    w.shutdown()
    w.join(3)
    assert not w.is_alive()
    assert fake.taps == [] and statuses == []


def test_opening_the_window_does_not_reach_the_emulator_until_first_use(screen):
    calls = []
    readings = []

    def connect(address, **_):
        calls.append(address)
        return Still(screen("EventChoices.png")), Target("fake", address)

    w = Worker(Callbacks(event=readings.append), connect=connect, find=lambda: [])
    w.start()
    for command in (("scan",), ("set_address", "127.0.0.1:16416")):
        w.send(*command)
    time.sleep(0.5)
    assert calls == []
    w.send("read_event")
    wait_for(lambda: readings)
    assert calls == ["127.0.0.1:16416"]


def test_a_failed_read_is_reported_and_the_worker_goes_on(screen):
    errors, statuses = [], []

    class Closed(Still):
        def screenshot(self):
            raise RuntimeError("模擬器截圖失敗，可能已關閉或斷線")

    w = started(Closed(None), error=errors.append, battle=statuses.append)
    w.send("read_event")
    wait_for(lambda: errors)
    w.send("start_battle", Plan(), False)
    wait_for(lambda: statuses)
    assert w.is_alive() and "截圖失敗" in errors[0]


def test_the_pc_client_takes_the_chosen_size_for_a_battle_and_gets_its_own_back(screen):
    pc, statuses = Sized(screen("EventChoices.png")), []
    w = on_pc(pc, battle=statuses.append)
    w.send("set_pc_size", "720")
    w.send("start_battle", Plan(), False)
    wait_for(lambda: statuses)
    assert pc.sizes == [(1280, 720)]
    assert "1280×720" in statuses[0].note
    w.stop_battle()
    wait_for(lambda: statuses[-1].phase is Phase.STOPPED)
    assert pc.sizes == [(1280, 720), "back"]
    w.shutdown()
    w.join(3)


def test_closing_lc_helper_mid_battle_gives_the_pc_client_its_size_back(screen):
    pc, statuses = Sized(screen("EventChoices.png")), []
    w = on_pc(pc, battle=statuses.append)
    w.send("set_pc_size", "1080")
    w.send("start_battle", Plan(), False)
    wait_for(lambda: statuses)
    w.shutdown()
    w.join(3)
    assert pc.sizes == [(1920, 1080), "back"]


def test_a_size_the_game_cannot_take_is_told_and_the_battle_runs_anyway(screen):
    pc, statuses = Sized(screen("EventChoices.png"), refuses="遊戲是全螢幕"), []
    w = on_pc(pc, battle=statuses.append)
    w.send("set_pc_size", "720")
    w.send("start_battle", Plan(), False)
    wait_for(lambda: statuses)
    assert statuses[0].phase is Phase.WAITING and "全螢幕" in statuses[0].note
    w.shutdown()
    w.join(3)


def test_an_emulator_keeps_its_size_and_an_unknown_size_is_the_default(screen):
    emulator, pc = Sized(screen("EventChoices.png")), Sized(screen("EventChoices.png"))
    w, v = started(emulator), on_pc(pc)
    w.send("set_pc_size", "720")
    v.send("set_pc_size", "8k")
    for worker in (w, v):
        worker.send("start_battle", Plan(), False)
    time.sleep(0.5)
    for worker in (w, v):
        worker.shutdown()
        worker.join(3)
    assert emulator.sizes == [] and pc.sizes == [(2560, 1440), "back"]
