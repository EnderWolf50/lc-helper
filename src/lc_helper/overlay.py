"""Each option's effects drawn on the game itself, as a card beside the option on its Choices page.

The overlay is a click-through window, just above the game's in the z-order (follow.py), laid exactly over the game's
picture: MuMu's render area (the nemudisplay child of its device window) or the PC client's client area. The cards
sit over the illustration and the story box, left of the option list, each at its option's height; positions are the
OCR boxes, in the game's 1280x720 pixels. A card says the check's sins, then each outcome (passed, failed, by chance)
with its gifts (keyword icon, name, keyword and tier, the start of the effect) and its HP and SP.
"""

import ctypes
import html
import re
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter,
                           QPalette, QPen, QTextDocument)
from PySide6.QtWidgets import QWidget

from . import device as devices
from . import events, follow, gifts, icons, trials

GAME_W, GAME_H = 1280, 720
# The cards' column, in game pixels: from the story panel's left edge to just short of the option frames (x 690),
# from the top of the story panel to above the party's portraits (EventChoices.png).
CARD_LEFT, CARD_RIGHT, CARD_TOP, CARD_BOTTOM = 52, 678, 108, 612
OPTION_FRAME = 690
CARD_GAP = 6
# Around a post-boss card's centre x: above the card, on the bare background, so neither its gift nor its trial is
# covered (the user, 2026-11-14). BossGiftTrials*.png: the cards 245 wide from y ~158, their Acquire and Owned tags
# from y 152; nothing above them under the top bar's buttons (y < 80).
TRIAL_CARD = (-117, 86, 234, 62)
OPTION_TEXT = 90  # an option's text and hint end within this far under its first line (frames are ~115 apart)
TEXT_PX, SMALL_PX, PAD_PX = 15, 13, 7  # at 1280x720
SHOW_FOR_MS = 60_000  # a read off a page nothing watches stays this long; a watched page's hints go with the page
# The sins as the game colours them, with a text colour that reads on each.
SIN_COLORS = {"暴怒": ("#b8322b", "#fff"), "色慾": ("#d06a1c", "#fff"), "怠惰": ("#d6ad2b", "#1b1408"),
              "暴食": ("#6f9c26", "#fff"), "憂鬱": ("#2f8db0", "#fff"), "傲慢": ("#2f5fb3", "#fff"),
              "嫉妒": ("#7a46ad", "#fff")}
# Kinds of option whose card says its kind at the top when there is no check: a sinless check, a battle, pages to come.
HEADED = {"check", "check_other", "check_fail_gift", "battle", "followup", "followup_other", "random"}
TONES = {"pass": "#8fd17a", "fail": "#ec7b66", "": "#e0b867"}
NOTHING = "<span style='color:#9c8b6e'>沒事發生</span>"
STAT_NAMES = {"hp": "HP", "hp%": "HP", "sp": "SP", "sp%": "SP"}

Rect = tuple[int, int, int, int]  # x, y, w, h in physical screen pixels


@dataclass(frozen=True)
class Label:
    box: tuple[int, int, int, int]  # the option's first OCR line, in game pixels
    option: dict  # the event's option the card is for
    recommended: bool = False  # a star before it and a gold border
    closed: bool = False  # answered in an earlier round: drawn faint
    middle: float | None = None  # the middle of the option's text on the game (its first line's when None)

    @property
    def text(self):
        """The card in one line of words."""
        return events.short_effect(self.option, limit=999)

    @property
    def want(self):
        return self.middle if self.middle is not None else self.box[1] + self.box[3] / 2


def labels(reading, recommend=None) -> list[Label]:
    """The labels for a reading: one per option visible on the page. recommend(option) says whether to star it."""
    rows = events.option_rows(reading.event, reading.lines)
    found = []
    for i, (option, box) in enumerate(rows):
        below = min(rows[i + 1][1][1] if i + 1 < len(rows) else GAME_H, box[1] + OPTION_TEXT)
        bottom = max(b[1] + b[3] for _, b in reading.lines if box[1] <= b[1] < below)
        found.append(Label(box, option, bool(recommend and recommend(option)), option["text"] in reading.closed,
                           (box[1] + bottom) / 2))
    return found


def hint_rest(option):
    """The game's hint without its check: what the option says it does, for a card with no gift to show."""
    hint = option.get("hint_zh") or option.get("hint") or ""
    return re.sub(r"^(進行)?" + events.CHECK.pattern + r"[ ，,]*", "", hint).strip()


def gets_html(gets):
    """A branch's HP, SP, cost and the like: each amount coloured by its sign, the sinners it falls on after."""
    parts, last_target = [], None
    for g in gets:
        what, target = g[0], (g[2] if len(g) > 2 else None)
        if target != last_target and last_target is not None:
            parts.append(f"<span style='color:#9c8b6e'>{html.escape(events.TARGETS.get(last_target, last_target))}</span>")
        last_target = target
        if what in STAT_NAMES:
            sign = "#8fd17a" if g[1] == "max" or g[1] > 0 else "#ec7b66"
            amount = "補滿" if g[1] == "max" else f"{g[1]:+g}".replace("-", "−") + ("%" if what.endswith("%") else "")
            parts.append(f"<span style='color:#b9a888'>{STAT_NAMES[what]}</span> <span style='color:{sign}'>{amount}</span>")
        elif what == "cost":
            parts.append(f"<span style='color:#b9a888'>經費</span> <span style='color:#e0b867'>{g[1]:+g}</span>")
        else:
            parts.append(html.escape(events.get_text(g)))
    if last_target is not None:
        parts.append(f"<span style='color:#9c8b6e'>{html.escape(events.TARGETS.get(last_target, last_target))}</span>")
    return "&nbsp;&nbsp;".join(parts)


def gift_html(gid, how, desc_lines, desc_width, small):
    """A gift: its keyword icon, name, keyword and tier, and its effect cut to desc_lines lines of desc_width px."""
    g = gifts.book().get(gid) or {}
    name = html.escape(g.get("zh") or g.get("en") or f"飾品 {gid}")
    keyword = g.get("keyword", "Keywordless")
    tier = events.ROMAN.get(g.get("tier"), "")
    tail = " ".join(x for x in (events.KEYWORDS.get(keyword, keyword), tier, how) if x)
    row = (f"<img src='kw:{keyword}' style='vertical-align: middle'> <span style='color:#f3cf7e'>{name}</span>"
           f" <span style='color:#a8977a'>{html.escape(tail)}</span>")
    desc = " ".join((g.get("desc_zh") or g.get("desc_en") or "").split())
    if desc_lines and desc:
        cut = QFontMetricsF(small).elidedText(desc, Qt.ElideRight, desc_width * desc_lines - small.pixelSize() * 2)
        row += f"<br><span style='color:#cbbd9f;font-size:{small.pixelSize()}px'>{html.escape(cut)}</span>"
    return row


def card_html(label, font, small, width, desc_lines):
    """A card's rich text: a head (star, the check's sins, a battle or a page to come), then a row per outcome."""
    o = label.option
    head = ["<img src='icon:star' style='vertical-align: middle'>"] if label.recommended else []
    sins = events.check_sins(o)
    if sins:
        head += [f"<span style='background-color:{SIN_COLORS[s][0]};color:{SIN_COLORS[s][1]}'>&nbsp;{s}&nbsp;</span>"
                 for s in sins]
        head.append("<span style='color:#eadcc4'>優勢判定</span>")
    elif o["kind"] in HEADED:
        head.append(f"<span style='color:#b9a888'>{html.escape(events.kind_text(o))}</span>")
    elif label.recommended:
        head.append("<span style='color:#f0c674'>推薦</span>")
    if label.closed:
        head.append("<span style='color:#9c8b6e'>已選過</span>")
    found = events.outcomes(o)
    metrics = QFontMetricsF(font)
    tag_w = max((metrics.horizontalAdvance(f.when) for f in found), default=0) + font.pixelSize() * 0.6
    rows = []
    for f in found:
        what = [gift_html(gid, how, desc_lines, width - tag_w, small) for gid, how in f.gifts]
        if f.gets:
            what.append(gets_html(f.gets))
        rows.append(f"<tr><td width='{tag_w:.0f}' style='color:{TONES[f.tone]}'>{html.escape(f.when)}</td>"
                    f"<td>{'<br>'.join(what) or NOTHING}</td></tr>")
    body = f"<table width='100%' cellspacing='0' cellpadding='1'>{''.join(rows)}</table>" if rows else ""
    if not any(f.gifts for f in found) and (rest := hint_rest(o) or ("" if rows else "沒有記錄效果")):
        body += f"<p style='margin:0;color:#cbbd9f'>{html.escape(rest)}</p>"
    return (f"<p style='margin:0 0 2px 0'>{'&nbsp;'.join(head)}</p>" if head else "") + body


def trial_html(w, small, width):
    """A post-boss card's worth: its rank (a star and 推薦 for a pick), its total, how it adds up, and its trial's
    effect in Chinese, cut to the card's width."""
    gold = "#f0c674"
    head = ("<img src='icon:star' style='vertical-align: middle'> " if w.pick else "") + (
        f"<span style='color:{gold if w.pick else '#eadcc4'}'>{'推薦 ' if w.pick else ''}第 {w.rank}</span>")
    total = f"<span style='color:{'#8fd17a' if w.total >= 0 else '#ec7b66'}'>{w.total:+.1f}</span>"
    why = "已持有" if w.card.owned else "推薦體系" if w.gift >= trials.GIFT_SCORES["main"] else ""
    calc = (f"<span style='color:#b9a888;font-size:{small.pixelSize()}px'>飾品 {w.gift:g}{f'（{why}）' if why else ''}"
            f" − 苦難 {w.burden:.1f}</span>")
    t = trials.book()["trials"].get(w.card.trial) if w.card.trial else None
    effect = (QFontMetricsF(small).elidedText(t["desc_zh"] or t["desc_en"], Qt.ElideRight, width) if t
              else "苦難沒認出：照這層最重的算")
    return (f"<p style='margin:0'>{head}&nbsp;&nbsp;{total}</p><p style='margin:0'>{calc}</p>"
            f"<p style='margin:0;color:#cbbd9f;font-size:{small.pixelSize()}px'>{html.escape(effect)}</p>")


def stack(wants, heights, top=CARD_TOP, bottom=CARD_BOTTOM, gap=CARD_GAP):
    """Tops for cards of heights, each centred on its want if it can be, top to bottom, none over another and all
    between top and bottom (the top one may rise past top when they cannot all fit)."""
    tops = []
    for want, h in zip(wants, heights):
        below = tops[-1] + heights[len(tops) - 1] + gap if tops else top
        tops.append(max(want - h / 2, top, below))
    limit = bottom
    for i in reversed(range(len(tops))):
        tops[i] = min(tops[i], limit - heights[i])
        limit = tops[i] - gap
    return tops


def room(wants, i, top=CARD_TOP, bottom=CARD_BOTTOM, gap=CARD_GAP):
    """The height card i can take without pushing its neighbours off their options: twice its want's distance to
    the nearer of the halfway lines to its neighbours (or the column's ends)."""
    up = (wants[i] - wants[i - 1]) / 2 if i else wants[i] - top
    down = (wants[i + 1] - wants[i]) / 2 if i + 1 < len(wants) else bottom - wants[i]
    return 2 * min(up, down) - gap


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
        self.trials: list[trials.Worth] = []  # the post-boss cards' worth, shown instead of items
        self.source = None
        self.follow = QTimer(self, interval=500, timeout=self.place)
        self.expire = QTimer(self, singleShot=True, timeout=self.hide_labels)

    def show_labels(self, items, source, hold_ms=SHOW_FOR_MS):
        """Show items over the game read from source; hold_ms 0 keeps them until hide_labels."""
        self.show_cards(list(items), [], source, hold_ms)

    def show_trials(self, worths, source):
        """Each post-boss card's worth above it, until hide_labels: the worker tells the page's leaving."""
        self.show_cards([], list(worths), source, 0)

    def show_cards(self, items, worths, source, hold_ms):
        self.items, self.trials, self.source = items, worths, source
        if not (self.items or self.trials) or not self.place():
            self.hide_labels()
            return
        self.show()
        self.follow.start()
        self.expire.start(hold_ms) if hold_ms else self.expire.stop()
        self.update()

    def hide_labels(self):
        self.follow.stop()
        self.expire.stop()
        self.items, self.trials = [], []
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

    def fonts(self):
        """The cards' text and small text (the gifts' effects), at the game's scale."""
        sy = self.height() / GAME_H
        font, small = QFont("Microsoft JhengHei UI"), QFont("Microsoft JhengHei UI")
        font.setPixelSize(max(9, round(TEXT_PX * sy)))
        small.setPixelSize(max(8, round(SMALL_PX * sy)))
        return font, small

    def document(self, label, width, desc_lines):
        """label's card as a text document width overlay pixels wide, its gifts' effects cut to desc_lines lines."""
        font, small = self.fonts()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(font)
        side, ratio = font.pixelSize() * 1.2, self.devicePixelRatioF()
        doc.addResource(QTextDocument.ImageResource, QUrl("icon:star"), icons.pixmap("star", "#f0c674", side, ratio))
        for f in events.outcomes(label.option):
            for gid, _ in f.gifts:
                k = (gifts.book().get(gid) or {}).get("keyword", "Keywordless")
                doc.addResource(QTextDocument.ImageResource, QUrl(f"kw:{k}"), icons.keyword(k, side, ratio))
        doc.setTextWidth(width)
        doc.setHtml(card_html(label, font, small, width, desc_lines))
        return doc

    def cards(self):
        """Each label's card laid out on the overlay, top to bottom: (label, document, rect in overlay pixels). A
        card shows as much of its gifts' effects as fits between its neighbours' options."""
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        width = (CARD_RIGHT - CARD_LEFT) * sx
        items = sorted(self.items, key=lambda label: label.want)
        wants = [label.want for label in items]
        docs = []
        for i, label in enumerate(items):
            for lines in (2, 1, 0):
                doc = self.document(label, width - 2 * pad, lines)
                if doc.size().height() + 2 * pad <= room(wants, i) * sy:
                    break
            docs.append(doc)
        heights = [(doc.size().height() + 2 * pad) / sy for doc in docs]
        tops = stack(wants, heights)
        return [(label, doc, QRectF(CARD_LEFT * sx, top * sy, width, h * sy))
                for label, doc, top, h in zip(items, docs, tops, heights)]

    def paintEvent(self, _):
        if not (self.items or self.trials):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.Text, QColor("#eadcc4"))
        for label, doc, rect in self.cards():
            gold = label.recommended
            p.setOpacity(1.0)
            p.setPen(QPen(QColor("#e7b45a" if gold else "#7a5d33"), (1.6 if gold else 1.0) * max(sy, 1)))
            p.setBrush(QColor(14, 11, 8, 245))
            p.drawRoundedRect(rect, 6 * sy, 6 * sy)
            y = min(max(label.want * sy, rect.top() + 10 * sy), rect.bottom() - 10 * sy)  # a pointer to the option
            p.setPen(QPen(QColor("#e7b45a" if gold else "#a07c45"), 2 * max(sy, 1)))
            p.drawLine(QPointF(rect.right(), y), QPointF((OPTION_FRAME - 3) * sx, y))
            p.save()
            p.setOpacity(0.5 if label.closed else 1.0)  # an answered option's card stays solid, its words faint
            p.translate(rect.left() + pad, rect.top() + pad)
            doc.documentLayout().draw(p, context)
            p.restore()
        for w, doc, rect in self.trial_cards():
            p.setPen(QPen(QColor("#e7b45a" if w.pick else "#7a5d33"), (1.6 if w.pick else 1.0) * max(sy, 1)))
            p.setBrush(QColor(14, 11, 8, 245))
            p.drawRoundedRect(rect, 6 * sy, 6 * sy)
            p.save()
            p.translate(rect.left() + pad, rect.top() + pad * 0.6)
            doc.documentLayout().draw(p, context)
            p.restore()
        p.end()

    def trial_cards(self):
        """Each post-boss card's worth laid out above the card: (worth, document, rect in overlay
        pixels)."""
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        dx, y, w, h = TRIAL_CARD
        font, small = self.fonts()
        side, ratio = font.pixelSize() * 1.2, self.devicePixelRatioF()
        star = icons.pixmap("star", "#f0c674", side, ratio)
        cards = []
        for worth in self.trials:
            rect = QRectF((worth.card.x + dx) * sx, y * sy, w * sx, h * sy)
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(font)
            doc.addResource(QTextDocument.ImageResource, QUrl("icon:star"), star)
            doc.setTextWidth(rect.width() - 2 * pad)
            doc.setHtml(trial_html(worth, small, rect.width() - 2 * pad))
            cards.append((worth, doc, rect))
        return cards
