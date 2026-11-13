import time

from lc_helper import fights
from lc_helper.battle import Fight, Phase, Plan
from lc_helper.device import Clock, Target
from lc_helper.worker import Callbacks, Worker
from fake_game import FakeBattle


def test_battles_are_logged_newest_first_with_a_summary(tmp_path):
    log = tmp_path / "battles.jsonl"
    fights.record(Fight("victory", 7, 151.0), "MuMuPlayer12", log, now=0)
    fights.record(Fight("wipe", 3, 62.4), "Limbus PC（合成觸控）", log, now=60)
    log.write_text(log.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    rows = fights.load(log)
    assert [r["result"] for r in rows] == ["wipe", "victory"]
    assert fights.row_text(rows[1]).endswith("勝利  7 回合  2:31")
    assert fights.summary(rows) == "2 場，勝利 1 場；平均 5.0 回合、1:47"
    assert fights.load(tmp_path / "none.jsonl") == []


def worker_on(device, **callbacks):
    w = Worker(Callbacks(**callbacks), connect=lambda address, **_: (device, Target("MuMuPlayer12", "127.0.0.1:1")),
               find=lambda: [])
    w.start()
    return w


def test_a_victory_reaches_the_window_and_can_stop_the_battle(screen):
    fake = FakeBattle(screen, Clock(), turns=2, play_s=0.5, max_shots=2000)
    seen, statuses = [], []
    w = worker_on(fake, fight=lambda f, device: seen.append((f.result, f.turns, device)), battle=statuses.append)
    w.send("set_stop_after_victory", True)
    w.send("start_battle", Plan(), False)
    end = time.monotonic() + 30
    while not (statuses and statuses[-1].phase is Phase.STOPPED) and time.monotonic() < end:
        time.sleep(0.05)
    assert seen == [("victory", 2, "MuMuPlayer12")]
    assert "戰鬥勝利" in statuses[-1].note
