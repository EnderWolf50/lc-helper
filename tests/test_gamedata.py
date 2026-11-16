"""The game data lc-helper reads, built from the resource package's data/ files (src/lc_helper/gamedata.py).

Expected values are literals from the shipped game text, not recomputed from the package.
"""

import json

from lc_helper import events, gifts, trials
from lc_helper.paths import PACKAGE


def test_an_event_has_its_text_in_three_scripts_and_its_options_in_the_tables_order():
    e = events.by_id()[130802]
    assert e["title"] == "Faelantern" and e["page"] is False
    assert e["story"].startswith("\"H-hang on. What's going on with this thing?")
    assert e["story_zh"].startswith("“等、等一下。這孩子怎麼了？")
    assert e["story_cn"].startswith("“等、等一下。这孩子怎么了？")
    first = e["options"][0]
    assert (first["text"], first["text_zh"], first["text_cn"]) == ("Keep reading the record", "繼續閱讀記錄", "继续阅读记录")
    assert first["kind"] == "other" and first["gift_keywords"] == []  # structure comes from event_table.json


def test_a_page_is_marked_and_event_ids_are_unique():
    book = events.book()["events"]
    assert len({e["id"] for e in book}) == len(book) == 217
    assert [e["id"] for e in book if e["page"]][:3] == [800201, 800203, 800205]


def test_an_options_hint_is_the_tables_english_and_the_texts_chinese():
    table = json.loads((PACKAGE / "data/event_table.json").read_text(encoding="utf-8"))
    row = next(e for e in table["events"] if e["id"] == 108201)
    option = events.by_id()[108201]["options"][0]
    assert option["hint"] == "Weakens the Poise Passive 「Adaptation」 for this Encounter"
    assert option["hint"] == row["options"][0]["hint"]
    assert option["hint_zh"] == "選擇後，本場戰鬥中弱化呼吸法相關被動技能 “適應”"


def test_the_events_gift_names_come_from_the_gift_table():
    gift = events.book()["gifts"]["9001"]
    assert gift == {"en": "Hellterfly's Dream", "zh": "地獄蝶之夢", "keyword": "Burn", "tier": 2}
    assert events.book()["zh_release"] == "2026111401"


def test_a_gift_has_names_effects_and_its_recipe():
    g = gifts.book()[9001]
    assert (g["en"], g["zh"], g["cn"], g["keyword"], g["tier"]) == ("Hellterfly's Dream", "地獄蝶之夢", "地狱蝶之梦", "Burn", 2)
    assert g["desc_zh"].startswith("透過技能效果使已帶有「燒傷」")
    assert g["plus_en"].startswith("When applying 「Burn」 Potency")
    assert gifts.book()[9083]["recipe"]["groups"][0] == {"ids": [9105, 9110, 9116, 9121, 9126, 9131, 9136], "need": 2}
    assert "recipe" not in gifts.book()[9001]


def test_a_trial_is_keyed_by_its_english_name_with_its_table_row_and_its_text():
    table = trials.book()
    assert table["model"]["level"] == 0.36
    trial = table["trials"]["Offense Level Up I"]
    assert trial["id"] == "MD511" and trial["effects"] == {"offense": 1}
    assert (trial["cn"], trial["zh"], trial["desc_en"], trial["desc_cn"]) == ("攻击等级强化I", "攻擊等級強化I", "Offense Level +1", "攻击等级+1")
    assert len(table["trials"]) == 105
