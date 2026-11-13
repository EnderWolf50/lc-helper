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
from . import events, ocr, vision
from .battle import AutoBattle, Phase, Plan, Status, Stopped

WATCH_EVERY = 1.0  # s between looks for a new event page while auto read is on


@dataclass
class Callbacks:
    device: Callable[[str, str], None] = lambda state, text: None  # ("connected" | "connecting" | "error", text)
    targets: Callable[[list], None] = lambda targets: None
    battle: Callable[[Status], None] = lambda status: None
    event: Callable[[events.Reading], None] = lambda reading: None
    error: Callable[[str], None] = lambda text: None


class Worker(threading.Thread):
    def __init__(self, callbacks: Callbacks, connect=None, find=None):
        super().__init__(daemon=True, name="lc-helper-worker")
        self.cb = callbacks
        self.connect_fn = connect or devices.connect
        self.find_fn = find or devices.targets
        self.commands: queue.Queue = queue.Queue()
        self.device = None
        self.address: str | None = None  # the emulator to connect to on first use; None: the first one found
        self.battle: AutoBattle | None = None
        self.battle_stop = threading.Event()
        self.watch = False
        self.last_watch = 0.0
        self.last_page = None  # thumbnail of the story box of the last page auto read showed
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
            busy = self.battle is not None or (self.watch and self.device is not None)
            try:
                name, args = self.commands.get(timeout=0.05 if busy else None)
            except queue.Empty:
                name = None
            if not self.alive:
                break
            if name:
                try:
                    getattr(self, "do_" + name)(*args)
                except Exception as e:  # a screenshot or OCR failed: report it, keep the thread for the next command
                    self.cb.error(str(e))
                continue
            try:
                if self.battle is not None:
                    self.battle_tick()
                elif self.watch and self.device is not None:
                    self.watch_tick()
            except Exception as e:  # the emulator went away mid-turn, or a screenshot failed
                self.end_battle(f"出錯：{e}")
                self.cb.error(str(e))

    def do_quit(self):
        self.end_battle()
        self.alive = False

    def do_warm(self):
        try:
            ocr.warm()
        except Exception as e:
            self.cb.error(f"OCR 載入失敗：{e}")

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
            self.device, target = self.connect_fn(address)
            self.cb.device("connected", f"{target.name} {target.address}")
        except Exception as e:
            self.cb.device("error", str(e))

    def do_start_battle(self, plan: Plan, hold: bool):
        if not self.ready():
            self.cb.battle(Status(Phase.STOPPED, plan, 0, "還沒連上模擬器"))
            return
        self.battle_stop.clear()
        self.battle = AutoBattle(self.device, plan, self.battle_stop, self.cb.battle, hold=hold)
        self.battle.emit(Phase.WAITING)

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
            self.battle.hold = hold

    def do_set_watch(self, on):
        self.watch, self.last_page = on, None
        if on:
            self.ready()

    def do_read_event(self):
        if not self.ready():
            return
        self.cb.event(events.read_screen(self.device.screenshot()))

    def battle_tick(self):
        try:
            self.battle.tick()
        except Stopped:
            self.end_battle()
            return
        if self.watch and self.battle is not None and self.battle.last and self.battle.last.phase is Phase.WAITING:
            try:
                self.watch_tick()
            except Exception as e:  # auto read failing must not end the battle
                self.cb.error(f"自動讀取事件失敗：{e}")

    def end_battle(self, note=""):
        if self.battle is None:
            return
        battle, self.battle = self.battle, None
        battle.emit(Phase.STOPPED, note or battle.stop_note)

    def watch_tick(self):
        """Read the event page once a new one shows: a Choices page whose story box differs from the last read."""
        now = time.monotonic()
        if now - self.last_watch < WATCH_EVERY:
            return
        self.last_watch = now
        image = self.device.screenshot()
        if not events.on_choices_page(image):
            return
        story = vision.thumb(vision.crop(image, vision.EVENT_STORY))
        if self.last_page is not None and vision.same_screen(self.last_page, story):
            return
        reading = events.read_screen(image)
        self.last_page = story
        self.cb.event(reading)
