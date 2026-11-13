"""The one thread that owns the emulator: it runs the auto battle and reads event pages, one command at a time.

The window sends commands (send) and gets results through callbacks it passes in; the battle's stop is an Event the
window sets directly, so a stop interrupts a turn in progress instead of queueing behind it.
"""

import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from . import device as devices
from . import event_skip, events, gifts, ocr, vision
from .battle import AutoBattle, Fight, Phase, Plan, Status, Stopped

WATCH_EVERY = 1.0  # s between looks for a new event page while auto read is on
SKIP_EVERY = 0.3  # s between looks while skipping an event's story (maalc taps every 0.15 s, reads every 0.45 s)
# s without an event read before the OCR model is dropped (auto read off). tools/ocr_memory.py, 2026-11-13: a read of
# the story box takes private memory from ~40 to ~975 MB, a release brings it back to 326-353 MB, and the next read
# loads again in 1.2-1.3 s.
OCR_IDLE = 180.0


@dataclass
class Callbacks:
    device: Callable[[str, str], None] = lambda state, text: None  # ("connected" | "connecting" | "error", text)
    targets: Callable[[list], None] = lambda targets: None
    battle: Callable[[Status], None] = lambda status: None
    event: Callable[[events.Reading], None] = lambda reading: None
    page_left: Callable[[], None] = lambda: None  # auto read saw the Choices page it had read go away
    fight: Callable[[Fight, str], None] = lambda fight, device: None  # a battle ended (and on which device)
    skip: Callable[[str], None] = lambda what: None  # what the story skipper did or waits for, when it changes
    gifts: Callable[["gifts.GiftReading"], None] = lambda reading: None  # the gifts a gift screen shows
    error: Callable[[str], None] = lambda text: None


class Worker(threading.Thread):
    def __init__(self, callbacks: Callbacks, connect=None, find=None, ocr_idle=OCR_IDLE):
        super().__init__(daemon=True, name="lc-helper-worker")
        self.cb = callbacks
        self.ocr_idle = ocr_idle
        self.ocr_used: float | None = None  # when OCR last ran; None once released (or never loaded)
        self.connect_fn = connect or devices.connect
        self.find_fn = find or devices.targets
        self.commands: queue.Queue = queue.Queue()
        self.device = None
        self.address: str | None = None  # the emulator to connect to on first use; None: the first one found
        self.pc_input = devices.PC_INPUT  # how taps reach the PC client (devices.PC_INPUTS)
        self.pc_size = devices.PC_SIZE  # the PC client's size while a battle runs (devices.PC_SIZES)
        self.size_back = None  # puts the PC client's window back as it was before the battle resized it
        self.target: devices.Target | None = None  # what the device is connected to
        self.battle: AutoBattle | None = None
        self.battle_stop = threading.Event()
        self.stop_after_victory = False
        self.watch = False
        self.skip = False
        self.skipper = event_skip.Skipper(self.read_text)
        self.last_skip, self.skip_said = 0.0, None
        self.last_watch = 0.0
        self.last_page = None  # thumbnails (story box, option list) of the last Choices page auto read showed
        self.last_gifts = None  # (page, gift ids) of the last gift screen auto read showed
        self.left_choices = False  # a Choices page was shown and its leaving is not told yet
        self.alive = True

    def send(self, name, *args):
        self.commands.put((name, args))

    def stop_battle(self):
        self.battle_stop.set()
        self.send("stop_battle")

    def shutdown(self):
        """Stop now: a running turn lifts its finger and ends, and no queued command runs after this."""
        self.alive = False
        self.battle_stop.set()
        self.send("quit")

    def run(self):
        while self.alive:
            busy = self.battle is not None or ((self.watch or self.skip) and self.device is not None)
            try:
                name, args = self.commands.get(timeout=0.05 if busy else self.until_ocr_idle())
            except queue.Empty:
                name = None
            if not self.alive:
                break
            self.release_idle_ocr()
            if name:
                try:
                    getattr(self, "do_" + name)(*args)
                except Exception as e:  # a screenshot or OCR failed: report it, keep the thread for the next command
                    self.cb.error(str(e))
                continue
            try:
                if self.battle is not None:
                    self.battle_tick()
                elif self.device is not None:
                    self.page_tick()
            except Exception as e:  # the emulator went away mid-turn, or a screenshot failed
                self.end_battle(f"出錯：{e}")
                self.cb.error(str(e))
        self.size_restored()  # shutdown() left the loop between turns, before any end_battle

    def do_quit(self):
        self.end_battle()
        self.alive = False

    def do_warm(self):
        try:
            ocr.warm()
            self.ocr_used = time.monotonic()
        except Exception as e:
            self.cb.error(f"OCR 載入失敗：{e}")

    def until_ocr_idle(self):
        """s until the OCR model is dropped, or None when nothing is due: it is not loaded, or auto read needs it."""
        if self.ocr_used is None or self.watch:
            return None
        return max(0.0, self.ocr_used + self.ocr_idle - time.monotonic())

    def release_idle_ocr(self):
        if self.until_ocr_idle() == 0.0:
            ocr.release()
            self.ocr_used = None

    def do_scan(self):
        try:
            self.cb.targets(self.find_fn())
        except Exception as e:
            self.cb.error(f"找模擬器失敗：{e}")

    def do_set_address(self, address):
        """Remember the emulator without touching it: opening the window must not reach a device a bot may drive."""
        self.address = address

    def ready(self):
        """The device, connected now if it was not yet: every command that needs the emulator starts here."""
        if self.device is None:
            self.do_connect(self.address)
        return self.device is not None

    def do_connect(self, address):
        self.end_battle()
        self.device, self.address = None, address
        self.cb.device("connecting", address or "自動")
        try:
            self.device, self.target = self.connect_fn(address, pc_input=self.pc_input)
            self.cb.device("connected", self.target.label)
        except Exception as e:
            self.cb.device("error", str(e))

    def do_set_pc_input(self, method):
        """A new way to tap the PC client: a PC connection is dropped (ending its battle) and made again on next use."""
        method = method if method in devices.PC_INPUTS else devices.PC_INPUT  # a hand-edited settings.json
        changed = method != self.pc_input
        self.pc_input = method
        if changed and self.device is not None and self.target.address == devices.PC:
            self.end_battle("換了 PC 版點擊方式，請重新開始")
            self.device = None
            self.cb.device("idle", "換了點擊方式：下次開始戰鬥或讀取事件時重新連線")

    def do_start_battle(self, plan: Plan, hold: bool):
        if not self.ready():
            self.cb.battle(Status(Phase.STOPPED, plan, 0, "還沒連上模擬器或 PC 版"))
            return
        self.battle_stop.clear()
        self.battle = AutoBattle(self.device, plan, self.battle_stop, self.cb.battle, hold=self.holds(hold),
                                 on_fight=self.fought, stop_after_victory=self.stop_after_victory)
        self.battle.emit(Phase.WAITING, self.resize_pc())

    def do_set_pc_size(self, key):
        """The PC client's size for the next battle; a running one keeps its size until it stops."""
        self.pc_size = key if key in devices.PC_SIZES else devices.PC_SIZE  # a hand-edited settings.json

    def resize_pc(self):
        """The PC client resized for the battle when asked: what to tell the user about it."""
        name, size = devices.PC_SIZES[self.pc_size]
        if size is None or self.target is None or self.target.address != devices.PC:
            return ""
        try:
            self.size_back = self.device.resized(size)
        except Exception as e:
            return f"沒有調整解析度：{e}"
        return f"遊戲畫面調成 {name}，停下後還原"

    def size_restored(self):
        back, self.size_back = self.size_back, None
        if back is not None:
            try:
                back()
            except Exception as e:  # the game closed mid-battle
                self.cb.error(f"沒能還原遊戲視窗大小：{e}")

    def fought(self, fight):
        self.cb.fight(fight, self.target.name if self.target else "")

    def do_set_stop_after_victory(self, on):
        self.stop_after_victory = on
        if self.battle is not None:
            self.battle.stop_after_victory = on

    def holds(self, asked):
        """Whether turns are held: when asked, and the device can hold without taking the user's mouse along."""
        return asked and self.device.can_hold

    def do_stop_battle(self):
        self.end_battle()

    def do_plan(self, **changes):
        if self.battle is not None:
            self.battle.plan = replace(self.battle.plan, **changes)
            self.battle.emit(self.battle.last.phase if self.battle.last else Phase.WAITING)

    def do_set_pick(self, pick):
        self.do_plan(pick=pick)

    def do_set_guard(self, guard):
        self.do_plan(guard=guard)

    def do_set_hold(self, hold):
        if self.battle is not None:
            self.battle.hold = self.holds(hold)

    def do_set_watch(self, on):
        """Auto read on loads the OCR model now, so the first event page shows without the ~2 s load; off starts the
        idle clock that drops it."""
        self.watch, self.last_page = on, None
        if on:
            self.ready()
            if not ocr.loaded():
                self.do_warm()
        elif self.ocr_used is not None:
            self.ocr_used = time.monotonic()

    def do_read_event(self):
        """F9: the gifts on a gift screen, else the event page."""
        if not self.ready():
            return
        image = self.device.screenshot()
        page = gifts.gift_page(image, self.read_text)
        if page:
            self.cb.gifts(self.read_gift_screen(image, page))
        else:
            self.cb.event(self.read(image))

    def read_gift_screen(self, image, page):
        reading = gifts.read_gifts(image, page, ocr.lines)
        self.ocr_used = time.monotonic()
        return replace(reading, source=self.target.address if self.target else None)

    def read(self, image):
        reading = replace(events.read_screen(image), source=self.target.address if self.target else None)
        self.ocr_used = time.monotonic()
        return reading

    def battle_tick(self):
        try:
            self.battle.tick()
        except Stopped:
            self.end_battle()
            return
        if self.battle is not None and self.battle.last and self.battle.last.phase is Phase.WAITING:
            try:
                self.page_tick()
            except Exception as e:  # auto read or skip failing must not end the battle
                self.cb.error(f"事件處理失敗：{e}")

    def end_battle(self, note=""):
        if self.battle is None:
            return
        battle, self.battle = self.battle, None
        self.size_restored()
        battle.emit(Phase.STOPPED, note or battle.stop_note)

    def page_tick(self):
        """Between battle turns, or with no battle: skip an event's story, and read its Choices page."""
        if self.skip:
            self.skip_tick()
        if self.watch:
            self.watch_tick()

    def do_set_skip(self, on):
        self.skip, self.skipper, self.skip_said = on, event_skip.Skipper(self.read_text), None
        if on:
            self.ready()

    def read_text(self, image, roi, only_rec=False):
        self.ocr_used = time.monotonic()
        return [text for text, _ in ocr.lines(image, roi, only_rec=only_rec)]

    def skip_tick(self):
        """One look while skipping a story: tap what the skipper says, and tell the window when that changes."""
        now = time.monotonic()
        if now - self.last_skip < SKIP_EVERY:
            return
        self.last_skip = now
        what, point = self.skipper.step(self.device.screenshot(), now)
        if point is not None:
            self.device.tap(*point)
        said = {"press": "按下一步", "card": "打開判定卡", "text": "推進文字"}.get(what, what)
        if said != self.skip_said:
            self.skip_said = said
            self.cb.skip(said)

    def watch_tick(self):
        """Read the event page once a new one shows or its option list moves (a scroll, a lit row): a Choices page
        whose story box or option list differs from the last read; leaving it is told once. Off it, read a gift
        screen whose gifts differ from the last shown."""
        now = time.monotonic()
        if now - self.last_watch < WATCH_EVERY:
            return
        self.last_watch = now
        image = self.device.screenshot()
        if not events.on_choices_page(image):
            self.last_page = None
            if self.left_choices:
                self.left_choices = False
                self.cb.page_left()
            if page := gifts.gift_page(image, self.read_text):
                reading = self.read_gift_screen(image, page)
                shown = (page, tuple(g["id"] for g, _ in reading.gifts))
                if reading.gifts and shown != self.last_gifts:
                    self.last_gifts = shown
                    self.cb.gifts(reading)
            else:
                self.last_gifts = None
            return
        self.left_choices = True
        page = [vision.thumb(vision.crop(image, roi)) for roi in (vision.EVENT_STORY, vision.CHOICE_ROWS)]
        if self.last_page is not None and all(vision.same_screen(a, b) for a, b in zip(self.last_page, page)):
            return
        reading = self.read(image)
        self.last_page = page
        self.cb.event(reading)
