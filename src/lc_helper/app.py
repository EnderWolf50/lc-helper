"""The floating window: the auto battle bar on top, the Mirror Dungeon event and gift sections under it, and the
settings on a page of their own behind the gear.

Settings (device, pick, guard, keywords, hotkeys, text size, pin, open sections, window position) live in
.local/settings.json beside the repository.
"""

import ctypes
import html
import os
import json
import sys
from ctypes import wintypes
from functools import partial
from math import ceil
from string import Template

from PySide6.QtCore import (QAbstractNativeEventFilter, QEvent, QModelIndex, QObject, QPoint, QRect, QSize, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QFontMetricsF, QIcon, QKeySequence, QPainter, QPixmap,
                           QStandardItem, QStandardItemModel, QTextDocument)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QKeySequenceEdit, QLabel, QLayout,
                               QLineEdit, QListWidget, QMenu, QProxyStyle, QPushButton, QSizePolicy, QSpinBox, QStyle,
                               QSystemTrayIcon, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import device as devices
from .paths import LOCAL
from . import events, fights, gifts, icons, recommend
from .overlay import Overlay, labels
from .battle import FOREVER, Phase, Pick, Plan, Status
from .worker import Callbacks, Worker

SETTINGS = LOCAL / "settings.json"
# guard_mode: its name in the guard list, and the Plan.guard it gives for guard turns.
GUARD_MODES = {"none": ("不防禦", lambda turns: 0), "turns": ("防禦前幾回合", lambda turns: turns),
               "forever": ("全程防禦", lambda turns: FOREVER)}
SECTIONS = {"event": "鏡牢事件", "gift": "飾品"}  # the main page's folding sections: key, title
DEFAULTS = {"address": None, "pc_input": devices.PC_INPUT, "pick": "win_rate", "guard_mode": "none", "guard": 1,
            "hold": True, "watch": False, "skip": False, "overlay": True, "keywords": [], "stop_after_victory": False,
            "notify": True, "open_sections": ["event"], "text_size": "normal", "pin": True, "pos": None,
            "hotkeys": {"battle": "F8", "read": "F9"}}
PICK_TEXT = {Pick.WIN_RATE: "勝率", Pick.DAMAGE: "傷害"}
PICK_TIPS = {Pick.WIN_RATE: "每回合按遊戲的 Win Rate（勝率）", Pick.DAMAGE: "每回合按遊戲的 Damage（傷害）"}
TEXT_SIZES = {"small": ("小", 10.5), "normal": ("標準", 12), "large": ("大", 13.5)}  # text_size: its name, points
PC_INPUT_NAMES = {"touch": "觸控", "window": "移視窗", "cursor": "借游標", "seize": "前景"}  # devices.PC_INPUTS, short
# The title bar's name for a device that is not connected, by the worker's device state.
DEVICE_STATES = {"idle": "未連線", "connecting": "連線中", "error": "連線失敗"}
REFERENCE_PT = 10  # the window's pixel sizes were set for text of this size
PANE_LINES = 3  # the detail pane's least height in lines of text, which is also its height with nothing to show
SCREEN_GAP = 8  # px kept free between the window's bottom and the screen's
# pin: window flags, the pin button's icon and tooltip. A Qt.Tool window has no taskbar entry, so the unpinned window
# is a normal one: when it falls behind the game, the taskbar and Alt+Tab still find it.
PIN = {True: (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool, "pin",
              "置頂中：點一下取消置頂，視窗改成一般視窗，被蓋住時從工作列或 Alt+Tab 叫回"),
       False: (Qt.FramelessWindowHint | Qt.Window, "unpinned", "沒有置頂：點一下讓視窗固定在最上層")}
# The settings whose value must be one of a set (load_settings): the keys of each table, or the listed values.
SETTING_CHOICES = {"text_size": TEXT_SIZES, "pc_input": devices.PC_INPUTS, "pin": PIN, "guard_mode": GUARD_MODES,
                   "guard": range(1, 100)}
MAX_KEYWORDS = 4  # the chips that fit on one row at every text size
# The settings that are a list of distinct values from a set, in the user's order: the set, and how many at most.
LIST_CHOICES = {"keywords": (recommend.CHOICES, MAX_KEYWORDS), "open_sections": (list(SECTIONS), len(SECTIONS))}
ICON, ICON_ON, HEAD_ICON = "#b9ab93", "#e7b45a", "#c9a165"
# The detail pane's icons, set in its text as images: <img src='icon:NAME'>, in these colours.
PANE_ICONS = {"star": "#f0c674", "bullet": "#eadcc4"}
DOT = {"idle": "#6b6152", "connecting": "#e7b45a", "connected": "#6cc070", "error": "#d9534f"}
EVENT_PLACEHOLDER = "<p style='color:#8f8270'>在事件的選項頁按「讀取畫面」，或輸入記得的幾個字查詢。</p>"
GIFT_PLACEHOLDER = "<p style='color:#8f8270'>在選飾品或獲得飾品的畫面按「讀取畫面」，或輸入飾品名字查詢。</p>"

STYLE = Template("""
QWidget#root { background: #17130f; border: 1px solid #5b4527; border-radius: 10px; }
QWidget { color: #eadcc4; font-family: "Microsoft JhengHei UI", "Segoe UI"; font-size: ${body}pt; }
QFrame#header { background: #231b13; border-top-left-radius: 10px; border-top-right-radius: 10px;
                border-bottom: 1px solid #5b4527; }
QLabel#title { color: #e7b45a; font-size: ${big}pt; font-weight: bold; letter-spacing: 1px; }
QLabel#device { color: #b9ab93; font-size: ${small}pt; }
QLabel#section { color: #c9a165; font-size: ${small}pt; font-weight: bold; }
QLabel#status { color: #b9ab93; font-size: ${small}pt; }
QPushButton, QToolButton { background: #2c2219; border: 1px solid #5b4527; border-radius: 6px; padding: 0 10px; }
QPushButton:hover, QToolButton:hover { background: #3a2c1f; }
QPushButton:checked { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; }
QPushButton:disabled { background: #1d1711; border-color: #3e2f1d; color: #6b6152; }
QPushButton#seg { background: #1d1711; color: #b9ab93; border-radius: 0; }
QPushButton#seg:hover { background: #2c2219; }
QPushButton#seg:checked { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; }
QPushButton#seg[end="first"] { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
QPushButton#seg[end="last"] { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QPushButton#start { background: #2f6b3a; border-color: #6fae6a; color: #fff; font-size: ${big}pt; font-weight: bold; }
QPushButton#start:hover { background: #377a43; }
QPushButton#start[running="true"] { background: #9e2b22; border-color: #d65a45; }
QPushButton#start[running="true"]:hover { background: #b8352a; }
QPushButton#read { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; font-weight: bold; }
QPushButton#read:hover { background: #7d5725; }
QListView#hits { background: #1d1711; border: 1px solid #5b4527; outline: none; }
QListView#hits::item { padding: 4px 6px; } QListView#hits::item:selected { background: #4a3417; color: #fff3dc; }
QListView#hits::item:disabled { color: #a99c86; }
QPushButton#link { background: transparent; border: none; color: #e7b45a; padding: 0; text-align: left;
                   text-decoration: underline; }
QPushButton#link:hover { color: #f0c674; }
QPushButton#sectionHead { background: #231b13; border: none; border-top: 1px solid #3e2f1d; border-radius: 0;
                          padding: 0; }
QPushButton#sectionHead:hover { background: #2c2219; }
QLabel#sectionTitle { color: #c9a165; font-weight: bold; }
QLabel#summary { color: #b9ab93; font-size: ${small}pt; }
QToolButton#flat, QToolButton#gear { background: transparent; border: none; padding: 4px 3px; }
QToolButton#flat:hover, QToolButton#gear:hover, QToolButton#gear:checked { background: #3a2c1f; }
QSpinBox, QLineEdit, QComboBox { background: #0f0c09; border: 1px solid #5b4527; border-radius: 6px; padding: 0 6px; }
QSpinBox::up-button, QSpinBox::down-button { width: ${arrow}px; }
QLineEdit { placeholder-text-color: #8f8270; }
QComboBox QAbstractItemView { background: #1d1711; selection-background-color: #6b4a1f; }
QListWidget { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; }
QListWidget::item { padding: 4px; } QListWidget::item:selected { background: #4a3417; }
QTextBrowser { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; padding: 4px; }
QPushButton#pill { background: transparent; color: #b9ab93; border-radius: ${pill}px; padding: 0 12px; }
QPushButton#pill:hover { background: #3a2c1f; }
QPushButton#pill:checked { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; }
QToolButton#chip { border-radius: ${chip}px; padding: 2px 10px; }
QToolButton#chip:hover { border-color: #e7b45a; }
QToolButton#chipAdd { background: transparent; color: #b9ab93; border: 1px dashed #5b4527; border-radius: ${chip}px;
                      padding: 2px 10px; }
QToolButton#chipAdd:hover { background: #3a2c1f; color: #eadcc4; }
QToolButton#chip::menu-indicator, QToolButton#chipAdd::menu-indicator { image: none; width: 0; }
QMenu { background: #1d1711; border: 1px solid #5b4527; padding: 4px 0; }
QMenu::item { padding: 4px 16px; } QMenu::item:selected { background: #4a3417; }
QMenu::item:disabled { color: #6b6152; }
QDialog { background: #17130f; }
QToolTip { color: #eadcc4; background: #231b13; border: 1px solid #5b4527; padding: 4px 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px 1px 2px 0; }
QScrollBar::handle:vertical { background: #4a3a26; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #6b4a1f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QKeySequenceEdit QLineEdit { min-width: 140px; }
""")


def control_height(line):
    """The height every button, field and list shares on a row, for text line pixels high: the line, 5 px padding and
    a 1 px border on each side."""
    return line + 12


def style(base, line):
    """The style sheet for body text of base points and line pixels: secondary text a step smaller, the title and START
    a step bigger. A pill's ends are round with half its height: Qt draws square corners for a radius over that."""
    return STYLE.substitute(body=base, small=base - 1.5, big=base + 1.5, pill=control_height(line) // 2,
                            arrow=control_height(line) // 2, chip=(line + 6) // 2)


def scaled(px, base):
    """A pixel size set for REFERENCE_PT text, for text of base points."""
    return round(px * base / REFERENCE_PT)


def pane_heights(contents, preferred, room, floor):
    """The detail panes' heights for texts contents px tall: each all of its text up to preferred, the rest
    scrolling, and together no more than the room left on the screen under them, the tallest giving way first.
    Never under floor, even in a window placed so low that it then runs off the screen: the user placed it, so it is
    not moved."""
    wants = [max(floor, min(content, preferred)) for content in contents]
    cap, taken = max(wants, default=0), 0
    for i, want in enumerate(sorted(wants)):
        share = (room - taken) // (len(wants) - i)  # what each pane still to place gets of the room left
        if share < want:
            cap = share
            break
        taken += want
    return [max(floor, min(want, cap)) for want in wants]


def migrate(saved):
    """Settings an older lc-helper wrote, in today's keys: its guard turns and 無限防禦 as a guard mode, its one main
    keyword as a list of one, its folded window as every section folded."""
    saved = dict(saved)
    forever, keyword, compact = (saved.pop(k, None) for k in ("forever", "keyword", "compact"))
    guard = saved.get("guard")
    if "guard_mode" not in saved:
        saved["guard_mode"] = "forever" if forever else "turns" if isinstance(guard, int) and guard > 0 else "none"
    if "keywords" not in saved and keyword is not None:
        saved["keywords"] = [keyword]
    if "open_sections" not in saved and compact:
        saved["open_sections"] = []
    return saved


def load_settings():
    """The saved settings over the defaults. The file is the user's to edit and another lc-helper version may have
    written it, so a value outside its allowed choices falls back to the default instead of failing the window."""
    try:
        saved = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    settings = DEFAULTS | migrate(saved if isinstance(saved, dict) else {})
    for key, allowed in SETTING_CHOICES.items():
        if settings[key] not in allowed:
            settings[key] = DEFAULTS[key]
    for key, (allowed, most) in LIST_CHOICES.items():
        value = settings[key]
        settings[key] = list(dict.fromkeys(v for v in value if v in allowed))[:most] if isinstance(value, list) \
            else DEFAULTS[key]
    return settings


def save_settings(settings):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def logo():
    """The app's icon, on the taskbar entry of the unpinned window and on the notifications."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(2, 2)
    painter.setBrush(QColor("#9e2b22"))
    painter.setPen(QColor("#e7b45a"))
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pix)


def guard_text(guard):
    return "全程防禦" if guard == FOREVER else f"防禦剩 {guard} 回合" if guard else ""


def status_text(status: Status):
    parts = [status.phase.value]
    if status.phase is not Phase.STOPPED and (g := guard_text(status.plan.guard)):
        parts.append(g)
    elif status.phase is not Phase.STOPPED:
        parts.append(PICK_TEXT[status.plan.pick])
    if status.turns:
        parts.append(f"已打 {status.turns} 回合")
    text = " · ".join(parts)
    return f"{text}\n{status.note}" if status.note else text


def event_html(event, read_text="", pick=None):
    """An event and what each option does, as the detail pane shows it; pick (option, why) gets a star."""
    if event is None:
        shown = html.escape(read_text.strip()[:200]) or "（沒讀到文字，確認畫面停在事件的選項頁）"
        return f"<p style='color:#d9a441'>沒對到事件</p><p style='color:#8f8270'>讀到：{shown}</p>"
    story = event["story_zh"] or event["story"]
    tail = "<br>".join(html.escape(s) for s in story.strip().splitlines()[-3:] if s.strip())
    rows = [f"<p style='color:#8f8270;margin:0'>事件 {event['id']}{'（後續頁）' if event['page'] else ''}</p>",
            f"<p style='color:#cbbd9f;margin:2px 0 6px 0'>{tail}</p>"]
    for i, o in enumerate(event["options"], 1):
        if not (o["text"] or o["text_zh"]):
            continue
        picked = pick is not None and o is pick[0]
        title = ("<img src='icon:star'> " if picked else "") + html.escape(o["text_zh"] or o["text"])
        en = html.escape(o["text"]) if o["text_zh"] else ""
        rows.append(f"<p style='margin:6px 0 0 0'><b style='color:#e7b45a'>{i}. {title}</b> "
                    f"<span style='color:#8f8270'>{en}</span> "
                    f"<span style='background:#3a2c1f;color:#d8c7a6'>&nbsp;{events.kind_text(o)}&nbsp;</span></p>")
        if picked:
            rows.append(f"<p style='color:#f0c674;margin:0 0 0 14px'>推薦：{html.escape(pick[1])}</p>")
        hint = o["hint_zh"] or o["hint"]
        if hint:
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>{html.escape(hint)}</p>")
        for e in events.effects(o):
            what = html.escape(e.what).replace("「", "<span style='color:#f0c674'>「").replace("」", "」</span>")
            rows.append(f"<p style='margin:0 0 0 14px'><img src='icon:bullet'> "
                        f"<span style='color:#9fc1d9'>{html.escape(e.when)}</span>"
                        f"：{what}</p>")
    return "".join(rows)


def gift_html(gift_list, heading=""):
    """Gifts and their effects, as the detail pane shows them: Chinese first, English under it."""
    rows = [f"<p style='color:#8f8270;margin:0'>{html.escape(heading)}</p>"] if heading else []
    names = gifts.book()
    for g in gift_list:
        rows.append(f"<p style='margin:6px 0 0 0'><b style='color:#e7b45a'>{html.escape(gifts.label(g))}</b> "
                    f"<span style='color:#8f8270'>{html.escape(g['en'])}</span></p>")
        if g["desc_zh"]:
            rows.append(f"<p style='color:#eadcc4;margin:0 0 0 14px'>{html.escape(g['desc_zh']).replace(chr(10), '<br>')}</p>")
        elif g["desc_en"]:
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>{html.escape(g['desc_en']).replace(chr(10), '<br>')}</p>")
        plus = g["plus_zh"] or g["plus_en"]
        if plus:
            rows.append(f"<p style='color:#9fc1d9;margin:2px 0 0 14px'>強化後：{html.escape(plus).replace(chr(10), '<br>')}</p>")
        for ids in (g.get("recipe") or {}).get("recipes", []):
            parts = " ＋ ".join(html.escape((names.get(i) or {}).get("zh") or str(i)) for i in ids)
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>融合：{parts}</p>")
        for group in (g.get("recipe") or {}).get("groups", []):
            parts = "、".join(html.escape((names.get(i) or {}).get("zh") or str(i)) for i in group["ids"])
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>融合：以下任 {group['need']} 個：{parts}</p>")
    return "".join(rows)


def result_text(event):
    story = (event["story_zh"] or event["story"] or " / ".join(o["text_zh"] or o["text"] for o in event["options"]))
    first = " ".join(story.split())[:38]
    return f"{first}…" if len(story) > 38 else first


class Bridge(QObject):
    """Callbacks from the worker thread, delivered on the window's thread."""

    device = Signal(str, str)
    targets = Signal(list)
    battle = Signal(object)
    event = Signal(object)
    page_left = Signal()
    fight = Signal(object, str)
    skip = Signal(str)
    gifts = Signal(object)
    error = Signal(str)

    def callbacks(self):
        return Callbacks(device=self.device.emit, targets=self.targets.emit, battle=self.battle.emit,
                         event=self.event.emit, page_left=self.page_left.emit, fight=self.fight.emit, skip=self.skip.emit,
                         gifts=self.gifts.emit,                         error=self.error.emit)


WM_HOTKEY, MOD_NOREPEAT = 0x0312, 0x4000
# Qt's portable key names (QKeySequence.toString) to Windows virtual-key codes and RegisterHotKey modifiers.
VK = ({f"F{i}": 0x6F + i for i in range(1, 25)} | {c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}
      | {"SPACE": 0x20, "PGUP": 0x21, "PGDOWN": 0x22, "END": 0x23, "HOME": 0x24, "LEFT": 0x25, "UP": 0x26,
         "RIGHT": 0x27, "DOWN": 0x28, "INS": 0x2D, "DEL": 0x2E, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
         "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC,
         ".": 0xBE, "/": 0xBF})
MODS = {"ALT": 0x1, "CTRL": 0x2, "SHIFT": 0x4, "META": 0x8}
HOTKEY_IDS = {"battle": 1, "read": 2}  # tools/launch_check.py posts WM_HOTKEY with these ids


def parse_hotkey(text):
    """(modifiers, virtual key) of a hotkey such as "F8" or "Ctrl+Shift+Q", or None when it is not one key."""
    *mods, key = [p.strip().upper() for p in (text or "").split("+")]
    if key not in VK or any(m not in MODS for m in mods):
        return None
    flags = 0
    for m in mods:
        flags |= MODS[m]
    return flags, VK[key]


class Hotkeys(QAbstractNativeEventFilter):
    """Global hotkeys (RegisterHotKey): they work while the emulator has the focus."""

    def __init__(self):
        super().__init__()
        self.actions = {}

    def add(self, hid, text, action):
        """Register text under id hid: whether Windows gave it (another program may hold it)."""
        parsed = parse_hotkey(text)
        if parsed is None or not ctypes.windll.user32.RegisterHotKey(None, hid, parsed[0] | MOD_NOREPEAT, parsed[1]):
            return False
        self.actions[hid] = action
        return True

    def clear(self):
        for hid in self.actions:
            ctypes.windll.user32.UnregisterHotKey(None, hid)
        self.actions = {}

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self.actions:
                QTimer.singleShot(0, self.actions[msg.wParam])
                return True, 0
        return False, 0


class HotkeyDialog(QDialog):
    """Press a key (with Ctrl, Alt or Shift if wanted) for each action; OK only when both are distinct hotkeys."""

    NAMES = {"battle": "開始／停止自動戰鬥", "read": "讀取畫面上的事件"}

    def __init__(self, keys, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("熱鍵設定")
        form = QFormLayout(self)
        self.edits = {}
        for name, label in self.NAMES.items():
            edit = QKeySequenceEdit(QKeySequence(keys[name]))
            edit.setMaximumSequenceLength(1)
            edit.keySequenceChanged.connect(self.check)
            form.addRow(label, edit)
            self.edits[name] = edit
        self.problem = QLabel(objectName="status")
        form.addRow(self.problem)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.check()

    def keys(self):
        return {name: edit.keySequence().toString(QKeySequence.PortableText) for name, edit in self.edits.items()}

    def check(self, *_):
        keys = self.keys()
        bad = [self.NAMES[n] for n, k in keys.items() if parse_hotkey(k) is None]
        problem = (f"{'、'.join(bad)}：請按一個按鍵（F1～F24、字母、數字，可加 Ctrl／Alt／Shift）" if bad
                   else "兩個動作不能用同一個熱鍵" if len(set(keys.values())) < len(keys) else "")
        self.problem.setText(problem)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)


class FightLog(QDialog):
    """The battles the auto battle played to their end, newest first, with a one-line summary."""

    def __init__(self, parent=None, path=None):
        super().__init__(parent, Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("戰鬥紀錄")
        lay = QVBoxLayout(self)
        rows = fights.load(path)
        self.summary = QLabel(fights.summary(rows), objectName="status")
        lay.addWidget(self.summary)
        self.rows = QListWidget()
        self.rows.addItems([fights.row_text(r) for r in rows])
        self.rows.setMinimumSize(320, 260)
        lay.addWidget(self.rows)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)


def device_choice(target):
    """A device as the device list names it: MuMu 0（16384）, or PC 版."""
    return target.label if target.address == devices.PC else f"{target.label}（{target.address.rsplit(':', 1)[-1]}）"


def event_summary(settings):
    """The folded event section's head: what it does on its own, and the keywords it recommends for."""
    parts = [text for key, text in (("watch", "自動讀取開"), ("skip", "跳過劇情開")) if settings[key]]
    if settings["keywords"]:
        parts.append("推薦 " + " › ".join(events.KEYWORDS[k] for k in settings["keywords"]))
    return " · ".join(parts)


class Segmented(QWidget):
    """Buttons side by side of which one is on, as 勝率|傷害. chosen(key) is emitted on the user's pick."""

    chosen = Signal(str)

    def __init__(self, choices, current, name):
        """choices: {key: (text, tooltip)}."""
        super().__init__(accessibleName=name)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        group = QButtonGroup(self)
        self.buttons = {}
        for i, (key, (text, tip)) in enumerate(choices.items()):
            button = QPushButton(text, objectName="seg", checkable=True, toolTip=tip)
            button.setProperty("key", key)
            button.setProperty("end", "first" if i == 0 else "last" if i == len(choices) - 1 else "")
            group.addButton(button)
            row.addWidget(button, 1)
            self.buttons[key] = button
        self.show_choice(current)
        group.buttonClicked.connect(lambda button: self.chosen.emit(button.property("key")))

    def show_choice(self, key):
        self.buttons[key].setChecked(True)


class Elided(QLabel):
    """One line of text that ends in … where it does not fit."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def paintEvent(self, e):
        rect = self.contentsRect()
        shown = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        self.style().drawItemText(QPainter(self), rect, self.alignment(), self.palette(), self.isEnabled(), shown,
                                  self.foregroundRole())


class SearchBox(QWidget):
    """A search field with its clear button and 查詢; the hits drop down from it in a list that closes on a pick.

    find(query) gives the hits, [(row text, found)], and missing is the row shown for none. picked(found) is emitted
    on the user's pick, cleared once the field is emptied, by its clear button or by hand."""

    picked = Signal(object)
    cleared = Signal()

    def __init__(self, placeholder, missing, find):
        super().__init__()
        self.find, self.missing, self.found = find, missing, []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.field = QLineEdit(placeholderText=placeholder, clearButtonEnabled=True)
        self.go = QPushButton("查詢", clicked=self.search)
        row.addWidget(self.field, 1)
        row.addWidget(self.go)
        self.hits = QStandardItemModel(self)
        # Set on the field with setWidget, not setCompleter: a pick leaves the user's words in the field.
        self.list = QCompleter(self.hits, self, completionMode=QCompleter.UnfilteredPopupCompletion,
                               maxVisibleItems=8)
        self.list.setWidget(self.field)
        self.list.popup().setObjectName("hits")
        self.list.popup().setTextElideMode(Qt.ElideRight)
        self.list.activated[QModelIndex].connect(lambda index: self.picked.emit(self.found[index.row()]))
        self.typing = QTimer(self, singleShot=True, interval=150, timeout=self.search)
        self.field.textChanged.connect(self.typed)
        # The open list hands Return to the field before it picks the lit row: searching then would refill the list
        # under that pick (a crash), so Return searches only while the list is closed.
        self.field.returnPressed.connect(lambda: self.list.popup().isVisible() or self.search())

    def typed(self, text):
        if text.strip():
            self.typing.start()
        else:
            self.typing.stop()
            self.list.popup().hide()
            self.cleared.emit()

    def search(self):
        """The hits for the field's words, dropped down under the field and 查詢, the first one lit for Enter."""
        self.typing.stop()
        query = self.field.text().strip()
        if not query:
            return
        hits = self.find(query) if len(query) >= 2 else []
        self.found = [found for _, found in hits]
        self.hits.clear()
        for text, _ in hits:
            self.hits.appendRow(QStandardItem(text))
        if not hits:
            row = QStandardItem(self.missing if len(query) >= 2 else "至少輸入兩個字")
            row.setFlags(Qt.NoItemFlags)
            self.hits.appendRow(row)
        self.list.complete(QRect(0, 0, self.width(), self.field.height()))
        if hits:
            self.list.popup().setCurrentIndex(self.hits.index(0, 0))


class Section(QWidget):
    """A part of the main page under a head that folds it away; folded, the head sums up what the part holds."""

    def __init__(self, title, opened):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.head = QPushButton(objectName="sectionHead", checkable=True, checked=opened, accessibleName=title)
        row = QHBoxLayout(self.head)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)
        self.arrow = QLabel()
        self.summary = Elided(objectName="summary")
        for part in (self.arrow, QLabel(title, objectName="sectionTitle"), self.summary):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            row.addWidget(part)
        row.setStretch(2, 1)
        lay.addWidget(self.head)
        self.body = QWidget()
        lay.addWidget(self.body)
        self.summed_up = ""
        self.head.toggled.connect(self.show_open)
        self.show_open(opened)

    def show_open(self, on):
        """The body, or the summary in the head. The summary label stays, empty, to keep the title at the left."""
        self.body.setVisible(on)
        self.summary.setText("" if on else self.summed_up)
        self.head.setToolTip("" if on else self.summed_up)

    def set_summary(self, text):
        self.summed_up = text
        self.show_open(self.head.isChecked())


class Look(QProxyStyle):
    """The platform's style, with the check boxes and the arrows of the lists and the spin box drawn like the window's
    icons; a check box is as tall as most of a line."""

    def drawPrimitive(self, element, option, painter, widget=None):
        rect = option.rect
        if element == QStyle.PE_IndicatorCheckBox:
            on = bool(option.state & QStyle.State_On)
            (name, color), side = ("checked", ICON_ON) if on else ("box", ICON), min(rect.width(), rect.height())
        elif widget is not None and (element in (QStyle.PE_IndicatorSpinUp, QStyle.PE_IndicatorSpinDown) or (
                element == QStyle.PE_IndicatorArrowDown and isinstance(widget, QComboBox))):
            # Qt's arrow box is a few pixels across: the chevron is sized to the text and centred on it.
            name, color = "up" if element == QStyle.PE_IndicatorSpinUp else "unfolded", ICON
            side = round(widget.fontMetrics().height() * 0.75)
        else:
            return super().drawPrimitive(element, option, painter, widget)
        painter.drawPixmap(rect.x() + (rect.width() - side) // 2, rect.y() + (rect.height() - side) // 2,
                           icons.pixmap(name, color, side, painter.device().devicePixelRatioF()))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PM_IndicatorWidth, QStyle.PM_IndicatorHeight) and widget is not None:
            return round(widget.fontMetrics().height() * 0.85)
        return super().pixelMetric(metric, option, widget)


class Window(QWidget):
    def __init__(self, worker_factory=Worker, hotkeys=None):
        settings = load_settings()
        super().__init__(None, PIN[settings["pin"]][0])
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("LC Helper")
        self.setWindowIcon(logo())
        app = QApplication.instance()
        if not app.property("look"):  # setStyle repolishes every widget: once per application
            app.setStyle(Look())
            app.setProperty("look", True)
        self.settings = settings
        self.hotkeys = hotkeys if hotkeys is not None else Hotkeys()
        self.hotkeys_taken = []
        self.overlay = Overlay()
        self.tray = None
        self.last_reading = None  # the event page last read, ranked again on new keywords
        self.shown_event = None
        self.running = False
        self.drag_from: QPoint | None = None
        self.controls = []  # the buttons, fields and lists that share one height on a row (apply_text_size)
        self.row_labels = []  # the labels before a row on the settings page, as wide as the widest
        self.fit_timer = QTimer(self, singleShot=True, interval=0, timeout=self.fit_panes)
        self.bridge = Bridge()
        self.worker = worker_factory(self.bridge.callbacks())
        self.build()
        self.bridge.device.connect(self.on_device)
        self.bridge.targets.connect(self.on_targets)
        self.bridge.battle.connect(self.on_battle)
        self.bridge.event.connect(self.on_event)
        self.bridge.page_left.connect(lambda: self.overlay.hide_labels())
        self.bridge.fight.connect(self.on_fight)
        self.bridge.gifts.connect(self.on_gifts)
        self.bridge.skip.connect(lambda what: self.say_skip(f"自動跳過：{what}"))
        self.bridge.error.connect(self.say)

    def control(self, widget):
        """widget, as tall as every other control on a row."""
        self.controls.append(widget)
        return widget

    def build(self):
        self.root = root = QWidget(self, objectName="root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SetFixedSize)  # the window is as tall as what it shows
        outer.addWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        lay.addWidget(self.build_header())
        self.main_page = QWidget()
        main = QVBoxLayout(self.main_page)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self.build_battle())
        self.sections = {"event": self.build_events(), "gift": self.build_gifts()}
        for key, section in self.sections.items():
            section.head.toggled.connect(partial(self.set_section_open, key))
            main.addWidget(section)
        lay.addWidget(self.main_page)
        self.settings_page = self.build_settings()
        self.settings_page.hide()
        lay.addWidget(self.settings_page)
        self.show_event_summary()
        self.apply_text_size()
        self.apply_hotkey_labels()
        self.update_start()
        if self.settings["pos"]:
            self.move(*self.settings["pos"])

    def build_header(self):
        """The title bar: the name, the device and whether it is connected, the settings, the pin and the close."""
        self.header = header = QFrame(objectName="header")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 6, 6, 6)
        h.setSpacing(0)
        h.addWidget(QLabel("LC Helper", objectName="title"))
        h.addStretch(1)
        self.dot = QLabel(objectName="dot", accessibleName="連線狀態")
        self.dot.setProperty("state", "idle")
        h.addWidget(self.dot)
        h.addSpacing(6)
        self.device_name = QLabel(DEVICE_STATES["idle"], objectName="device")
        h.addWidget(self.device_name)
        h.addSpacing(8)
        for part in (self.dot, self.device_name):
            part.setToolTip("還沒連線：第一次開始戰鬥或讀取事件時才連")
        self.gear = QToolButton(objectName="gear", checkable=True, accessibleName="設定", toolTip="設定")
        self.gear.toggled.connect(self.show_settings)
        self.pin = QToolButton(objectName="flat", checkable=True, checked=self.settings["pin"], accessibleName="置頂")
        self.pin.toggled.connect(self.set_pin)
        self.close_button = QToolButton(objectName="flat", accessibleName="關閉", toolTip="關閉 LC Helper",
                                        clicked=self.close)
        for button in (self.gear, self.pin, self.close_button):
            h.addWidget(button)
        return header

    def build_battle(self):
        """The auto battle bar, always on the main page: the skill pick, the guard, START and a status line."""
        s = self.settings
        bar = QWidget()
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.picks = Segmented({p.value: (PICK_TEXT[p], PICK_TIPS[p]) for p in Pick}, s["pick"], "選技能")
        self.picks.chosen.connect(self.set_pick)
        self.controls += self.picks.buttons.values()
        row.addWidget(self.picks, 5)
        self.guard_box = self.control(QComboBox(accessibleName="防禦"))
        for mode, (name, _) in GUARD_MODES.items():
            self.guard_box.addItem(name, mode)
        self.guard_box.setCurrentIndex(self.guard_box.findData(s["guard_mode"]))
        self.guard_box.activated.connect(self.set_guard_mode)
        row.addWidget(self.guard_box, 6)
        self.guard_spin = self.control(QSpinBox(minimum=1, maximum=99, value=s["guard"], suffix=" 回合",
                                                accessibleName="防禦回合數"))
        self.guard_spin.valueChanged.connect(self.set_guard_turns)
        self.guard_spin.setVisible(s["guard_mode"] == "turns")
        row.addWidget(self.guard_spin)
        lay.addLayout(row)
        self.start = QPushButton(objectName="start", clicked=self.toggle_battle)
        lay.addWidget(self.start)
        self.status = QLabel(objectName="status", wordWrap=True, visible=False)
        lay.addWidget(self.status)
        return bar

    def build_events(self):
        """The Mirror Dungeon event section: read the screen, search the events, the pane, the recommendation and
        the helpers that act on the game."""
        s = self.settings
        section = Section(SECTIONS["event"], "event" in s["open_sections"])
        ev = QVBoxLayout(section.body)
        ev.setContentsMargins(12, 10, 12, 12)
        ev.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.read_button = self.control(QPushButton(objectName="read", clicked=lambda: self.worker.send("read_event")))
        row.addWidget(self.read_button, 1)
        self.watch = self.control(QPushButton("自動", objectName="pill", checkable=True, checked=s["watch"],
                                              toolTip="自動讀取：畫面出現事件選項或飾品畫面就讀取顯示"))
        self.watch.toggled.connect(self.set_watch)
        row.addWidget(self.watch)
        ev.addLayout(row)
        self.event_search = SearchBox("搜尋事件文字（中/英）", "找不到符合的事件",
                                      lambda query: [(result_text(e), e) for e in events.search(query, limit=8)])
        self.event_search.picked.connect(self.show_found_event)
        self.event_search.cleared.connect(self.clear_event)
        self.controls += [self.event_search.field, self.event_search.go]
        ev.addWidget(self.event_search)
        self.detail = QTextBrowser(openExternalLinks=False)
        self.detail.document().documentLayout().documentSizeChanged.connect(lambda _: self.fit_timer.start())
        self.detail.setHtml(EVENT_PLACEHOLDER)
        ev.addWidget(self.detail)
        ev.addWidget(QLabel("推薦體系（依順序）", objectName="section"))
        self.keyword_row = QHBoxLayout()
        self.keyword_row.setSpacing(6)
        ev.addLayout(self.keyword_row)
        self.show_keywords()
        ev.addWidget(QLabel("輔助", objectName="section"))
        row = QHBoxLayout()
        row.setSpacing(6)
        self.skip_box = self.control(QPushButton("跳過劇情", objectName="pill", checkable=True, checked=s["skip"],
                                                 toolTip="自動跳過劇情：一路推進到選項頁（不替你選）"))
        self.skip_box.toggled.connect(self.set_skip)
        row.addWidget(self.skip_box)
        self.overlay_box = self.control(QPushButton("疊加顯示", objectName="pill", checkable=True,
                                                    checked=s["overlay"], toolTip="疊加顯示：把選項效果直接標在遊戲畫面上"))
        self.overlay_box.toggled.connect(self.set_overlay)
        row.addWidget(self.overlay_box)
        row.addStretch()
        ev.addLayout(row)
        self.skip_state = QLabel(objectName="status", visible=False)
        ev.addWidget(self.skip_state)
        return section

    def build_gifts(self):
        """The gift section: search the gifts, and the pane that also shows the gifts a gift screen read finds."""
        section = Section(SECTIONS["gift"], "gift" in self.settings["open_sections"])
        lay = QVBoxLayout(section.body)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        self.gift_search = SearchBox("搜尋飾品名字（中/英）", "找不到符合的飾品",
                                     lambda query: [(f"{gifts.label(g)}  {g['en']}", g)
                                                    for g in gifts.search(query, limit=8)])
        self.gift_search.picked.connect(lambda gift: self.show_gifts([gift]))
        self.gift_search.cleared.connect(self.clear_gifts)
        self.controls += [self.gift_search.field, self.gift_search.go]
        lay.addWidget(self.gift_search)
        self.gift_detail = QTextBrowser(openExternalLinks=False)
        self.gift_detail.document().documentLayout().documentSizeChanged.connect(lambda _: self.fit_timer.start())
        self.gift_detail.setHtml(GIFT_PLACEHOLDER)
        lay.addWidget(self.gift_detail)
        return section

    def build_settings(self):
        """The settings page the gear shows in place of the main page, in groups."""
        s = self.settings
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        def group(title):
            if lay.count():
                lay.addSpacing(6)
            lay.addWidget(QLabel(title, objectName="section"))

        group("戰鬥")
        for key, text, toggled in (
                ("hold", "回合播放時按住畫面（加快 E.G.O 動畫）", self.set_hold),
                ("stop_after_victory", "勝利後停止自動戰鬥", partial(self.set_flag, "stop_after_victory")),
                ("notify", "戰鬥結束時跳出 Windows 通知", partial(self.set_flag, "notify"))):
            box = QCheckBox(text, checked=s[key])
            box.toggled.connect(toggled)
            lay.addWidget(box)
        self.fight_log = QPushButton("戰鬥紀錄…", objectName="link", clicked=lambda: FightLog(self).exec())
        lay.addWidget(self.fight_log, 0, Qt.AlignLeft)

        group("裝置")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.device_box = self.control(QComboBox(accessibleName="裝置"))
        self.device_box.addItem("自動偵測", None)
        self.device_box.activated.connect(self.pick_device)
        row.addWidget(self.device_box, 1)
        row.addWidget(self.control(QPushButton("重新尋找", toolTip="重新尋找模擬器與 PC 版",
                                               clicked=lambda: self.worker.send("scan"))))
        lay.addLayout(row)
        tips = {key: f"{name}（{cost}{'' if can_hold else '，回合播放時不按住'}）"
                for key, (name, cost, _, can_hold) in devices.PC_INPUTS.items()}
        self.pc_inputs = Segmented({key: (short, tips[key]) for key, short in PC_INPUT_NAMES.items()},
                                   s["pc_input"], "PC 版點擊方式")
        self.pc_inputs.chosen.connect(self.set_pc_input)
        lay.addLayout(self.labelled("PC 點擊", self.pc_inputs))

        group("顯示")
        self.sizes = Segmented({key: (name, "") for key, (name, _) in TEXT_SIZES.items()}, s["text_size"], "字級")
        self.sizes.chosen.connect(self.set_text_size)
        lay.addLayout(self.labelled("字級", self.sizes))

        group("熱鍵")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.hotkey_text = QLabel()
        row.addWidget(self.hotkey_text, 1)
        row.addWidget(self.control(QPushButton("修改…", clicked=self.edit_hotkeys)))
        lay.addLayout(row)
        return page

    def labelled(self, text, widget):
        """A settings row: a label as wide as the others, then widget."""
        self.controls += getattr(widget, "buttons", {}).values()
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(text)
        self.row_labels.append(label)
        row.addWidget(label)
        row.addWidget(widget, 1)
        return row

    def apply_text_size(self):
        """Text of the chosen size everywhere, dialogs included, in a window and controls sized to it."""
        base = TEXT_SIZES[self.settings["text_size"]][1]
        font = QFont("Microsoft JhengHei UI")
        font.setPointSizeF(base)
        QApplication.setFont(font)
        metrics = QFontMetrics(font)
        QApplication.instance().setStyleSheet(style(base, metrics.height()))
        self.root.setFixedWidth(scaled(380, base))
        height = control_height(metrics.height())
        for widget in self.controls:
            widget.setFixedHeight(height)
        self.start.setFixedHeight(height + 8)
        for section in self.sections.values():
            section.head.setFixedHeight(height + 4)
        width = max(metrics.horizontalAdvance(label.text()) for label in self.row_labels)
        for label in self.row_labels:
            label.setFixedWidth(width)
        self.apply_icons()
        self.apply_pane_icons()
        QTimer.singleShot(0, self.adjustSize)

    def fit_panes(self):
        """The detail panes shown as tall as pane_heights makes them where the window is now. Their text changing
        size, the window being laid out again (the text size, a fold, a line shown or hidden above a pane) or moving
        bring it here.

        Qt carries a new pane height up to the window one layout per event pass, so a fit that read the window's
        bottom in between would chase the fit before it, for good: the layouts holding the panes run here first."""
        panes = [pane for pane in (self.detail, self.gift_detail) if pane.isVisible()]
        if not panes:
            return  # showing one lays the window out, which comes back here
        for pane in panes:
            holder = pane.parentWidget()
            while holder is not None:
                holder.layout().activate()
                holder = holder.parentWidget()
        pane = panes[0]
        chrome = pane.height() - pane.viewport().height()  # the border and the padding, the same on every pane
        screen = self.screen().availableGeometry()
        room = sum(p.height() for p in panes) + screen.bottom() - SCREEN_GAP - self.frameGeometry().bottom()
        floor = PANE_LINES * pane.fontMetrics().lineSpacing() + 2 * round(pane.document().documentMargin()) + chrome
        preferred = scaled(300, TEXT_SIZES[self.settings["text_size"]][1])
        contents = [ceil(p.document().size().height()) + chrome for p in panes]
        for p, height in zip(panes, pane_heights(contents, preferred, room, floor)):
            p.setFixedHeight(height)

    def moveEvent(self, e):
        """The pane follows the screen's bottom while the window is dragged, too. The fit waits for the next event
        pass, so a burst of mouse moves costs one layout; it only resizes the window, from its top, which moves
        nothing and so comes back to no moveEvent."""
        self.fit_timer.start()
        super().moveEvent(e)

    def apply_icons(self):
        """The icons for the states they show, at the text's size, drawn for the screen's pixel ratio."""
        side, ratio = scaled(15, TEXT_SIZES[self.settings["text_size"]][1]), self.devicePixelRatioF()
        pinned = self.settings["pin"]
        _, pin_icon, pin_tip = PIN[pinned]
        for button, name, color in ((self.gear, "gear", ICON_ON if self.gear.isChecked() else ICON),
                                    (self.pin, pin_icon, ICON_ON if pinned else ICON),
                                    (self.close_button, "close", ICON),
                                    (self.start, "stop" if self.running else "play", "#fff")):
            button.setIcon(icons.icon(name, color, side, ratio))
            button.setIconSize(QSize(side, side))
        self.pin.setToolTip(pin_tip)
        self.dot.setPixmap(icons.pixmap("dot", DOT[self.dot.property("state")], side // 2, ratio))
        for section in self.sections.values():
            arrow = "unfolded" if section.head.isChecked() else "folded"
            section.arrow.setPixmap(icons.pixmap(arrow, HEAD_ICON, side, ratio))

    def apply_pane_icons(self):
        """The detail pane's icons (PANE_ICONS) as its document's images, drawn for the screen's pixel ratio. An image
        stands on the baseline, so a square twice as tall as the middle of a Chinese glyph above the baseline is
        centred on the text beside it, at any text size and in any font."""
        text = self.detail.document()
        ink = QFontMetricsF(self.detail.font()).tightBoundingRect("國")
        side, ratio = round(-(ink.top() + ink.bottom())), self.devicePixelRatioF()
        for name, color in PANE_ICONS.items():
            text.addResource(QTextDocument.ImageResource, QUrl(f"icon:{name}"), icons.pixmap(name, color, side, ratio))
        text.markContentsDirty(0, text.characterCount())  # addResource alone leaves the old size in the layout

    def event(self, e):
        if e.type() == QEvent.DevicePixelRatioChange:  # moved to a screen of another scale
            self.apply_icons()
            self.apply_pane_icons()
        elif e.type() == QEvent.LayoutRequest:  # laid out again: what is above the pane may have changed height
            self.fit_timer.start()
        return super().event(e)

    def show_settings(self, on):
        """The settings page in place of the main page while the gear is on."""
        self.main_page.setVisible(not on)
        self.settings_page.setVisible(on)
        self.apply_icons()
        QTimer.singleShot(0, self.adjustSize)

    def set_section_open(self, key, on):
        opened = set(self.settings["open_sections"]) - {key} | ({key} if on else set())
        self.settings["open_sections"] = [k for k in SECTIONS if k in opened]
        save_settings(self.settings)
        self.apply_icons()
        QTimer.singleShot(0, self.adjustSize)

    def show_event_summary(self):
        self.sections["event"].set_summary(event_summary(self.settings))

    def set_pin(self, on):
        """Keep the window on top of the game, or make it a normal window, where it is."""
        self.settings["pin"] = on
        self.apply_icons()
        pos = self.pos()
        self.setWindowFlags(PIN[on][0])  # Qt makes a new native window, hidden
        self.move(pos)
        self.show()
        save_settings(self.settings)

    def set_text_size(self, key):
        self.settings["text_size"] = key
        self.sizes.show_choice(key)
        self.apply_text_size()
        save_settings(self.settings)

    def apply_hotkey_labels(self):
        keys = self.settings["hotkeys"]
        self.read_button.setText(f"讀取畫面  {keys['read']}")
        self.start.setToolTip(f"全域熱鍵 {keys['battle']}")
        self.hotkey_text.setText(f"開始／停止  {keys['battle']}　　讀取畫面  {keys['read']}")

    def apply_hotkeys(self):
        """Register the hotkeys in settings (again): the ones Windows refused, which another program holds."""
        keys = self.settings["hotkeys"]
        actions = {"battle": self.toggle_battle, "read": lambda: self.worker.send("read_event")}
        self.hotkeys.clear()
        self.hotkeys_taken = [keys[n] for n, a in actions.items() if not self.hotkeys.add(HOTKEY_IDS[n], keys[n], a)]
        self.apply_hotkey_labels()
        self.update_start()
        if self.hotkeys_taken:
            self.say(f"熱鍵 {', '.join(self.hotkeys_taken)} 被其他程式佔用，請在設定（齒輪）的「熱鍵」換一個")
        elif not self.running:
            self.say("")
        return self.hotkeys_taken

    def edit_hotkeys(self):
        dialog = HotkeyDialog(self.settings["hotkeys"], self)
        if dialog.exec() == QDialog.Accepted:
            self.settings["hotkeys"] = dialog.keys()
            self.apply_hotkeys()

    def say(self, text):
        """The battle bar's status line: the battle under way, or what went wrong; it takes no room while empty."""
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def plan(self):
        s = self.settings
        return Plan(Pick(s["pick"]), GUARD_MODES[s["guard_mode"]][1](s["guard"]))

    def update_start(self):
        """START, green with a play icon; while the battle runs, a red stop."""
        key = self.settings["hotkeys"]["battle"]
        self.start.setText(f"停止  {key}" if self.running else f"開始自動戰鬥  {key}")
        self.apply_icons()
        self.start.setProperty("running", "true" if self.running else "false")
        self.start.style().unpolish(self.start)
        self.start.style().polish(self.start)

    def toggle_battle(self):
        if self.running:
            self.worker.stop_battle()
        else:
            self.running = True
            self.update_start()
            self.worker.send("start_battle", self.plan(), self.settings["hold"])

    def set_pick(self, key):
        self.settings["pick"] = key
        self.worker.send("set_pick", Pick(key))

    def set_guard_mode(self, index):
        self.settings["guard_mode"] = self.guard_box.itemData(index)
        self.guard_spin.setVisible(self.settings["guard_mode"] == "turns")
        self.worker.send("set_guard", self.plan().guard)

    def set_guard_turns(self, turns):
        self.settings["guard"] = turns
        self.worker.send("set_guard", self.plan().guard)

    def set_hold(self, on):
        self.settings["hold"] = on
        self.worker.send("set_hold", on)

    def set_flag(self, key, on):
        self.settings[key] = on
        if key == "stop_after_victory":
            self.worker.send("set_stop_after_victory", on)

    def on_fight(self, fight, device):
        """A battle ended: log it, and say so in a Windows notification when asked."""
        row = fights.record(fight, device)
        if self.settings["notify"]:
            self.notifier().showMessage(f"戰鬥{fights.RESULT_TEXT[fight.result]}",
                                        f"{row['turns']} 回合，{fights.duration(row['seconds'])}"
                                        + ("；自動戰鬥已停止" if fight.result == "victory" and self.settings["stop_after_victory"] else ""))

    def notifier(self):
        """The tray icon Windows notifications come from, made on first use."""
        if self.tray is None:
            self.tray = QSystemTrayIcon(logo(), self)
            self.tray.setToolTip("LC Helper")
            self.tray.show()
        return self.tray

    def set_pc_input(self, key):
        self.settings["pc_input"] = key
        self.pc_inputs.show_choice(key)
        self.worker.send("set_pc_input", key)

    def set_watch(self, on):
        self.settings["watch"] = on
        self.show_event_summary()
        self.worker.send("set_watch", on)

    def set_skip(self, on):
        self.settings["skip"] = on
        self.show_event_summary()
        self.say_skip("")
        self.worker.send("set_skip", on)

    def say_skip(self, text):
        """The skipper's state under its switch; the line takes no room while empty."""
        self.skip_state.setText(text)
        self.skip_state.setVisible(bool(text) and self.skip_box.isChecked())
        QTimer.singleShot(0, self.adjustSize)

    def show_keywords(self):
        """The recommended keywords as chips in their order, each with a menu to move it or remove it, then ＋ 體系
        while there is room for one more, or what adding one does while there is none."""
        while self.keyword_row.count():
            if widget := self.keyword_row.takeAt(0).widget():
                widget.hide()
                widget.deleteLater()  # later: the menu that asked for this may belong to it
        keywords = self.settings["keywords"]
        for i, keyword in enumerate(keywords):
            name = events.KEYWORDS[keyword]
            chip = QToolButton(objectName="chip", text=f"{i + 1} {name}", popupMode=QToolButton.InstantPopup,
                               accessibleName=f"推薦體系第 {i + 1} 位：{name}", toolTip="調整順序或移除")
            menu = QMenu(chip)
            for text, j in (("往前移", i - 1), ("往後移", i + 1)):
                order = list(keywords)
                if 0 <= j < len(order):
                    order[i], order[j] = order[j], order[i]
                self.keyword_action(menu, text, order).setEnabled(0 <= j < len(order))
            self.keyword_action(menu, "移除", [k for k in keywords if k != keyword])
            chip.setMenu(menu)
            self.keyword_row.addWidget(chip)
        if len(keywords) < MAX_KEYWORDS:
            add = QToolButton(objectName="chipAdd", text="＋ 體系", popupMode=QToolButton.InstantPopup,
                              toolTip="加入一個體系，排在最後")
            menu = QMenu(add)
            for keyword in recommend.CHOICES:
                if keyword not in keywords:
                    self.keyword_action(menu, f"{events.KEYWORDS[keyword]}  {keyword}", [*keywords, keyword])
            add.setMenu(menu)
            self.keyword_row.addWidget(add)
        if not keywords:
            self.keyword_row.addWidget(QLabel("加入後標出建議的選項", objectName="status"))
        self.keyword_row.addStretch()

    def keyword_action(self, menu, text, keywords):
        """A menu item that sets keywords."""
        action = menu.addAction(text)
        action.triggered.connect(lambda: self.set_keywords(keywords))
        return action

    def set_keywords(self, keywords):
        """New keywords or a new order: the chips, the folded summary and the event shown follow."""
        self.settings["keywords"] = keywords
        self.show_keywords()
        self.show_event_summary()
        if self.last_reading is not None:
            self.shown_event = None
            self.on_event(self.last_reading)
        elif self.shown_event is not None:
            self.show_event(self.shown_event)

    def set_overlay(self, on):
        self.settings["overlay"] = on
        if not on:
            self.overlay.hide_labels()

    def pick_device(self, index):
        self.settings["address"] = self.device_box.itemData(index)
        self.worker.send("connect", self.settings["address"])

    def on_device(self, state, text):
        """The device's state in the title bar: the dot's colour, and the device's name once connected; a failed
        connection also says why on the status line."""
        self.dot.setProperty("state", state)
        self.device_name.setText(text if state == "connected" else DEVICE_STATES[state])
        for part in (self.dot, self.device_name):
            part.setToolTip(f"已連上 {text}" if state == "connected" else text)
        self.apply_icons()
        if state == "error":
            self.say(text)
        elif not self.running:
            self.say("")

    def on_targets(self, targets):
        current = self.settings["address"]
        self.device_box.clear()
        self.device_box.addItem("自動偵測", None)
        for t in targets:
            self.device_box.addItem(device_choice(t), t.address)
        if current and self.device_box.findData(current) < 0:
            self.device_box.addItem(f"{current}（沒找到）", current)  # the worker still aims at it: say so
        self.device_box.setCurrentIndex(max(self.device_box.findData(current), 0))

    def on_battle(self, status: Status):
        """The battle's state on START and the status line, which keeps a stopped battle's reason only."""
        self.running = status.phase is not Phase.STOPPED
        self.update_start()
        self.say(status_text(status) if self.running or status.note else "")
        # The spin box counts down with the battle, to 0, and goes back to the set value once it stops;
        # set_guard_turns only hears the user, so a change made mid-battle restarts the count from what the user picked.
        left = status.plan.guard if self.running and status.plan.guard != FOREVER else self.settings["guard"]
        self.guard_spin.blockSignals(True)
        self.guard_spin.setMinimum(0 if self.running else 1)
        self.guard_spin.setValue(left)
        self.guard_spin.blockSignals(False)

    def on_event(self, reading):
        """A read event page: its effects in the window (unless it is the page already shown, read again for a
        scroll or a lit row) and, with the overlay on, beside the options on the game."""
        self.last_reading = reading
        if not (reading.event and reading.event is self.shown_event and not reading.others):
            self.show_event(reading.event, " ".join([reading.story, *reading.options]), reading.others, reading.closed)
            self.shown_event = reading.event
        if self.settings["overlay"] and reading.event and not reading.others:
            pick = recommend.best(reading.event, self.settings["keywords"], reading.closed)
            self.overlay.show_labels(labels(reading, lambda o: pick is not None and o is pick[0]), reading.source,
                                     hold_ms=0 if self.settings["watch"] else 60_000)
        else:
            self.overlay.hide_labels()

    def show_found_event(self, event):
        self.last_reading = None
        self.show_event(event)

    def clear_event(self):
        """The search field emptied: the pane goes back to saying how to fill it."""
        self.shown_event = self.last_reading = None
        self.detail.setHtml(EVENT_PLACEHOLDER)

    def on_gifts(self, reading):
        """A gift screen read: its gifts in Chinese, with the effects once enhanced and their fusion recipes."""
        heading = {"choice": "畫面上可以選的飾品", "get": "剛獲得的飾品"}.get(reading.page, "")
        if reading.gifts:
            self.show_gifts([g for g, _ in reading.gifts], heading)
        else:
            self.gift_detail.setHtml("<p style='color:#d9a441'>飾品畫面上沒讀到飾品名字</p>")

    def show_gifts(self, gift_list, heading=""):
        """Gifts in the gift pane; the folded section names them."""
        self.gift_detail.setHtml(gift_html(gift_list, heading))
        self.sections["gift"].set_summary("最近：" + "、".join(g["zh"] or g["en"] for g in gift_list))

    def clear_gifts(self):
        self.gift_detail.setHtml(GIFT_PLACEHOLDER)
        self.sections["gift"].set_summary("")

    def show_event(self, event, read_text="", others=(), closed=()):
        """An event in the detail pane, its recommended option starred when keywords are set; closed are option
        texts shown grey on screen."""
        self.shown_event = event
        pick = (lambda e: recommend.best(e, self.settings["keywords"], closed))
        page = event_html(event, read_text, pick(event))
        if others:
            page = ("<p style='color:#d9a441;margin:0 0 4px 0'>畫面上的文字對到不只一個事件，選項效果各列一份</p>"
                    + "<hr>".join(event_html(e, pick=pick(e)) for e in (event, *others)))
        self.detail.setHtml(page)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.header.geometry().contains(e.position().toPoint()):
            self.drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.drag_from is not None:
            self.move(e.globalPosition().toPoint() - self.drag_from)

    def mouseReleaseEvent(self, e):
        self.drag_from = None

    def closeEvent(self, e):
        self.settings["pos"] = [self.x(), self.y()]
        save_settings(self.settings)
        self.overlay.close()
        if self.tray is not None:
            self.tray.hide()
        self.worker.shutdown()
        self.worker.join(timeout=3)
        super().closeEvent(e)
        QApplication.quit()  # a Qt.Tool window does not count as the last window: closing it alone quits nothing


def offline_worker(callbacks):
    """A worker that finds and connects to nothing: event search only, and no adb or game window is touched."""
    def no_device(address, **_):
        raise RuntimeError("離線模式（--offline）：不連模擬器或 PC 版，只能查事件")
    return Worker(callbacks, connect=no_device, find=lambda: [])


def self_test():
    """Search the events and OCR a line of rendered text, writing what came back to .local/self-test.txt: proof that
    a built lc-helper.exe carries its data, the OCR model and MaaFramework's libraries. No device is touched."""
    import cv2
    import numpy as np

    from . import ocr
    image = np.zeros((720, 1280, 3), np.uint8)
    cv2.putText(image, "What will you do?", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    hits = events.search("螺旋")
    found = gifts.search("地獄蝶")
    lines = [f"search 螺旋: {len(hits)} events, first {hits[0]['id'] if hits else None}",
             f"gift 地獄蝶: {found[0]['en'] if found else None}",
             f"ocr: {[text for text, _ in ocr.lines(image, (60, 60, 700, 100))]}"]
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / "self-test.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(worker_factory=Worker):
    if "--self-test" in sys.argv[1:]:
        self_test()
        return
    offline = "--offline" in sys.argv[1:] and worker_factory is Worker
    if offline:
        worker_factory = offline_worker
    app = QApplication(sys.argv)
    hotkeys = Hotkeys()
    app.installNativeEventFilter(hotkeys)
    window = Window(worker_factory, hotkeys)
    window.apply_hotkeys()
    if offline:
        window.device_name.setText("離線模式")
        window.device_name.setToolTip("離線模式（--offline）：只查事件，不連模擬器或 PC 版")
    window.show()
    window.worker.start()
    window.worker.send("scan")
    window.worker.send("set_address", window.settings["address"])
    window.worker.send("set_pc_input", window.settings["pc_input"])
    window.worker.send("set_stop_after_victory", window.settings["stop_after_victory"])
    if window.settings["watch"]:  # auto read loads the OCR model now; otherwise the first event read does
        window.worker.send("set_watch", True)
    if window.settings["skip"]:
        window.worker.send("set_skip", True)
    code = app.exec()
    hotkeys.clear()
    if sys.stdout is not None:  # None in the built lc-helper.exe, which has no console
        sys.stdout.flush()
    # MaaFramework's controller threads can hold up interpreter shutdown (seen with a connect still running);
    # the settings are saved and the battle stopped by now.
    os._exit(code)
