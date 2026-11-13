"""The battle log: one JSON line per battle the auto battle played to its end, in .local/battles.jsonl."""

import json
import time

from .paths import LOCAL

LOG = LOCAL / "battles.jsonl"
RESULT_TEXT = {"victory": "勝利", "wipe": "全滅"}


def record(fight, device="", path=None, now=None):
    """Append fight (battle.Fight) with the time it ended and the device it was played on; the row written."""
    path = path or LOG
    row = {"at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "result": fight.result,
           "turns": fight.turns, "seconds": round(fight.seconds, 1), "device": device}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load(path=None, limit=200):
    """The last limit rows, newest first; a line that does not parse is skipped."""
    path = path or LOG
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows[::-1]


def duration(seconds):
    m, s = divmod(round(seconds), 60)
    return f"{m}:{s:02d}"


def row_text(row):
    return f"{row['at'][5:16]}  {RESULT_TEXT.get(row['result'], row['result'])}  {row['turns']} 回合  {duration(row['seconds'])}"


def summary(rows):
    """One line over rows: battles, wins, average turns and time."""
    if not rows:
        return "還沒有紀錄：自動戰鬥打完一場（勝利或全滅）就會記一筆"
    wins = sum(r["result"] == "victory" for r in rows)
    turns = sum(r["turns"] for r in rows) / len(rows)
    seconds = sum(r["seconds"] for r in rows) / len(rows)
    return f"{len(rows)} 場，勝利 {wins} 場；平均 {turns:.1f} 回合、{duration(seconds)}"
