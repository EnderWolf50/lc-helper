"""Auto battle: each turn, guard while guard turns are left, else Win Rate or Damage, then START.

A port of maalc's PlayTurn, HoldTurn and their helpers (agent/actions.py, spec 03 section 8), minus the Mirror
Dungeon run around them. The engine owns no thread: run() loops on the caller's thread until stop is set.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal

from . import vision
from .device import Clock, Covered, Device


class Pick(StrEnum):
    WIN_RATE = "win_rate"
    DAMAGE = "damage"


FOREVER = "forever"


@dataclass(frozen=True)
class Plan:
    """How the next turns are played: guard turns left (a count or FOREVER), then pick."""

    pick: Pick = Pick.WIN_RATE
    guard: int | Literal["forever"] = 0

    @property
    def guarding(self) -> bool:
        return self.guard == FOREVER or self.guard > 0

    def guarded_once(self) -> "Plan":
        return self if self.guard == FOREVER or self.guard == 0 else replace(self, guard=self.guard - 1)


class Phase(StrEnum):
    WAITING = "等待戰鬥回合"
    MENU = "戰鬥選單開著，等它關上"
    POPUP = "有彈窗，等它關上"
    PICKING = "選技能"
    GUARDING = "防禦中"
    PLAYING = "回合進行中"
    STOPPED = "已停止"


@dataclass(frozen=True)
class Status:
    phase: Phase
    plan: Plan
    turns: int
    note: str = ""


@dataclass(frozen=True)
class Fight:
    """One battle the engine played to its end: "victory" (the VICTORY banner) or "wipe" (every sinner died)."""

    result: Literal["victory", "wipe"]
    turns: int
    seconds: float


class Stopped(Exception):
    pass


class Gone(Exception):
    """The turn screen went away mid-turn (a menu, a popup, the next screen): its taps stop (maalc page_guard)."""


IDLE_EVERY = 0.3  # s between looks while no turn waits (maalc MirrorHub's rate)
STILL_GAP = 0.2  # s between the two screenshots that tell a resting turn HUD from a moving one
START_WAIT, START_LEAST, PLAQUE_WAIT = 1.5, 0.3, 1.5  # maalc #145: a turn starts 0.45-0.7 s after START
MAX_FAILED = 3  # turns in a row that START did not start: the screen is not what the engine thinks, so it stops
# maalc #150: a finger held on the screen while a turn plays speeds up its E.G.O animations. The top-left corner
# touches nothing on a battle screen, and a lift there touches nothing on the screens that follow a turn.
HOLD_SPOT, HOLD_EVERY, HOLD_LIMIT = (1, 1), 0.3, 6.0
GUARD_TAP_WAIT = 0.1  # maalc #119: portrait taps 150 ms apart lost none of 168
# maalc #145: the guard chain drag, slower on each try; the game links a slot only if it draws a frame while the
# finger is on it.
GUARD_DRAGS = ({"settle": 0.05, "dwell": 0.03, "hold": 0.05, "pause": 0.01},
               {"settle": 0.05, "dwell": 0.1, "hold": 0.1, "pause": 0.02},
               {"settle": 0.05, "dwell": 0.2, "hold": 0.1, "pause": 0.02})


class AutoBattle:
    def __init__(self, device: Device, plan: Plan, stop: threading.Event,
                 on_status: Callable[[Status], None] = lambda s: None, clock: Clock | None = None, hold: bool = True,
                 on_fight: Callable[[Fight], None] = lambda f: None, stop_after_victory: bool = False):
        self.device, self.plan, self.stop, self.on_status = device, plan, stop, on_status
        self.clock = clock or Clock()
        self.hold = hold
        self.on_fight, self.stop_after_victory = on_fight, stop_after_victory
        self.fight_turns, self.fight_from = 0, 0.0  # this battle's turns and when it started
        self.turns = self.failed = 0
        self.last: Status | None = None
        self.stop_note = ""

    def run(self) -> None:
        try:
            while True:
                self.tick()
        except Stopped:
            pass
        finally:
            self.emit(Phase.STOPPED, self.stop_note)

    def emit(self, phase, note=""):
        status = Status(phase, self.plan, self.turns, note)
        if status != self.last:
            self.last = status
            self.on_status(status)

    def sleep(self, s):
        if self.stop.is_set():
            raise Stopped
        self.clock.sleep(s)
        if self.stop.is_set():
            raise Stopped

    def shot(self):
        if self.stop.is_set():
            raise Stopped
        return self.device.screenshot()

    def until(self, done, timeout, least=0.0, every=0.2):
        """Screenshots every `every` s until done(image) holds: that image, or None after timeout s."""
        self.sleep(least)
        end = self.clock.now() + timeout
        while True:
            image = self.shot()
            if done(image):
                return image
            if self.clock.now() >= end:
                return None
            self.sleep(every)

    def tap(self, x, y, wait=0.0):
        self.device.tap(x, y)
        self.sleep(wait)

    def tick(self):
        image = self.shot()
        if vision.battle_menu(image):
            self.emit(Phase.MENU)
            self.sleep(IDLE_EVERY)
        elif vision.popup(image):
            self.emit(Phase.POPUP)
            self.sleep(IDLE_EVERY)
        elif box := vision.battle_turn(image):
            self.play_turn(image, box)
        elif vision.turn_playing(image):
            self.emit(Phase.PLAYING)
            self.hold_turn() if self.hold else self.sleep(IDLE_EVERY)
        else:
            self.emit(Phase.WAITING)
            if self.fight_turns and vision.wiped(image):
                self.end_fight("wipe")
            elif self.fight_turns and vision.victory(image):
                self.end_fight("victory")
            self.sleep(IDLE_EVERY)

    def end_fight(self, result):
        fight = Fight(result, self.fight_turns, self.clock.now() - self.fight_from)
        self.fight_turns = 0
        self.on_fight(fight)
        if result == "victory" and self.stop_after_victory:
            self.stop_note = f"戰鬥勝利（{fight.turns} 回合），自動戰鬥停止"
            raise Stopped

    def play_turn(self, image, box):
        """One turn, acted on a resting HUD only: the Win Rate label also matches in a turn's first frames."""
        self.sleep(STILL_GAP)
        after = self.shot()
        if vision.battle_turn(after) != box or not vision.hud_still(image, after, box) or not vision.turn_page(after):
            return
        try:
            self.submit(after, box)
        except Gone:
            self.emit(Phase.WAITING)

    def check_page(self, image=None):
        """Before a batch of taps: the turn still waits for input with nothing over it, else Gone."""
        if not vision.turn_page(self.shot() if image is None else image):
            raise Gone

    def submit(self, after, box):
        disc = vision.start_disc(box)
        guarded, note = False, ""
        if self.plan.guarding:
            self.emit(Phase.GUARDING)
            if vision.disc_lit(after, disc):  # picks made before (by hand, or Win Rate): a tap on the left gear clears them
                self.check_page(after)
                self.tap(*vision.guard_chain(vision.slot_xs(box[0]))[0])
                after = self.until(lambda im: not vision.disc_lit(im, disc), timeout=1) or self.shot()
            if vision.gear_hollow(after, box):
                note = "專注戰鬥沒有防禦鏈，這回合改用自動選技能，防禦回合數保留"
            else:
                guarded = self.guard(box, disc)
                note = "" if guarded else "防禦沒選上，這回合改用自動選技能"
            if guarded:
                self.plan = self.plan.guarded_once()
        started = guarded or self.pick(box, disc, self.plan.pick, note)
        if not started:
            self.failed += 1
            if self.failed >= MAX_FAILED:
                self.stop_note = f"連續 {MAX_FAILED} 個回合按 START 都沒開始，自動戰鬥停止"
                raise Stopped
            return
        self.failed = 0
        self.turns += 1
        if not self.fight_turns:
            self.fight_from = self.clock.now()
        self.fight_turns += 1
        self.emit(Phase.PLAYING)
        if self.hold:
            self.hold_turn()

    def pick(self, box, disc, pick, note=""):
        """Win Rate or Damage (one tap), then START: whether the turn started. If it did not, the picks are cleared at
        the left gear and the pick and START are tried once more (maalc #145)."""
        self.emit(Phase.PICKING, note)
        dx, dy = vision.WIN_RATE if pick is Pick.WIN_RATE else vision.DAMAGE
        for attempt in range(2):
            image = self.shot()
            for _ in range(2):
                if vision.disc_lit(image, disc) or vision.start_shown(image, disc):
                    break
                # Win Rate toggles: a second tap clears what the first picked, so it is tapped again only when the
                # picks did not show up (maalc #58: a tap in the turn's opening did nothing).
                self.check_page(image)
                self.tap(box[0] + dx, box[1] + dy)
                lit = self.until(lambda im: vision.disc_lit(im, disc), timeout=1.5)
                image = self.shot() if lit is None else lit
                if lit is not None or (pick is Pick.WIN_RATE and vision.win_rate_on(image, box)):
                    break
            if self.press_start(disc):
                return True
            if attempt == 0 and (xs := vision.slot_xs(box[0])):
                self.check_page()
                self.tap(*vision.guard_chain(xs)[0])
                self.until(lambda im: not vision.disc_lit(im, disc), timeout=1)
        return False

    def turn_started(self, image):
        return vision.turn_playing(image) or vision.battle_turn(image) is None

    def press_start(self, disc):
        """Press START: whether the turn starts. Pressed once more when the plaque shows but the turn did not start."""
        for _ in range(2):
            self.tap(*disc)
            if self.until(self.turn_started, timeout=START_WAIT, least=START_LEAST) is not None:
                return True
            if self.until(lambda im: vision.start_shown(im, disc), timeout=PLAQUE_WAIT, every=0.1) is None:
                return False
        return False

    def hold_turn(self):
        """Hold a finger on HOLD_SPOT while the turn plays, until the next turn waits for input, the battle menu
        opens, the engine stops or HOLD_LIMIT s pass. Always lifted on return."""
        end = self.clock.now() + HOLD_LIMIT
        try:
            self.device.touch_down(*HOLD_SPOT)
        except Covered:  # the corner is under another window: this turn plays at its own speed
            self.sleep(IDLE_EVERY)
            return
        try:
            while self.clock.now() < end:
                self.sleep(HOLD_EVERY)
                image = self.shot()
                if vision.turn_playing(image):
                    if vision.popup(image):
                        return  # a popup over the turn (the network): lift so it can be answered
                    continue
                if vision.battle_turn(image) or vision.battle_menu(image) or vision.popup(image):
                    return
                if vision.victory(image) or vision.wiped(image):
                    return  # the battle ended: the engine's next look tells which way
        finally:
            self.device.touch_up()

    def lower_skills(self, xs, before=None, timeout=1.5):
        """The first screenshot whose lower skills at xs read as they did 0.1 s before, after every one of them
        swapped from before; without before, every one shows something. maalc #119: a swap shows 0.1-0.6 s after
        the tap and fades for ~0.4 s."""
        last = [None]

        def done(image):
            now = [vision.guard_score(image, x) for x in xs]
            steady = last[0] is not None and all(abs(a[1] - b[1]) <= 2 for a, b in zip(now, last[0]))
            last[0] = now
            changed = None not in vision.guard_shown(before, now) if before else min(t for _, t in now) > 20
            return steady and changed
        image = self.until(done, timeout=timeout, every=0.1)
        return self.shot() if image is None else image

    def drag(self, points, settle, dwell, hold, pause, step=10):
        """One touch through points: down on the first, settle s, then step px moves pause s apart, dwell s on each
        point; lifted on the last after hold s."""
        self.device.touch_down(*points[0])
        try:
            self.sleep(settle)
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                n = max(1, max(abs(x1 - x0), abs(y1 - y0)) // step)
                for k in range(1, n + 1):
                    self.device.touch_move(round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n))
                    self.sleep(pause)
                if (x1, y1) != points[-1]:
                    self.sleep(dwell)
            self.sleep(hold)
        finally:
            self.device.touch_up()

    def guard(self, box, disc):
        """Pick every slot's guard skill and press START: whether the turn started on guard (maalc PlayTurn.guard).

        A portrait tap swaps the slot's lower skill and its guard skill, and the game can keep the swap from turn to
        turn, so every portrait is tapped once and the lower skills compared before and after; the slots that went
        off guard are tapped back. One drag from the left gear through every lower skill links them, then START.
        A staggered slot acts no skill this turn: it is neither tapped nor dragged through.
        """
        xs = vision.slot_xs(box[0])
        image = self.lower_skills([vision.lower_x(sx) for sx in xs])
        staggered = vision.staggered(image, xs)
        if all(staggered):
            self.check_page(image)
            return self.press_start(disc)
        acting = [sx for sx, s in zip(xs, staggered) if not s]
        lows = [vision.lower_x(sx) for sx in acting]
        before = [vision.guard_score(image, lx) for lx in lows]
        self.check_page(image)
        for sx in acting:
            self.tap(sx, vision.SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        image = self.lower_skills(lows, before)
        after = [vision.guard_score(image, lx) for lx in lows]
        shown = vision.guard_shown(before, after)
        unsure = [i for i, s in enumerate(shown) if s is None]
        if unsure:  # maalc: the glow on a unit's slot flickers; swap those back and compare once more
            self.check_page(image)
            for i in unsure:
                self.tap(acting[i], vision.SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
            image = self.lower_skills([lows[i] for i in unsure], [after[i] for i in unsure])
            again = vision.guard_shown([after[i] for i in unsure], [vision.guard_score(image, lows[i]) for i in unsure])
            for i, s in zip(unsure, again):
                shown[i] = s
        if None in shown:
            return False
        self.check_page(image)
        for sx, on in zip(acting, shown):
            if not on:
                self.tap(sx, vision.SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        chain = vision.guard_chain(xs, staggered)
        for params in GUARD_DRAGS:
            self.check_page()
            self.drag(chain, **params)
            # maalc #145: the panel tilts back for ~0.15 s after the lift; START pressed in it was lost 4 times in 18.
            self.until(lambda im: vision.battle_turn(im) is not None, timeout=1, every=0.05)
            if self.press_start(disc):
                return True
            image = self.shot()
            if not vision.disc_lit(image, disc):
                return False  # the drag linked nothing
            self.check_page(image)
            self.tap(*chain[0])
            self.until(lambda im: not vision.disc_lit(im, disc), timeout=1)
        return False

