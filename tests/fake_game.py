"""A battle made of maalc's live screenshots that answers taps and drags the way the game does, on a virtual clock."""

import threading

from lc_helper import vision

WIN_RATE_AT = (1004, 545)  # vision.WIN_RATE / DAMAGE from the BattleTurn.png label at (984, 531)
DAMAGE_AT = (1004, 583)
NEAR = 12


class VirtualClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.001)


def near(p, q):
    return abs(p[0] - q[0]) <= NEAR and abs(p[1] - q[1]) <= NEAR


class FakeBattle:
    """turns turns of a battle, then the VICTORY screen; stop is set once the engine has looked at it twice, or after
    max_shots screenshots. With start_works False, START does nothing.

    States: "turn" (BattleTurn.png, or `turn_image`), "lit" (picks made: BattleTurnLit.png), "playing"
    (BattlePause.png for `play_s`), "over" (Victory.png). A portrait tap swaps that slot's lower skill with a flat
    brown guard icon; a drag from the left gear through every acting slot's lower skill links the guard chain.
    """

    can_hold = True

    def __init__(self, screen, clock, turns=3, turn_image="BattleTurn.png", play_s=2.0, max_shots=None,
                 start_works=True, menu_after_pick=False, popup_while_playing=False):
        self.screen, self.clock, self.turns, self.play_s = screen, clock, turns, play_s
        self.max_shots, self.start_works, self.shots = max_shots, start_works, 0
        self.menu_after_pick, self.popup_while_playing = menu_after_pick, popup_while_playing
        self.holds = []  # (down, up) virtual times of each finger held on (1, 1)
        self.base = screen(turn_image)
        self.box = vision.battle_turn(self.base)
        self.xs = vision.slot_xs(self.box[0])
        self.chain = vision.guard_chain(self.xs)
        self.state, self.started, self.picked, self.looks_over = "turn", 0, None, 0
        self.swapped = [False] * len(self.xs)
        self.log, self.taps, self.path, self.down = [], [], [], None
        self.stop = threading.Event()

    def screenshot(self):
        self.shots += 1
        if self.max_shots and self.shots >= self.max_shots:
            self.stop.set()
        if self.state == "playing" and self.clock.now() >= self.play_until:
            self.state = "turn" if self.started < self.turns else "over"
        if self.state == "over":
            self.looks_over += 1
            if self.looks_over >= 2:
                self.stop.set()
            return self.screen("Victory.png")
        if self.state == "menu":
            return self.screen("BattleMenu.png")
        if self.state == "playing":
            image = self.screen("BattlePause.png")
            if self.popup_while_playing:
                button = vision.template("dialog_button.png")
                h, w = button.shape[:2]
                image[420:420 + h, 560:560 + w] = button
            return image
        image = self.screen("BattleTurnLit.png") if self.state == "lit" else self.base.copy()
        if self.state == "turn":
            for x, on in zip(self.xs, self.swapped):
                if on:
                    lx = vision.lower_x(x)
                    image[vision.LOWER_Y - 16:vision.LOWER_Y + 16, lx - 16:lx + 16] = (50, 100, 150)
        return image

    def tap(self, x, y):
        p = (x, y)
        if self.state == "turn" and near(p, WIN_RATE_AT) and self.menu_after_pick:
            self.state = "menu"  # the user opened the battle menu right as Win Rate was tapped
        elif self.state == "turn" and near(p, WIN_RATE_AT):
            self.picked, self.state = "win_rate", "lit"
        elif self.state == "turn" and near(p, DAMAGE_AT):
            self.picked, self.state = "damage", "lit"
        elif self.state == "lit" and near(p, vision.start_disc(self.box)) and self.start_works:
            self.log.append(self.picked)
            self.started += 1
            self.state, self.play_until = "playing", self.clock.now() + self.play_s
        elif self.state == "lit" and near(p, self.chain[0]):
            self.state, self.picked = "turn", None
        elif self.state == "turn":
            for i, x in enumerate(self.xs):
                if near(p, (x, vision.SLOT_PORTRAIT_Y)):
                    self.swapped[i] = not self.swapped[i]
        self.taps.append(p)

    def touch_down(self, x, y):
        self.down, self.path = (x, y), [(x, y)]
        self.down_at = self.clock.now()

    def touch_move(self, x, y):
        self.path.append((x, y))

    def touch_up(self):
        if self.down == (1, 1):
            self.log.append("hold")
            self.holds.append((self.down_at, self.clock.now()))
        elif self.state == "turn" and near(self.down, self.chain[0]):
            linked = all(any(near(q, (x, 665)) for q in self.path) for x in self.xs)
            if linked and all(self.swapped):
                self.picked, self.state = "guard", "lit"
        self.down = None

    def starts(self):
        """What each started turn was played with, in order: "win_rate", "damage" or "guard"."""
        return [e for e in self.log if e != "hold"]
