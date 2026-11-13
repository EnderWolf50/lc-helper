"""The floating window: auto battle controls on top, the Mirror Dungeon event lookup below.

Settings (device, pick, guard turns, hotkeys, window position) live in .local/settings.json beside the repository.
"""

import ctypes
import html
import os
import json
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QSpinBox,
                               QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import events
from .battle import FOREVER, Phase, Pick, Plan, Status
from .worker import Callbacks, Worker

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS = ROOT / ".local/settings.json"
DEFAULTS = {"address": None, "pick": "win_rate", "guard": 0, "forever": False, "hold": True, "watch": False,
            "compact": False, "pos": None, "hotkeys": {"battle": "F8", "read": "F9"}}
PICK_TEXT = {Pick.WIN_RATE: "勝率", Pick.DAMAGE: "傷害"}

STYLE = """
QWidget#root { background: #17130f; border: 1px solid #5b4527; border-radius: 10px; }
QWidget { color: #eadcc4; font-family: "Microsoft JhengHei UI", "Segoe UI"; font-size: 10pt; }
QFrame#header { background: #231b13; border-top-left-radius: 10px; border-top-right-radius: 10px;
                border-bottom: 1px solid #5b4527; }
QLabel#title { color: #e7b45a; font-weight: bold; letter-spacing: 1px; }
QLabel#section { color: #c9a165; font-size: 9pt; font-weight: bold; }
QLabel#status { color: #b9ab93; font-size: 9pt; }
QLabel#dot[state="connected"] { color: #6cc070; } QLabel#dot[state="connecting"] { color: #e7b45a; }
QLabel#dot[state="error"] { color: #d9534f; } QLabel#dot[state="idle"] { color: #6b6152; }
QPushButton, QToolButton { background: #2c2219; border: 1px solid #5b4527; border-radius: 6px; padding: 5px 10px; }
QPushButton:hover, QToolButton:hover { background: #3a2c1f; }
QPushButton:checked { background: #6b4a1f; border-color: #e7b45a; color: #fff3dc; }
QPushButton#primary { background: #9e2b22; border-color: #d65a45; color: #fff; font-weight: bold; padding: 8px; }
QPushButton#primary:hover { background: #b8352a; }
QPushButton#primary[running="true"] { background: #3d4a2a; border-color: #8fb35a; }
QToolButton#flat { background: transparent; border: none; padding: 2px 6px; color: #b9ab93; }
QToolButton#flat:hover { color: #fff; }
QToolButton#flat::menu-indicator { image: none; width: 0; }
QSpinBox, QLineEdit, QComboBox { background: #0f0c09; border: 1px solid #5b4527; border-radius: 6px; padding: 4px 6px; }
QComboBox QAbstractItemView { background: #1d1711; selection-background-color: #6b4a1f; }
QListWidget { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; }
QListWidget::item { padding: 4px; } QListWidget::item:selected { background: #4a3417; }
QTextBrowser { background: #0f0c09; border: 1px solid #3e2f1d; border-radius: 6px; padding: 4px; }
QCheckBox { color: #b9ab93; font-size: 9pt; }
QMenu { background: #1d1711; border: 1px solid #5b4527; } QMenu::item:selected { background: #4a3417; }
"""


def load_settings():
    try:
        return DEFAULTS | json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


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


def event_html(event, read_text=""):
    """An event and what each option does, as the detail pane shows it."""
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
        title = html.escape(o["text_zh"] or o["text"])
        en = html.escape(o["text"]) if o["text_zh"] else ""
        rows.append(f"<p style='margin:6px 0 0 0'><b style='color:#e7b45a'>{i}. {title}</b> "
                    f"<span style='color:#7d715f'>{en}</span> "
                    f"<span style='background:#3a2c1f;color:#d8c7a6'>&nbsp;{events.kind_text(o)}&nbsp;</span></p>")
        hint = o["hint_zh"] or o["hint"]
        if hint:
            rows.append(f"<p style='color:#a99c86;margin:0 0 0 14px'>{html.escape(hint)}</p>")
        for e in events.effects(o):
            what = html.escape(e.what).replace("「", "<span style='color:#f0c674'>「").replace("」", "」</span>")
            rows.append(f"<p style='margin:0 0 0 14px'>• <span style='color:#9fc1d9'>{html.escape(e.when)}</span>"
                        f"：{what}</p>")
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
    error = Signal(str)

    def callbacks(self):
        return Callbacks(device=self.device.emit, targets=self.targets.emit, battle=self.battle.emit,
                         event=self.event.emit, error=self.error.emit)


VK = {f"F{i}": 0x6F + i for i in range(1, 13)}
WM_HOTKEY, MOD_NOREPEAT = 0x0312, 0x4000


class Hotkeys(QAbstractNativeEventFilter):
    """Global hotkeys (RegisterHotKey): they work while the emulator has the focus."""

    def __init__(self):
        super().__init__()
        self.actions = {}

    def add(self, name, action):
        vk = VK.get(name.upper())
        hid = len(self.actions) + 1
        if vk is None or not ctypes.windll.user32.RegisterHotKey(None, hid, MOD_NOREPEAT, vk):
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


class Window(QWidget):
    def __init__(self, worker_factory=Worker):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.settings = load_settings()
        self.running = False
        self.drag_from: QPoint | None = None
        self.bridge = Bridge()
        self.worker = worker_factory(self.bridge.callbacks())
        self.build()
        self.bridge.device.connect(self.on_device)
        self.bridge.targets.connect(self.on_targets)
        self.bridge.battle.connect(self.on_battle)
        self.bridge.event.connect(self.on_event)
        self.bridge.error.connect(lambda text: self.status.setText(text))
        self.search_timer = QTimer(self, singleShot=True, interval=120, timeout=self.run_search)

    def build(self):
        s = self.settings
        root = QWidget(self, objectName="root")
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
        h.addStretch()
        self.dot = QLabel("●", objectName="dot")
        self.dot.setProperty("state", "idle")
        self.dot.setToolTip("還沒連線：第一次開始戰鬥或讀取事件時才連")
        h.addWidget(self.dot)
        self.device_box = QComboBox()
        self.device_box.setMinimumWidth(130)
        self.device_box.addItem("自動偵測", None)
        self.device_box.activated.connect(self.pick_device)
        h.addWidget(self.device_box)
        more = QToolButton(objectName="flat", text="⋯", popupMode=QToolButton.InstantPopup)
        menu = QMenu(more)
        self.hold_action = QAction("回合播放時按住畫面（加快 E.G.O 動畫）", menu, checkable=True, checked=s["hold"])
        self.hold_action.toggled.connect(self.set_hold)
        menu.addAction(self.hold_action)
        menu.addAction("重新尋找模擬器", lambda: self.worker.send("scan"))
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
        self.query = QLineEdit(placeholderText="輸入事件或選項文字（中/英）")
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(lambda: self.search_timer.start())
        row.addWidget(self.query)
        self.read_button = QPushButton(clicked=lambda: self.worker.send("read_event"))
        row.addWidget(self.read_button)
        ev.addLayout(row)
        self.watch = QCheckBox("自動讀取：畫面出現事件選項就顯示", checked=s["watch"])
        self.watch.toggled.connect(self.set_watch)
        ev.addWidget(self.watch)
        self.results = QListWidget()
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.hide()
        self.results.currentItemChanged.connect(lambda item, _: item and self.show_event(item.data(Qt.UserRole)))
        ev.addWidget(self.results)
        self.detail = QTextBrowser(openExternalLinks=False)
        self.detail.setFixedHeight(300)
        self.detail.setHtml("<p style='color:#8f8270'>在事件的選項頁按「讀取畫面」，或輸入記得的幾個字。</p>")
        ev.addWidget(self.detail)
        body.addWidget(self.event_box)
        self.event_box.setVisible(not s["compact"])

        root.setFixedWidth(380)
        self.apply_hotkey_labels()
        self.update_start()
        if s["pos"]:
            self.move(*s["pos"])

    def apply_hotkey_labels(self):
        keys = self.settings["hotkeys"]
        self.read_button.setText(f"讀取畫面  {keys['read']}")
        self.start.setToolTip(f"全域熱鍵 {keys['battle']}")

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

    def set_watch(self, on):
        self.settings["watch"] = on
        self.worker.send("set_watch", on)

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
            self.device_box.addItem(f"{t.name} {t.address.rsplit(':', 1)[-1]}", t.address)
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
        self.results.hide()
        self.show_event(reading.event, " ".join([reading.story, *reading.options]), reading.others)

    def show_event(self, event, read_text="", others=()):
        page = event_html(event, read_text)
        if others:
            page = ("<p style='color:#d9a441;margin:0 0 4px 0'>畫面上的文字對到不只一個事件，選項效果各列一份</p>"
                    + "<hr>".join(event_html(e) for e in (event, *others)))
        self.detail.setHtml(page)

    def run_search(self):
        hits = events.search(self.query.text())
        self.results.clear()
        for e in hits:
            item = QListWidgetItem(result_text(e))
            item.setData(Qt.UserRole, e)
            self.results.addItem(item)
        self.results.setFixedHeight(min(len(hits), 5) * 26 + 6)
        self.results.setVisible(bool(hits))
        if hits:
            self.results.setCurrentRow(0)
        elif self.query.text().strip():
            self.detail.setHtml("<p style='color:#8f8270'>找不到符合的事件。</p>")

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
        self.worker.shutdown()
        self.worker.join(timeout=3)
        super().closeEvent(e)
        QApplication.quit()  # a Qt.Tool window does not count as the last window: closing it alone quits nothing


def main(worker_factory=Worker):
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Microsoft JhengHei UI", 10))
    window = Window(worker_factory)
    hotkeys = Hotkeys()
    app.installNativeEventFilter(hotkeys)
    keys = window.settings["hotkeys"]
    taken = [k for k, action in ((keys["battle"], window.toggle_battle),
                                 (keys["read"], lambda: window.worker.send("read_event"))) if not hotkeys.add(k, action)]
    window.show()
    window.worker.start()
    window.worker.send("scan")
    window.worker.send("set_address", window.settings["address"])
    window.worker.send("warm")
    if window.settings["watch"]:
        window.worker.send("set_watch", True)
    window.hotkeys_taken = taken
    if taken:
        window.status.setText(f"熱鍵 {', '.join(taken)} 被其他程式佔用，請改 .local/settings.json 的 hotkeys")
    code = app.exec()
    hotkeys.clear()
    sys.stdout.flush()
    # MaaFramework's controller threads can hold up interpreter shutdown (seen with a connect still running);
    # the settings are saved and the battle stopped by now.
    os._exit(code)
