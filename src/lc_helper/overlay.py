"""Each option's effects drawn on the game itself, beside the option on its Choices page.

The overlay is a click-through window, just above the game's in the z-order (follow.py), laid exactly over the game's
picture: MuMu's render area
(the nemudisplay child of its device window) or the PC client's client area. Labels sit left of the option list,
over the story box, at each option's height; positions are the OCR boxes, in the game's 1280x720 pixels.
"""

import ctypes
import re
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import device as devices
from . import events, follow, icons

GAME_W, GAME_H = 1280, 720
LABEL_RIGHT = 712  # labels end here, just left of the option list (OCR boxes start at x ~730)
LABEL_LEFT = 40
SHOW_FOR_MS = 60_000  # a read off a page nothing watches stays this long; a watched page's hints go with the page

Rect = tuple[int, int, int, int]  # x, y, w, h in physical screen pixels


@dataclass(frozen=True)
class Label:
    box: tuple[int, int, int, int]  # the option's first OCR line, in game pixels
    text: str
    recommended: bool = False  # drawn with a star before the text and a gold border


def labels(reading, recommend=None) -> list[Label]:
    """The labels for a reading: one per option visible on the page. recommend(option) says whether to star it."""
    rows = events.option_rows(reading.event, reading.lines)
    return [Label(box, events.short_effect(option), bool(recommend and recommend(option))) for option, box in rows]


def fit_16_9(rect: Rect) -> Rect:
    """The 16:9 picture inside a render area: MuMu letterboxes when its window is not 16:9."""
    x, y, w, h = rect
    if w * 9 > h * 16:
        fw = round(h * 16 / 9)
        return x + (w - fw) // 2, y, fw, h
    fh = round(w * 9 / 16)
    return x, y + (h - fh) // 2, w, fh


def mumu_index(address):
    """MuMu 12's instance number from its adb address: port 16384 + 32 x index; None for other addresses."""
    m = re.fullmatch(r"127\.0\.0\.1:(\d+)", address or "")
    if not m or int(m[1]) < 16384 or (int(m[1]) - 16384) % 32:
        return None
    return (int(m[1]) - 16384) // 32


# ---- Windows: find the game's picture on screen (physical pixels) ----

user32 = ctypes.WinDLL("user32")
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@dataclass(frozen=True)
class Win:
    hwnd: int
    pid: int
    cls: str
    title: str
    visible: bool


def _text(hwnd, getter):
    buf = ctypes.create_unicode_buffer(256)
    getter(hwnd, buf, 256)
    return buf.value


def _win(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return Win(hwnd, pid.value, _text(hwnd, user32.GetClassNameW), _text(hwnd, user32.GetWindowTextW),
               bool(user32.IsWindowVisible(hwnd)))


def _windows(parent=None):
    found = []
    callback = EnumProc(lambda hwnd, _: found.append(_win(hwnd)) or True)
    user32.EnumChildWindows(parent, callback, 0) if parent else user32.EnumWindows(callback, 0)
    return found


def pick_mumu_display(tops, children_of, index):
    """The nemudisplay window of MuMu instance index (any, when there is only one), from top-level windows and a
    children_of(hwnd) lookup. MuMu 12 names a hidden window of each device process "...MuMuPlayerGlobal-12.0-<index>"
    (seen 2026-11-13 on instance 0; ※ one sample)."""
    displays = {}  # pid -> display hwnd
    for w in tops:
        if w.visible and w.cls.startswith("Qt"):
            for c in children_of(w.hwnd):
                if c.cls == "nemuwin" and c.visible:
                    displays[w.pid] = c.hwnd
    if not displays:
        return None
    for w in tops:
        m = re.search(r"MuMuPlayerGlobal-[\d.]+-(\d+)$", w.title)
        if m and w.pid in displays and int(m[1]) == index:
            return displays[w.pid]
    return next(iter(displays.values())) if len(displays) == 1 else None


def _rect(hwnd, client=False) -> Rect | None:
    r = wintypes.RECT()
    if client:
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return None
        p = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(p))
        return p.x, p.y, r.right, r.bottom
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def game_picture(source):
    """The window that shows the game for the device read from (None when not found), and whether the picture is its
    client area: the PC client's window, or MuMu's render area."""
    if source == devices.PC:
        return next((w.hwnd for w in _windows() if w.cls == devices.PC_CLASS and w.title == devices.PC_TITLE),
                    None), True
    return pick_mumu_display(_windows(), _windows, mumu_index(source)), False


def game_rect(source) -> Rect | None:
    """Where the game's 1280x720 picture is on screen, in physical pixels, for the device read from; None when its
    window is not found or is minimised."""
    hwnd, client = game_picture(source)
    rect = _rect(hwnd, client) if hwnd and not (client and user32.IsIconic(hwnd)) else None
    return fit_16_9(rect) if rect and rect[2] > 0 and rect[3] > 0 else None


def game_window(source):
    """The game's top-level window for the device read from, the one that comes to the foreground; None when not
    found."""
    return follow.root(game_picture(source)[0])


def lifts():
    """Whether windows are native Windows ones whose z-order follow can set: not under the offscreen platform the
    tests run on, whose window ids are no window handles."""
    return QGuiApplication.platformName() == "windows"


class Overlay(QWidget):
    """The labels, laid over the game. show_labels places it; it follows the game window while shown."""

    def __init__(self, locate=game_rect, window_of=game_window):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.locate, self.window_of = locate, window_of
        self.items: list[Label] = []
        self.source = None
        self.follow = QTimer(self, interval=500, timeout=self.place)
        self.expire = QTimer(self, singleShot=True, timeout=self.hide_labels)

    def show_labels(self, items, source, hold_ms=SHOW_FOR_MS):
        """Show items over the game read from source; hold_ms 0 keeps them until hide_labels."""
        self.items, self.source = list(items), source
        if not self.items or not self.place():
            self.hide_labels()
            return
        self.show()
        self.follow.start()
        self.expire.start(hold_ms) if hold_ms else self.expire.stop()
        self.update()

    def hide_labels(self):
        self.follow.stop()
        self.expire.stop()
        self.items = []
        self.hide()

    def place(self):
        """Lay the window over the game's picture: whether the game is on screen. Placed natively, in physical
        pixels, so it matches the game on any monitor and scale."""
        rect = self.locate(self.source)
        if rect is None:
            self.hide()
            return False
        if not self.isVisible():
            self.show()
        user32.SetWindowPos(int(self.winId()), None, *rect, 0x0010 | 0x0004)  # SWP_NOACTIVATE | SWP_NOZORDER
        self.lift()
        return True

    def lift(self):
        """Just above the game's window: over the game, under every window in front of it."""
        if lifts() and (game := self.window_of(self.source)):
            follow.place_above(int(self.winId()), game)

    def paintEvent(self, _):
        if not self.items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        font = QFont("Microsoft JhengHei UI")
        font.setPixelSize(max(9, round(15 * sy)))
        p.setFont(font)
        metrics = p.fontMetrics()
        ink = QFontMetricsF(font).tightBoundingRect("國")
        middle = -(ink.top() + ink.bottom()) / 2  # the baseline sits this far under the option's middle line
        star = 2 * middle  # as tall as the Chinese glyphs, as in the detail pane
        for item in self.items:
            x, y, _, h = item.box
            lead = star + metrics.horizontalAdvance(" ") if item.recommended else 0
            width = min(metrics.horizontalAdvance(item.text) + lead + 18, (LABEL_RIGHT - LABEL_LEFT) * sx)
            cy = (y + h / 2) * sy
            box = QRectF(LABEL_RIGHT * sx - width, cy - 13 * sy, width, 26 * sy)
            p.setPen(QPen(QColor("#e7b45a" if item.recommended else "#8a6a3a"), 1.2))
            p.setBrush(QColor(15, 12, 9, 225))
            p.drawRoundedRect(box, 6 * sy, 6 * sy)
            if item.recommended:
                icons.paint(p, "star", "#f0c674", QRectF(box.left() + 9, cy - star / 2, star, star))
            p.setPen(QColor("#fff3dc" if item.recommended else "#eadcc4"))
            p.drawText(QPointF(box.left() + 9 + lead, cy + middle),
                       metrics.elidedText(item.text, Qt.ElideRight, int(box.width() - 18 - lead)))
            p.setPen(QPen(QColor("#e7b45a"), 2))  # a short pointer to the option
            p.drawLine(box.right(), cy, (x - 4) * sx, cy)
        p.end()
