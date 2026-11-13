"""The floating window: auto battle controls on top, the Mirror Dungeon event lookup below.

Settings (device, pick, guard turns, hotkeys, text size, pin, window position) live in .local/settings.json beside the repository.
"""

import ctypes
import html
import os
import json
import sys
from ctypes import wintypes
from string import Template

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QHBoxLayout, QKeySequenceEdit, QLabel, QLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QPushButton, QSpinBox, QSystemTrayIcon, QTextBrowser,
                               QToolButton, QVBoxLayout, QWidget)

from . import device as devices
from .paths import LOCAL
from . import events, fights, gifts, recommend
from .overlay import Overlay, labels
from .battle import FOREVER, Phase, Pick, Plan, Status
from .worker import Callbacks, Worker

SETTINGS = LOCAL / "settings.json"
DEFAULTS = {"address": None, "pc_input": devices.PC_INPUT, "pick": "win_rate", "guard": 0, "forever": False,
            "hold": True, "watch": False, "skip": False, "overlay": True, "keyword": None, "stop_after_victory": False, "notify": True, "compact": False, "text_size": "normal", "pin": True, "pos": None, "hotkeys": {"battle": "F8", "read": "F9"}}
PICK_TEXT = {Pick.WIN_RATE: "勝率", Pick.DAMAGE: "傷害"}
TEXT_SIZES = {"small": ("小", 10.5), "normal": ("標準", 12), "large": ("大", 13.5)}  # text_size: menu name, points
REFERENCE_PT = 10  # the window's pixel sizes were set for text of this size
# pin: window flags, and the pin button's tooltip. A Qt.Tool window has no taskbar entry, so the unpinned window is a
# normal one: when it falls behind the game, the taskbar and Alt+Tab still find it.
PIN = {True: (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
              "置頂中：點一下取消置頂，視窗改成一般視窗，被蓋住時從工作列或 Alt+Tab 叫回"),
       False: (Qt.FramelessWindowHint | Qt.Window, "沒有置頂：點一下讓視窗固定在最上層")}

STYLE = Template("""
QWidget#root { background: #17130f; border: 1px solid #5b4527; border-radius: 10px; }
QWidget { color: #eadcc4; font-family: "Microsoft JhengHei UI", "Segoe UI"; font-size: ${body}pt; }
QFrame#header { background: #231b13; border-top-left-radius: 10px; border-top-right-radius: 10px;
                border-bottom: 1px solid #5b4527; }
QLabel#title { color: #e7b45a; font-size: ${big}pt; font-weight: bold; letter-spacing: 1px; }
QLabel#section { color: #c9a165; font-size: ${small}pt; font-weight: bold; }
QLabel#status { color: #b9ab93; font-size: ${small}pt; }
QLabel#dot[state="connected"] { color: #6cc070; } QLabel#dot[state="connecting"] { color: #e7b45a; }
QLabel#dot[state="error"] { color: #d9534f; } QLabel#dot[state="idle"] { color: #6b6152; }
QPushButton, QToolButton { background: #2c2219; border: 1px solid #5b4527; border-radius: 6px; padding: 5px 10px; }
QPushButton:hover, QToolButton:hover { background: #3a2c1f; }
QPushButton:checked { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; }
QPushButton:disabled { background: #1d1711; border-color: #3e2f1d; color: #6b6152; }
QPushButton#primary { background: #9e2b22; border-color: #d65a45; color: #fff; font-size: ${big}pt; font-weight: bold;
                       padding: 8px; }
QPushButton#primary:hover { background: #b8352a; }
QPushButton#primary[running="true"] { background: #3d4a2a; border-color: #8fb35a; }
QToolButton#flat { background: transparent; border: none; padding: 2px 6px; color: #b9ab93; }
QToolButton#flat:hover { color: #fff; }
QToolButton#flat:checked { color: #e7b45a; }
QToolButton#flat::menu-indicator { image: none; width: 0; }
QSpinBox, QLineEdit, QComboBox { background: #0f0c09; border: 1px solid #5b4527; border-radius: 6px; padding: 4px 6px; }
QComboBox QAbstractItemView { background: #1d1711; selection-background-color: #6b4a1f; }
QListWidget { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; }
QListWidget::item { padding: 4px; } QListWidget::item:selected { background: #4a3417; }
QTextBrowser { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; padding: 4px; }
QCheckBox { color: #b9ab93; font-size: ${small}pt; }
QMenu { background: #1d1711; border: 1px solid #5b4527; } QMenu::item:selected { background: #4a3417; }
QDialog { background: #17130f; }
QKeySequenceEdit QLineEdit { min-width: 140px; }
""")


def style(base):
    """The style sheet for body text of base points: secondary text a step smaller, the title and START a step bigger."""
    return STYLE.substitute(body=base, small=base - 1.5, big=base + 1.5)


def scaled(px, base):
    """A pixel size set for REFERENCE_PT text, for text of base points."""
    return round(px * base / REFERENCE_PT)


def load_settings():
    try:
        return DEFAULTS | json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)


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
    return "無限防禦" if guard == FOREVER else f"防禦剩 {guard} 回合" if guard else ""


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
        title = ("★ " if picked else "") + html.escape(o["text_zh"] or o["text"])
        en = html.escape(o["text"]) if o["text_zh"] else ""
        rows.append(f"<p style='margin:6px 0 0 0'><b style='color:#e7b45a'>{i}. {title}</b> "
                    f"<span style='color:#7d715f'>{en}</span> "
                    f"<span style='background:#3a2c1f;color:#d8c7a6'>&nbsp;{events.kind_text(o)}&nbsp;</span></p>")
        if picked:
            rows.append(f"<p style='color:#f0c674;margin:0 0 0 14px'>推薦：{html.escape(pick[1])}</p>")
        hint = o["hint_zh"] or o["hint"]
        if hint:
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>{html.escape(hint)}</p>")
        for e in events.effects(o):
            what = html.escape(e.what).replace("「", "<span style='color:#f0c674'>「").replace("」", "」</span>")
            rows.append(f"<p style='margin:0 0 0 14px'>• <span style='color:#9fc1d9'>{html.escape(e.when)}</span>"
                        f"：{what}</p>")
    return "".join(rows)


def gift_html(gift_list, heading=""):
    """Gifts and their effects, as the detail pane shows them: Chinese first, English under it."""
    rows = [f"<p style='color:#8f8270;margin:0'>{html.escape(heading)}</p>"] if heading else []
    names = gifts.book()
    for g in gift_list:
        rows.append(f"<p style='margin:6px 0 0 0'><b style='color:#e7b45a'>{html.escape(gifts.label(g))}</b> "
                    f"<span style='color:#7d715f'>{html.escape(g['en'])}</span></p>")
        for text, color in ((g["desc_zh"], "#eadcc4"), (g["desc_en"] if not g["desc_zh"] else "", "#a99c86")):
            if text:
                rows.append(f"<p style='color:{color};margin:0 0 0 14px'>{html.escape(text).replace(chr(10), '<br>')}</p>")
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


class Window(QWidget):
    def __init__(self, worker_factory=Worker, hotkeys=None):
        settings = load_settings()
        super().__init__(None, PIN[settings["pin"]][0])
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("LC Helper")
        self.setWindowIcon(logo())
        self.settings = settings
        self.hotkeys = hotkeys if hotkeys is not None else Hotkeys()
        self.hotkeys_taken = []
        self.overlay = Overlay()
        self.tray = None
        self.last_reading = None  # the event page last read, ranked again on a new keyword
        self.shown_event = None
        self.running = False
        self.drag_from: QPoint | None = None
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
        self.bridge.error.connect(lambda text: self.status.setText(text))
        self.search_timer = QTimer(self, singleShot=True, interval=120, timeout=self.run_search)

    def build(self):
        s = self.settings
        self.root = root = QWidget(self, objectName="root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SetFixedSize)  # the window is as tall as what it shows
        outer.addWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(8)

        header = QFrame(objectName="header")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 6, 6, 6)
        h.addWidget(QLabel("LC Helper", objectName="title"))
        self.dot = QLabel("●", objectName="dot")
        self.dot.setProperty("state", "idle")
        self.dot.setToolTip("還沒連線：第一次開始戰鬥或讀取事件時才連")
        h.addWidget(self.dot)
        self.device_box = QComboBox()
        self.device_box.addItem("自動偵測", None)
        self.device_box.activated.connect(self.pick_device)
        h.addWidget(self.device_box, 1)  # the device list takes the width the buttons leave
        self.pin = QToolButton(objectName="flat", text="置頂", checkable=True, checked=s["pin"], toolTip=PIN[s["pin"]][1])
        self.pin.toggled.connect(self.set_pin)
        h.addWidget(self.pin)
        more = QToolButton(objectName="flat", text="⋯", popupMode=QToolButton.InstantPopup)
        menu = QMenu(more)
        self.hold_action = QAction("回合播放時按住畫面（加快 E.G.O 動畫）", menu, checkable=True, checked=s["hold"])
        self.hold_action.toggled.connect(self.set_hold)
        menu.addAction(self.hold_action)
        for key, text in (("stop_after_victory", "勝利後停止自動戰鬥"), ("notify", "戰鬥結束時跳出 Windows 通知")):
            action = QAction(text, menu, checkable=True, checked=s[key])
            action.toggled.connect(lambda on, key=key: self.set_flag(key, on))
            menu.addAction(action)
        menu.addAction("戰鬥紀錄…", lambda: FightLog(self).exec())
        pc_menu = menu.addMenu("PC 版點擊方式")
        group = QActionGroup(pc_menu)
        for key, (name, cost, _, can_hold) in devices.PC_INPUTS.items():
            text = f"{name}（{cost}{'' if can_hold else '，回合播放時不按住'}）"
            action = QAction(text, group, checkable=True, checked=key == s["pc_input"])
            action.triggered.connect(lambda _, key=key: self.set_pc_input(key))
            pc_menu.addAction(action)
        menu.addAction("重新尋找模擬器與 PC 版", lambda: self.worker.send("scan"))
        menu.addAction("熱鍵設定…", self.edit_hotkeys)
        size_menu = menu.addMenu("字級")
        group = QActionGroup(size_menu)
        for key, (name, _) in TEXT_SIZES.items():
            action = QAction(name, group, checkable=True, checked=key == s["text_size"])
            action.triggered.connect(lambda _, key=key: self.set_text_size(key))
            size_menu.addAction(action)
        more.setMenu(menu)
        h.addWidget(more)
        self.fold = QToolButton(objectName="flat", text="▸" if s["compact"] else "▾", clicked=self.toggle_compact)
        self.fold.setToolTip("收合事件查詢")
        h.addWidget(self.fold)
        h.addWidget(QToolButton(objectName="flat", text="✕", clicked=self.close))
        lay.addWidget(header)
        self.header = header

        body = QVBoxLayout()
        body.setContentsMargins(12, 0, 12, 0)
        body.setSpacing(8)
        lay.addLayout(body)

        body.addWidget(QLabel("自動戰鬥", objectName="section"))
        row = QHBoxLayout()
        self.picks = QButtonGroup(self)
        for pick in Pick:
            b = QPushButton(f"{PICK_TEXT[pick]}  {'Win Rate' if pick is Pick.WIN_RATE else 'Damage'}", checkable=True)
            b.setChecked(s["pick"] == pick.value)
            self.picks.addButton(b)
            b.setProperty("pick", pick.value)
            row.addWidget(b)
        self.picks.buttonClicked.connect(self.set_pick)
        body.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("先防禦"))
        self.guard_spin = QSpinBox(minimum=0, maximum=99, value=s["guard"], suffix=" 回合")
        self.guard_spin.valueChanged.connect(self.set_guard)
        row.addWidget(self.guard_spin)
        self.forever = QPushButton("∞ 無限防禦", checkable=True, checked=s["forever"])
        self.forever.toggled.connect(self.set_guard)
        row.addWidget(self.forever)
        row.addStretch()
        body.addLayout(row)
        self.guard_spin.setEnabled(not s["forever"])

        self.start = QPushButton(objectName="primary", clicked=self.toggle_battle)
        body.addWidget(self.start)
        self.status = QLabel("還沒連上模擬器，第一次開始戰鬥或讀取事件時才連", objectName="status", wordWrap=True)
        body.addWidget(self.status)

        self.event_box = QWidget()
        ev = QVBoxLayout(self.event_box)
        ev.setContentsMargins(0, 4, 0, 0)
        ev.setSpacing(6)
        ev.addWidget(QLabel("鏡牢事件", objectName="section"))
        row = QHBoxLayout()
        self.query = QLineEdit(placeholderText="輸入事件、選項或飾品名字（中/英）")
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(lambda: self.search_timer.start())
        row.addWidget(self.query)
        self.read_button = QPushButton(clicked=lambda: self.worker.send("read_event"))
        row.addWidget(self.read_button)
        ev.addLayout(row)
        self.watch = QCheckBox("自動讀取：畫面出現事件選項就顯示", checked=s["watch"])
        self.watch.toggled.connect(self.set_watch)
        ev.addWidget(self.watch)
        self.skip_box = QCheckBox("自動跳過劇情：一路推進到選項頁（不替你選）", checked=s["skip"])
        self.skip_box.toggled.connect(self.set_skip)
        ev.addWidget(self.skip_box)
        self.skip_state = QLabel(objectName="status", visible=False)
        ev.addWidget(self.skip_state)
        self.overlay_box = QCheckBox("疊加顯示：把選項效果直接標在遊戲畫面上", checked=s["overlay"])
        self.overlay_box.toggled.connect(self.set_overlay)
        ev.addWidget(self.overlay_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("推薦選項，依主要體系：", objectName="status"))
        self.keyword_box = QComboBox()
        self.keyword_box.addItem("不推薦", None)
        for k in recommend.CHOICES:
            self.keyword_box.addItem(f"{events.KEYWORDS.get(k, k)}  {k}", k)
        self.keyword_box.setCurrentIndex(max(self.keyword_box.findData(s["keyword"]), 0))
        self.keyword_box.activated.connect(self.set_keyword)
        row.addWidget(self.keyword_box, 1)
        ev.addLayout(row)
        self.results = QListWidget()
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.hide()
        self.results.currentItemChanged.connect(lambda item, _: item and self.show_hit(*item.data(Qt.UserRole)))
        ev.addWidget(self.results)
        self.detail = QTextBrowser(openExternalLinks=False)
        self.detail.setHtml("<p style='color:#8f8270'>在事件的選項頁按「讀取畫面」，或輸入記得的幾個字。</p>")
        ev.addWidget(self.detail)
        body.addWidget(self.event_box)
        self.event_box.setVisible(not s["compact"])

        self.apply_text_size()
        self.apply_hotkey_labels()
        self.update_start()
        if s["pos"]:
            self.move(*s["pos"])

    def apply_text_size(self):
        """Text of the chosen size everywhere, menus and dialogs included, in a window sized to it."""
        base = TEXT_SIZES[self.settings["text_size"]][1]
        font = QFont("Microsoft JhengHei UI")
        font.setPointSizeF(base)
        QApplication.setFont(font)
        QApplication.instance().setStyleSheet(style(base))
        self.root.setFixedWidth(scaled(380, base))
        self.detail.setFixedHeight(scaled(300, base))
        QTimer.singleShot(0, self.adjustSize)

    def set_pin(self, on):
        """Keep the window on top of the game, or make it a normal window, where it is."""
        self.settings["pin"] = on
        self.pin.setToolTip(PIN[on][1])
        pos = self.pos()
        self.setWindowFlags(PIN[on][0])  # Qt makes a new native window, hidden
        self.move(pos)
        self.show()
        save_settings(self.settings)

    def set_text_size(self, key):
        self.settings["text_size"] = key
        self.apply_text_size()
        save_settings(self.settings)

    def apply_hotkey_labels(self):
        keys = self.settings["hotkeys"]
        self.read_button.setText(f"讀取畫面  {keys['read']}")
        self.start.setToolTip(f"全域熱鍵 {keys['battle']}")

    def apply_hotkeys(self):
        """Register the hotkeys in settings (again): the ones Windows refused, which another program holds."""
        keys = self.settings["hotkeys"]
        actions = {"battle": self.toggle_battle, "read": lambda: self.worker.send("read_event")}
        self.hotkeys.clear()
        self.hotkeys_taken = [keys[n] for n, a in actions.items() if not self.hotkeys.add(HOTKEY_IDS[n], keys[n], a)]
        self.apply_hotkey_labels()
        self.update_start()
        if self.hotkeys_taken:
            self.status.setText(f"熱鍵 {', '.join(self.hotkeys_taken)} 被其他程式佔用，請在「⋯」→「熱鍵設定」換一個")
        return self.hotkeys_taken

    def edit_hotkeys(self):
        dialog = HotkeyDialog(self.settings["hotkeys"], self)
        if dialog.exec() == QDialog.Accepted:
            self.settings["hotkeys"] = dialog.keys()
            if not self.apply_hotkeys():
                self.status.setText("熱鍵已更新")

    def plan(self):
        pick = Pick(self.picks.checkedButton().property("pick"))
        return Plan(pick, FOREVER if self.forever.isChecked() else self.guard_spin.value())

    def update_start(self):
        self.start.setText(f"停止  {self.settings['hotkeys']['battle']}" if self.running
                           else f"▶ 開始自動戰鬥  {self.settings['hotkeys']['battle']}")
        self.start.setProperty("running", "true" if self.running else "false")
        self.start.style().unpolish(self.start)
        self.start.style().polish(self.start)

    def toggle_battle(self):
        if self.running:
            self.worker.stop_battle()
        else:
            self.running = True
            self.update_start()
            self.worker.send("start_battle", self.plan(), self.hold_action.isChecked())

    def set_pick(self, button):
        self.settings["pick"] = button.property("pick")
        self.worker.send("set_pick", Pick(self.settings["pick"]))

    def set_guard(self, *_):
        self.settings["guard"], self.settings["forever"] = self.guard_spin.value(), self.forever.isChecked()
        self.guard_spin.setEnabled(not self.forever.isChecked())
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
        self.worker.send("set_pc_input", key)

    def set_watch(self, on):
        self.settings["watch"] = on
        self.worker.send("set_watch", on)

    def set_skip(self, on):
        self.settings["skip"] = on
        self.say_skip("")
        self.worker.send("set_skip", on)

    def say_skip(self, text):
        """The skipper's state under its switch; the line takes no room while empty."""
        self.skip_state.setText(text)
        self.skip_state.setVisible(bool(text) and self.skip_box.isChecked())
        QTimer.singleShot(0, self.adjustSize)

    def set_keyword(self, index):
        """A new main keyword: the event shown is ranked again."""
        self.settings["keyword"] = self.keyword_box.itemData(index)
        if self.last_reading is not None:
            self.shown_event = None
            self.on_event(self.last_reading)
        elif self.shown_event is not None:
            self.show_event(self.shown_event)

    def set_overlay(self, on):
        self.settings["overlay"] = on
        if not on:
            self.overlay.hide_labels()

    def toggle_compact(self):
        compact = self.event_box.isVisible()
        self.settings["compact"] = compact
        self.event_box.setVisible(not compact)
        self.fold.setText("▸" if compact else "▾")
        QTimer.singleShot(0, self.adjustSize)

    def pick_device(self, index):
        self.settings["address"] = self.device_box.itemData(index)
        self.worker.send("connect", self.settings["address"])

    def on_device(self, state, text):
        self.dot.setProperty("state", state)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        self.dot.setToolTip(text)
        if not self.running:
            self.status.setText({"connected": f"已連上 {text}", "connecting": "連線中…"}.get(state, text))

    def on_targets(self, targets):
        current = self.settings["address"]
        self.device_box.clear()
        self.device_box.addItem("自動偵測", None)
        for t in targets:
            self.device_box.addItem(t.name if t.address == devices.PC else f"{t.name} {t.address.rsplit(':', 1)[-1]}",
                                    t.address)
        if current and self.device_box.findData(current) < 0:
            self.device_box.addItem(f"{current}（沒找到）", current)  # the worker still aims at it: say so
        self.device_box.setCurrentIndex(max(self.device_box.findData(current), 0))

    def on_battle(self, status: Status):
        self.running = status.phase is not Phase.STOPPED
        self.update_start()
        self.status.setText(status_text(status))
        # The spin box counts down with the battle and goes back to the set value once it stops; set_guard only
        # hears the user, so a change made mid-battle restarts the count from what the user picked.
        left = status.plan.guard if self.running and status.plan.guard != FOREVER else self.settings["guard"]
        self.guard_spin.blockSignals(True)
        self.guard_spin.setValue(left)
        self.guard_spin.blockSignals(False)

    def on_event(self, reading):
        """A read event page: its effects in the window (unless it is the page already shown, read again for a
        scroll or a lit row) and, with the overlay on, beside the options on the game."""
        self.results.hide()
        self.last_reading = reading
        if not (reading.event and reading.event is self.shown_event and not reading.others):
            self.show_event(reading.event, " ".join([reading.story, *reading.options]), reading.others, reading.closed)
            self.shown_event = reading.event
        if self.settings["overlay"] and reading.event and not reading.others:
            pick = recommend.best(reading.event, self.settings["keyword"], reading.closed)
            star = (lambda o: "★" if pick and o is pick[0] else "")
            self.overlay.show_labels(labels(reading, star), reading.source,
                                     hold_ms=0 if self.settings["watch"] else 60_000)
        else:
            self.overlay.hide_labels()

    def show_hit(self, kind, found):
        self.last_reading = None
        if kind == "gift":
            self.detail.setHtml(gift_html([found]))
        else:
            self.show_event(found)

    def on_gifts(self, reading):
        """A gift screen read: its gifts in Chinese, with the effects once enhanced and their fusion recipes."""
        self.results.hide()
        self.shown_event = self.last_reading = None
        heading = {"choice": "畫面上可以選的飾品", "get": "剛獲得的飾品"}.get(reading.page, "")
        self.detail.setHtml(gift_html([g for g, _ in reading.gifts], heading) if reading.gifts
                            else "<p style='color:#d9a441'>飾品畫面上沒讀到飾品名字</p>")

    def show_event(self, event, read_text="", others=(), closed=()):
        """An event in the detail pane, its recommended option starred when a main keyword is set; closed are
        option texts shown grey on screen."""
        self.shown_event = event
        pick = (lambda e: recommend.best(e, self.settings["keyword"], closed))
        page = event_html(event, read_text, pick(event))
        if others:
            page = ("<p style='color:#d9a441;margin:0 0 4px 0'>畫面上的文字對到不只一個事件，選項效果各列一份</p>"
                    + "<hr>".join(event_html(e, pick=pick(e)) for e in (event, *others)))
        self.detail.setHtml(page)

    def run_search(self):
        query = self.query.text()
        hits = [("gift", g) for g in gifts.search(query, limit=4)] + [("event", e) for e in events.search(query, limit=6)]
        self.results.clear()
        for kind, found in hits:
            item = QListWidgetItem(f"飾品｜{gifts.label(found)}" if kind == "gift" else result_text(found))
            item.setData(Qt.UserRole, (kind, found))
            self.results.addItem(item)
        self.results.setFixedHeight(min(len(hits), 5) * self.results.sizeHintForRow(0) + 6)
        self.results.setVisible(bool(hits))
        if hits:
            self.results.setCurrentRow(0)
        elif self.query.text().strip():
            self.detail.setHtml("<p style='color:#8f8270'>找不到符合的事件或飾品。</p>")

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
        window.status.setText("離線模式：只查事件，不連模擬器或 PC 版")
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
