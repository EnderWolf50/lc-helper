"""settings.json is the user's to edit, and an older or newer lc-helper may have written it."""

import json

from lc_helper import app as ui


def load(tmp_path, monkeypatch, saved):
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    ui.SETTINGS.write_text(json.dumps(saved), encoding="utf-8")
    return ui.load_settings()


def test_an_old_infinite_guard_becomes_the_whole_battle_guard(tmp_path, monkeypatch):
    settings = load(tmp_path, monkeypatch, {"guard": 3, "forever": True})
    assert (settings["guard_mode"], settings["guard"]) == ("forever", 3) and "forever" not in settings


def test_old_guard_turns_become_a_guard_of_the_first_turns(tmp_path, monkeypatch):
    settings = load(tmp_path, monkeypatch, {"guard": 2, "forever": False})
    assert (settings["guard_mode"], settings["guard"]) == ("turns", 2)


def test_no_old_guard_turns_is_no_guard(tmp_path, monkeypatch):
    settings = load(tmp_path, monkeypatch, {"guard": 0, "forever": False})
    assert (settings["guard_mode"], settings["guard"]) == ("none", 1), "a count of 0 turns falls back to 1"


def test_an_old_main_keyword_becomes_the_first_and_only_one(tmp_path, monkeypatch):
    assert load(tmp_path, monkeypatch, {"keyword": "Charge"})["keywords"] == ["Charge"]
    assert load(tmp_path, monkeypatch, {"keyword": None})["keywords"] == []
    assert "keyword" not in load(tmp_path, monkeypatch, {"keyword": "Charge"})


def test_an_old_folded_window_opens_folded_and_an_unfolded_one_as_a_fresh_one(tmp_path, monkeypatch):
    assert load(tmp_path, monkeypatch, {"compact": True})["open_sections"] == []
    assert load(tmp_path, monkeypatch, {"compact": False})["open_sections"] == ["event"], "the default"
    assert "compact" not in load(tmp_path, monkeypatch, {"compact": True})


def test_todays_keys_win_over_old_ones_left_beside_them(tmp_path, monkeypatch):
    settings = load(tmp_path, monkeypatch, {"guard_mode": "none", "guard": 4, "forever": True, "keywords": ["Burn"],
                                            "keyword": "Bleed", "open_sections": ["gift"], "compact": False})
    assert (settings["guard_mode"], settings["keywords"], settings["open_sections"]) == ("none", ["Burn"], ["gift"])


def test_values_outside_their_choices_fall_back(tmp_path, monkeypatch):
    settings = load(tmp_path, monkeypatch, {"guard_mode": "sometimes", "guard": "x", "keywords": "Burn",
                                            "open_sections": ["shop", "gift", "gift", {"x": 1}]})
    assert (settings["guard_mode"], settings["guard"], settings["keywords"], settings["open_sections"]) == \
        ("none", 1, [], ["gift"])
    keywords = load(tmp_path, monkeypatch, {"keywords": ["Fire", "Bleed", "Burn", "Bleed", 3, None]})["keywords"]
    assert keywords == ["Bleed", "Burn"], "known ones, once each, in the user's order"


def test_a_fresh_window_guards_nothing_recommends_nothing_and_opens_the_event_section(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "SETTINGS", tmp_path / "settings.json")
    settings = ui.load_settings()
    assert (settings["guard_mode"], settings["keywords"], settings["open_sections"]) == ("none", [], ["event"])
