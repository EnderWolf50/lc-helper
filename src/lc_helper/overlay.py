"""Each option's effects drawn on the game itself, as a card beside the option on its Choices page.

The overlay is a window just above the game's in the z-order (follow.py), laid exactly over the game's picture: MuMu's
render area (the nemudisplay child of its device window) or the PC client's client area. The cards sit over the
illustration and the story box, left of the option list, each at its option's height; positions are the OCR boxes, in
the game's 1280x720 pixels. A card at a glance says the check's sins, then a block per outcome (passed, failed, by
chance) with its gifts' pictures and its HP and SP; a click opens it in full, each gift's name and whole effect. The
post-boss gift choice gets each card's worth above it, and the shop's fuse page the gift a recipe makes beside the
wheel, a click opening its whole effect. The window takes clicks only on its cards: every other click goes through to
the game, and none takes the game's focus.
"""

import ctypes
import html
import re
from ctypes import wintypes
from dataclasses import dataclass
from itertools import groupby

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter,
                           QPalette, QPen, QRegion, QTextCharFormat, QTextDocument)
from PySide6.QtWidgets import QWidget

from . import device as devices
from . import events, follow, gifts, icons, trials
from .palette import INK, TEXT_FAMILY, display_family

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
PICTURE_GAP, GIFT_GAP = 6, 3  # overlay px: a gift's picture to its name; one gift's picture to the next's
POINTER_END = 10  # game px: a card's pointer to its option leaves the card at least this far from its corners
# The brief cards' gift pictures, as tall as a line and this many small lines (picture_side), the biggest first:
# Overlay.cards takes the first at which the cards all stay beside their options. One line alone is too small (the
# user, 2026-11-14). A full card's pictures are as tall as the first.
PICTURE_LINES = (2, 1)
# A brief card's block per outcome: its fill, and the gap between blocks and the margin inside one, as shares of the
# small text's size.
BLOCK_FILL, BLOCK_GAP, BLOCK_PAD = INK["raise"], 0.45, 0.35
EDGE = 8  # game px: a full card taller than the cards' column keeps this far inside the game's picture
CUT = 6  # game px: a card's corners cut off at 45 degrees, as the game's frames and maalc's are
# The fuse page's box, in game pixels, under the shop's top-left button (y 25-80) and above the party's portraits
# (CARD_BOTTOM). Brief, it is left of the wheel, whose left material slot starts at x 187 (ShopFuseRecipe.png), so that
# it covers no material slot (a 4- or 5-material recipe's, unseen, also sit on the wheel ※), its middle at the centre
# slot's, no taller than FUSE_BRIEF: about the centre slot's frame (y 283-415). Opened, it runs over the wheel up to
# FUSE_OPEN_RIGHT, short of the owned gifts' panel (x ~605).
FUSE_LEFT, FUSE_RIGHT, FUSE_OPEN_RIGHT, FUSE_TOP, FUSE_BRIEF = EDGE, 178, 590, 100, 130
# The fuse box's effect text, px at 1280x720: brief at the first, cut; opened, the largest at which the whole effect
# fits, else the last with the effect cut.
FUSE_SMALL = (13, 12, 11)
SHOW_FOR_MS = 60_000  # a read off a page nothing watches stays this long; a watched page's hints go with the page
SIN_SIDE = 1.35  # a check's sin icon, as a share of its line's text size
# Barlow Condensed's size as a share of the text's beside it: narrow and short, its digits stand as tall as the CJK
# text at this.
NUMERALS = 1.15
# Kinds of option whose card says its kind at the top when there is no check: a sinless check, a battle, pages to come.
HEADED = {"check", "check_other", "check_fail_gift", "battle", "followup", "followup_other", "random"}
TONES = {"pass": INK["keep"], "fail": INK["bad"], "": INK["accent-ink"]}
NOTHING = f"<span style='color:{INK['muted']}'>沒事發生</span>"
# Between one effect and the next, maalc's " · " (gui/src/App.tsx): a line breaks after it, never inside an effect.
SEPARATOR = f"<span style='color:{INK['muted']}'>&nbsp;· </span>"
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


def numerals(text, px, weight, ink):
    """text in maalc's condensed face at weight, sized to stand as tall as px text beside it."""
    return (f"<span style='font-family:\"{display_family(weight)}\";font-size:{round(px * NUMERALS)}px;"
            f"font-weight:{weight};color:{INK[ink]}'>{text}</span>")


def effect_html(g, px):
    """One gets entry at px: a stat's name and amount (coloured by its sign) or the cost and its amount, in maalc's
    condensed face; else the effect in words."""
    what = g[0]
    if what in STAT_NAMES:
        if g[1] == "max":
            amount = f"<span style='color:{INK['keep']}'>補滿</span>"
        else:
            amount = numerals(f"{g[1]:+g}".replace("-", "−") + ("%" if what.endswith("%") else ""), px, 700,
                              "keep" if g[1] > 0 else "bad")
        return numerals(STAT_NAMES[what], px, 600, "muted") + "&nbsp;" + amount
    if what == "cost":
        return (f"<span style='color:{INK['muted']}'>經費</span>&nbsp;"
                + numerals(f"{g[1]:+g}".replace("-", "−"), px, 700, "accent-ink"))
    return f"<span style='color:{INK['fg-2']}'>{html.escape(events.get_text(g))}</span>"


def gets_html(gets, px):
    """A branch's HP, SP, cost and the like at px, a dot between one effect and the next: each run of effects on the
    same sinners (a gets entry's third item) led by a chip naming them."""
    parts = []
    for target, run in groupby(gets, key=lambda g: g[2] if len(g) > 2 else None):
        effects = [effect_html(g, px) for g in run]
        if target is not None:
            name = html.escape(events.TARGETS.get(target, target)).replace(" ", "&nbsp;")
            effects[0] = (f"<span style='background-color:{INK['line']};color:{INK['fg-2']}'>&nbsp;{name}&nbsp;</span>"
                          f"&nbsp;{effects[0]}")
        parts += effects
    return SEPARATOR.join(parts)


def picture_side(font, small, lines):
    """A gift's picture on an event card, px: as tall as a line of text and lines lines of small text. Every card on a
    page has its pictures one size (Overlay.cards; the user, 2026-11-14: pictures of different sizes)."""
    return QFontMetricsF(font).height() + lines * QFontMetricsF(small).height()


def on_text(pix, font):
    """pix for font's text, set on the baseline (on_baseline): cut to its drawing and padded below, so its middle meets
    the middle of the CJK glyphs beside it. Qt sets such a picture's bottom a descent under the baseline
    (qtextdocumentlayout.cpp, resizeInlineObject). vertical-align: middle centres one a quarter of the x-height over the
    baseline instead, well under a CJK glyph's middle: the sin icons sat low (the user, 2026-11-15)."""
    pix = icons.inked(pix)
    m = QFontMetricsF(font)
    glyphs = -m.tightBoundingRect("判定").center().y()  # above the baseline
    return icons.padded_below(pix, max(0.0, glyphs + m.descent() - pix.height() / pix.devicePixelRatio() / 2))


def on_baseline(doc):
    """doc's star and sin icons set on the baseline, for on_text. HTML cannot ask for it: Qt reads vertical-align:
    baseline as normal, the picture's bottom on the baseline (qtexthtmlparser.cpp)."""
    cursor = doc.find("\ufffc")  # each picture is one object character
    while not cursor.isNull():
        f = cursor.charFormat()
        if f.isImageFormat() and f.toImageFormat().name().startswith(("sin:", "icon:")):
            f.setVerticalAlignment(QTextCharFormat.AlignBaseline)
            cursor.setCharFormat(f)
        cursor = doc.find("\ufffc", cursor)


def head_html(label):
    """A card's head: a star for the recommended one, the check's sins (else a battle or a page to come), and
    whether it was answered already; empty for none of these."""
    o = label.option
    head = ["<img src='icon:star'>"] if label.recommended else []
    sins = events.check_sins(o)
    if sins:
        head.append(" ".join(f"<img src='sin:{icons.SIN_ICONS[s]}'>&#8239;"
                             f"<span style='color:{INK['fg-2']}'>{s}</span>" for s in sins))
        head.append(f"<span style='color:{INK['muted']}'>優勢判定</span>")
    elif o["kind"] in HEADED:
        head.append(f"<span style='color:{INK['muted']}'>{html.escape(events.kind_text(o))}</span>")
    elif label.recommended:
        head.append(f"<span style='color:{INK['accent']}'>推薦</span>")
    if label.closed:
        head.append(f"<span style='color:{INK['muted']}'>已選過</span>")
    return f"<p style='margin:0 0 2px 0'>{'&nbsp;'.join(head)}</p>" if head else ""


def rest_html(option, found):
    """What an option says it does when it gives no gift (or that nothing is recorded for it), as a line."""
    rest = hint_rest(option) or ("" if found else "沒有記錄效果")
    if any(f.gifts for f in found) or not rest:
        return ""
    return f"<p style='margin:0;color:{INK['fg-2']}'>{html.escape(rest)}</p>"


def brief_html(label, small):
    """A card at a glance: its head, then a block per outcome (passed, failed, by chance) with its tag, its gifts'
    pictures (gift:ID, their keyword and tier on them) and what it costs or gives. The gifts' names and effects wait
    for a click (full_html): most players look only at the pictures (the user, 2026-11-14)."""
    found = events.outcomes(label.option)
    note = f"color:{INK['muted']};font-size:{small.pixelSize()}px"
    gap, pad = round(small.pixelSize() * BLOCK_GAP), round(small.pixelSize() * BLOCK_PAD)
    blocks = []
    for f in found:
        parts = [f"<p style='margin:0;color:{TONES[f.tone]}'>{html.escape(f.when)}</p>"]
        if f.gifts:
            parts.append("<p style='margin:0'>" + "&nbsp;".join(
                f"<img src='gift:{gid}'>" + (f"<span style='{note}'>&nbsp;{html.escape(how)}</span>" if how else "")
                for gid, how in f.gifts) + "</p>")
        if f.gets:
            parts.append(f"<p style='margin:0;font-size:{small.pixelSize()}px'>"
                         f"{gets_html(f.gets, small.pixelSize())}</p>")
        if not (f.gifts or f.gets):
            parts.append(f"<p style='margin:0'>{NOTHING}</p>")
        blocks.append(f"<td bgcolor='{BLOCK_FILL}' valign='top'>{''.join(parts)}</td>")
    body = (f"<table cellspacing='{gap}' cellpadding='{pad}' style='margin:-{gap}px'>"
            f"<tr>{''.join(blocks)}</tr></table>" if blocks else "")
    return head_html(label) + body + rest_html(label.option, found)


def gift_effect(gid):
    g = gifts.book().get(gid) or {}
    return (g.get("desc_zh") or g.get("desc_en") or "").strip()


def gift_text(gid, how, px, cut=None):
    """A gift's name, its keyword, tier and how, and under them its effect at px: whole, or its first cut characters
    and an ellipsis."""
    g = gifts.book().get(gid) or {}
    name = html.escape(g.get("zh") or g.get("en") or f"飾品 {gid}")
    keyword = g.get("keyword", "Keywordless")
    tier = events.ROMAN.get(g.get("tier"), "")
    tail = " ".join(x for x in (events.KEYWORDS.get(keyword, keyword), tier, how) if x)
    text = (f"<span style='color:{INK['fg']};font-weight:600'>{name}</span> "
            f"<span style='color:{INK['muted']}'>{html.escape(tail)}</span>")
    desc = gift_effect(gid) if cut is None else gift_effect(gid)[:cut].rstrip() + "…"
    if desc:
        text += (f"<br><span style='color:{INK['fg-2']};font-size:{px}px'>"
                 f"{html.escape(desc).replace(chr(10), '<br>')}</span>")
    return text


def gift_html(gid, how, side, small, first=True):
    """A gift on a full card: the game's slot of it (gift:ID, side px, its tier and keyword on it), then its text
    (gift_text). A gift after the first in its outcome sits a little below the one before, so their pictures do not
    touch."""
    above = "" if first else f" style='margin-top:{GIFT_GAP}px'"
    return (f"<table cellspacing='0' cellpadding='0'{above}><tr><td width='{side + PICTURE_GAP:.0f}' valign='top'>"
            f"<img src='gift:{gid}'></td><td valign='middle'>{gift_text(gid, how, small.pixelSize())}</td></tr>"
            "</table>")


def fuse_html(gid, px, cut, rest):
    """The fuse box: the gift's text (gift_text), and under an effect cut to fit, rest: where to read the rest."""
    more = f"<br><span style='color:{INK['muted']};font-size:{px}px'>{rest}</span>" if cut is not None else ""
    return gift_text(gid, "", px, cut) + more


def full_html(label, font, small, side):
    """A card opened by a click: its head, then a row per outcome with each gift's picture (side px), name, keyword,
    tier and whole effect, and its HP and SP."""
    found = events.outcomes(label.option)
    tag_w = max((QFontMetricsF(font).horizontalAdvance(f.when) for f in found), default=0) + font.pixelSize() * 0.6
    rows = []
    for f in found:
        what = [gift_html(gid, how, side, small, first=not j) for j, (gid, how) in enumerate(f.gifts)]
        if f.gets:
            what.append(f"<p style='margin:0'>{gets_html(f.gets, font.pixelSize())}</p>")  # under the gifts (blocks)
        rows.append(f"<tr><td width='{tag_w:.0f}' style='color:{TONES[f.tone]}'>{html.escape(f.when)}</td>"
                    f"<td>{''.join(what) or NOTHING}</td></tr>")
    body = f"<table width='100%' cellspacing='0' cellpadding='1'>{''.join(rows)}</table>" if rows else ""
    return head_html(label) + body + rest_html(label.option, found)


def trial_html(w, small, width):
    """A post-boss card's worth: its rank (a star and 推薦 for a pick), its total, how it adds up, and its trial's
    effect in Chinese, cut to the card's width."""
    head = ("<img src='icon:star'> " if w.pick else "") + (
        f"<span style='color:{INK['accent' if w.pick else 'fg']}'>{'推薦 ' if w.pick else ''}第 {w.rank}</span>")
    total = f"<span style='color:{INK['keep' if w.total >= 0 else 'bad']}'>{w.total:+.1f}</span>"
    why = "已持有" if w.card.owned else "推薦體系" if w.gift >= trials.GIFT_SCORES["main"] else ""
    calc = (f"<span style='color:{INK['muted']};font-size:{small.pixelSize()}px'>飾品 {w.gift:g}"
            f"{f'（{why}）' if why else ''} − 苦難 {w.burden:.1f}</span>")
    t = trials.book()["trials"].get(w.card.trial) if w.card.trial else None
    effect = (QFontMetricsF(small).elidedText(t["desc_zh"] or t["desc_en"], Qt.ElideRight, width) if t
              else "苦難沒認出：照這層最重的算")
    return (f"<p style='margin:0'>{head}&nbsp;&nbsp;{total}</p><p style='margin:0'>{calc}</p>"
            f"<p style='margin:0;color:{INK['fg-2']};font-size:{small.pixelSize()}px'>{html.escape(effect)}</p>")


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


def beside(wants, tops, heights, top=CARD_TOP):
    """Whether stacked cards each stay beside their option: all under the column's top, and each one's pointer
    meeting its option's middle, not stopped at the card's edge."""
    return (not tops or tops[0] >= top) and all(
        t + POINTER_END <= want <= t + h - POINTER_END for want, t, h in zip(wants, tops, heights))


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
        # Clicks on the cards open and close them; the mask (set_mask) passes every other click to the game below.
        # WindowDoesNotAcceptFocus is WS_EX_NOACTIVATE: a click leaves the game the foreground window.
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.locate, self.window_of = locate, window_of
        self.items: list[Label] = []
        self.trials: list[trials.Worth] = []  # the post-boss cards' worth, shown instead of items
        self.fuse = None  # (gift, its picture's box): the gift the fuse page's recipe makes, shown instead of items
        # The card open in full: its option's text, or the fuse box's gift id.
        self.opened: str | int | None = None
        self.hits: list[tuple[str | int, QRectF]] = []  # (the opened key, rect) of each card a click opens or closes
        self.source = None
        self.follow = QTimer(self, interval=500, timeout=self.place)
        self.expire = QTimer(self, singleShot=True, timeout=self.hide_labels)

    def show_labels(self, items, source, hold_ms=SHOW_FOR_MS):
        """Show items over the game read from source; hold_ms 0 keeps them until hide_labels. An open card stays
        open while its option is still among them (a page read again)."""
        self.show_cards(list(items), [], source, hold_ms)

    def show_trials(self, worths, source):
        """Each post-boss card's worth above it, until hide_labels: the worker tells the page's leaving."""
        self.show_cards([], list(worths), source, 0)

    def show_fuse(self, gift, box, source):
        """The gift the fuse page's recipe makes, its picture at box, beside the wheel until hide_labels: the worker
        tells the page's leaving. A box opened by a click stays open while its gift is the one shown."""
        self.show_cards([], [], source, 0, (gift, box))

    def show_cards(self, items, worths, source, hold_ms, fuse=None):
        self.items, self.trials, self.fuse, self.source = items, worths, fuse, source
        if self.opened not in {label.option["text"] for label in items} | ({fuse[0]["id"]} if fuse else set()):
            self.opened = None
        if not self.showing() or not self.place():
            self.hide_labels()
            return
        self.show()
        self.follow.start()
        self.expire.start(hold_ms) if hold_ms else self.expire.stop()
        self.set_mask()
        self.update()

    def hide_labels(self):
        self.follow.stop()
        self.expire.stop()
        self.items, self.trials, self.fuse, self.opened, self.hits = [], [], None, None, []
        self.hide()

    def showing(self):
        return bool(self.items or self.trials or self.fuse)

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

    def resizeEvent(self, e):
        """The game's window resized: the cards move, and the mask with them. A hidden window's mask waits for
        show_cards."""
        if self.isVisible():
            self.set_mask()
        super().resizeEvent(e)

    def fonts(self):
        """The cards' text and small text (the gifts' effects), at the game's scale."""
        sy = self.height() / GAME_H
        font, small = QFont(TEXT_FAMILY), QFont(TEXT_FAMILY)
        font.setPixelSize(max(9, round(TEXT_PX * sy)))
        small.setPixelSize(max(8, round(SMALL_PX * sy)))
        return font, small

    def document(self, label, width, lines, full=False):
        """label's card as a text document width overlay pixels wide, its gifts in the game's slot (icons.game_gift)
        as tall as a line and lines small lines: brief (brief_html), or full (full_html)."""
        font, small = self.fonts()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(font)
        side, ratio = font.pixelSize() * 1.2, self.devicePixelRatioF()
        doc.addResource(QTextDocument.ImageResource, QUrl("icon:star"),
                        on_text(icons.pixmap("star", INK["accent"], side, ratio), font))
        for s in events.check_sins(label.option):
            doc.addResource(QTextDocument.ImageResource, QUrl(f"sin:{icons.SIN_ICONS[s]}"),
                            on_text(icons.sin(s, font.pixelSize() * SIN_SIDE, ratio), font))
        picture = picture_side(font, small, lines)
        for f in events.outcomes(label.option):
            for gid, _ in f.gifts:
                g = gifts.book().get(gid) or {}
                doc.addResource(QTextDocument.ImageResource, QUrl(f"gift:{gid}"),
                                icons.game_gift(gid, g.get("keyword", "Keywordless"), picture, ratio,
                                                events.ROMAN.get(g.get("tier"), "")))
        doc.setTextWidth(width)
        doc.setHtml(full_html(label, font, small, picture) if full else brief_html(label, small))
        on_baseline(doc)
        return doc

    def cards(self):
        """Each label's brief card laid out on the overlay, top to bottom: (label, document, rect in overlay pixels).
        Every card on the page has its gifts' pictures one size, the biggest of PICTURE_LINES at which they all stay
        beside their options, and one width, as wide as the widest needs: right against the options, over as little
        of the story as it can."""
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        width = (CARD_RIGHT - CARD_LEFT) * sx
        items = sorted(self.items, key=lambda label: label.want)
        wants = [label.want for label in items]
        for lines in PICTURE_LINES:
            docs = [self.document(label, width - 2 * pad, lines) for label in items]
            card_w = min(width, max((doc.idealWidth() for doc in docs), default=0) + 2 * pad)
            for doc in docs:
                doc.setTextWidth(card_w - 2 * pad)
            heights = [(doc.size().height() + 2 * pad) / sy for doc in docs]
            tops = stack(wants, heights)
            if beside(wants, tops, heights):
                break
        return [(label, doc, QRectF(CARD_RIGHT * sx - card_w, top * sy, card_w, h * sy))
                for label, doc, top, h in zip(items, docs, tops, heights)]

    def opened_card(self, laid):
        """The card opened by a click, in full and the column's whole width, from its brief card's top down over the
        cards below, moved up as far as it must to stay in the cards' column (or, taller than that, in the game's
        picture): (label, document, rect in overlay pixels), or None."""
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        width = (CARD_RIGHT - CARD_LEFT) * sx
        for label, _, rect in laid:
            if label.option["text"] == self.opened:
                doc = self.document(label, width - 2 * pad, PICTURE_LINES[0], full=True)
                h = (doc.size().height() + 2 * pad) / sy
                lo, hi = (CARD_TOP, CARD_BOTTOM) if h <= CARD_BOTTOM - CARD_TOP else (EDGE, GAME_H - EDGE)
                top = max(lo, min(rect.top() / sy, hi - h))
                return label, doc, QRectF(CARD_LEFT * sx, top * sy, width, h * sy)
        return None

    def pointer(self, label, rect):
        """The y of a card's pointer to its option, in overlay pixels: the option's middle, kept off the corners."""
        sy = self.height() / GAME_H
        return min(max(label.want * sy, rect.top() + POINTER_END * sy), rect.bottom() - POINTER_END * sy)

    def set_mask(self):
        """Take clicks only where cards are drawn (with their pointers): every other click goes to the game. The
        event cards and the fuse box are the ones a click opens or closes (self.hits)."""
        if not self.showing() or self.width() <= 0:
            self.hits = []
            return
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        laid = self.cards()
        opened = self.opened_card(laid)
        shown = [(label, rect) for label, _, rect in laid] + ([opened[::2]] if opened else [])
        region = QRegion()
        for label, rect in shown:
            region = region.united(rect.toAlignedRect())
            y, half = self.pointer(label, rect), 2 * max(sy, 1)
            line = QRectF(rect.right(), y - half, (OPTION_FRAME - 3) * sx - rect.right(), 2 * half)
            region = region.united(line.toAlignedRect())
        for _, _, rect in self.trial_cards():
            region = region.united(rect.toAlignedRect())
        self.hits = [(label.option["text"], rect) for label, rect in reversed(shown)]
        if fused := self.fuse_card():
            region = region.united(fused[1].toAlignedRect())
            self.hits.append((self.fuse[0]["id"], fused[1]))
        self.setMask(region)

    def card_at(self, point):
        """The opened key (Overlay.opened) of the card under point (the open card first, as it lies on top), or
        None."""
        return next((text for text, rect in self.hits if rect.contains(point)), None)

    def mousePressEvent(self, e):
        """A click on a brief card opens it in full; on the open card, closes it; on another, opens that one."""
        key = self.card_at(e.position()) if e.button() == Qt.LeftButton else None
        if key is None:
            return
        self.opened = None if key == self.opened else key
        self.set_mask()
        self.update()

    def mouseMoveEvent(self, e):
        self.setCursor(Qt.PointingHandCursor if self.card_at(e.position()) else Qt.ArrowCursor)

    def plate(self, p, rect, edge, strong, alpha=245):
        """A card's plate: maalc's panel, its corners cut, framed in edge, the frame thicker when strong."""
        sy = self.height() / GAME_H
        fill = QColor(INK["panel"])
        fill.setAlpha(alpha)
        p.setPen(QPen(QColor(edge), (2.0 if strong else 1.0) * max(sy, 1)))
        p.setBrush(fill)
        p.drawPath(icons.chamfered(rect, CUT * sy))

    def draw_card(self, p, context, label, doc, rect, opened=False):
        """A card: its frame (amber for the recommended one, maalc's focus ink for the open one, else bronze), its
        pointer to the option, its text."""
        sx, sy = self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        amber = label.recommended
        p.setOpacity(1.0)
        self.plate(p, rect, INK["accent"] if amber else INK["fg"] if opened else INK["line-2"], amber or opened,
                   250 if opened else 245)
        y = self.pointer(label, rect)
        p.setPen(QPen(QColor(INK["accent"] if amber else INK["line-2"]), 2 * max(sy, 1)))
        p.drawLine(QPointF(rect.right(), y), QPointF((OPTION_FRAME - 3) * sx, y))
        p.save()
        p.setOpacity(0.5 if label.closed else 1.0)  # an answered option's card stays solid, its words faint
        p.translate(rect.left() + pad, rect.top() + pad)
        doc.documentLayout().draw(p, context)
        p.restore()

    def paintEvent(self, _):
        if not self.showing():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sy = self.height() / GAME_H
        pad = PAD_PX * sy
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.Text, QColor(INK["fg"]))
        laid = self.cards()
        opened = self.opened_card(laid)
        for label, doc, rect in laid:
            if opened is None or label is not opened[0]:
                self.draw_card(p, context, label, doc, rect)
        if opened:
            self.draw_card(p, context, *opened, opened=True)
        for w, doc, rect in self.trial_cards():
            self.plate(p, rect, INK["accent" if w.pick else "line-2"], w.pick)
            p.save()
            p.translate(rect.left() + pad, rect.top() + pad * 0.6)
            doc.documentLayout().draw(p, context)
            p.restore()
        if fused := self.fuse_card():
            doc, rect = fused
            opened = self.opened == self.fuse[0]["id"]
            self.plate(p, rect, INK["fg" if opened else "line-2"], opened, 250 if opened else 245)
            p.save()
            p.translate(rect.left() + pad, rect.top() + pad)
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
        star = on_text(icons.pixmap("star", INK["accent"], side, ratio), font)
        cards = []
        for worth in self.trials:
            rect = QRectF((worth.card.x + dx) * sx, y * sy, w * sx, h * sy)
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(font)
            doc.addResource(QTextDocument.ImageResource, QUrl("icon:star"), star)
            doc.setTextWidth(rect.width() - 2 * pad)
            doc.setHtml(trial_html(worth, small, rect.width() - 2 * pad))
            on_baseline(doc)
            cards.append((worth, doc, rect))
        return cards

    def fuse_card(self):
        """The fuse box laid out between FUSE_TOP and CARD_BOTTOM: (document, rect in overlay pixels), or None when
        there is none. Brief, it is left of the wheel, its middle at the centre slot's picture's if it can be; opened
        by a click, it runs out over the wheel from the brief box's top, moved up as far as it must to fit."""
        if self.fuse is None:
            return None
        (gift, box), sx, sy = self.fuse, self.width() / GAME_W, self.height() / GAME_H
        pad = PAD_PX * sy
        width = (FUSE_RIGHT - FUSE_LEFT) * sx
        doc = self.fuse_document(gift["id"], width - 2 * pad, FUSE_BRIEF * sy - 2 * pad, FUSE_SMALL[:1],
                                 "點一下看全文")
        h = doc.size().height() + 2 * pad
        top = min(max((box[1] + box[3] / 2) * sy - h / 2, FUSE_TOP * sy), CARD_BOTTOM * sy - h)
        if self.opened != gift["id"]:
            return doc, QRectF(FUSE_LEFT * sx, top, width, h)
        width = (FUSE_OPEN_RIGHT - FUSE_LEFT) * sx
        doc = self.fuse_document(gift["id"], width - 2 * pad, (CARD_BOTTOM - FUSE_TOP) * sy - 2 * pad, FUSE_SMALL,
                                 "全文見 LC Helper 視窗")
        h = doc.size().height() + 2 * pad
        return doc, QRectF(FUSE_LEFT * sx, max(FUSE_TOP * sy, min(top, CARD_BOTTOM * sy - h)), width, h)

    def fuse_document(self, gid, width, room, sizes, rest):
        """The fuse box's text width overlay pixels wide, no taller than room: its effect at the largest of sizes
        (px at 1280x720) that fits it whole, else at the last, cut to the most characters that fit, rest under it."""
        font, _ = self.fonts()
        sy = self.height() / GAME_H

        def laid(px, cut=None):
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(font)
            doc.setTextWidth(width)
            doc.setHtml(fuse_html(gid, max(8, round(px * sy)), cut, rest))
            return doc

        for px in sizes:
            if (doc := laid(px)).size().height() <= room:
                return doc
        lo, hi = 0, len(gift_effect(gid))
        while lo < hi:
            mid = (lo + hi + 1) // 2
            lo, hi = (mid, hi) if laid(sizes[-1], mid).size().height() <= room else (lo, mid - 1)
        return laid(sizes[-1], lo)
