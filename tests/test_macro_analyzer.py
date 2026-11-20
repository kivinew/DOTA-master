# -*- coding: utf-8 -*-
"""Тесты analysis/macro_analyzer.py: анализ айтемов и прокачки."""

from analysis import macro_analyzer
from analysis.macro_analyzer import analyze_items, analyze_skill_build


def _fake_match_details() -> dict:
    return {
        "match_id": 8990206260,
        "radiant_score": 44,
        "dire_score": 34,
        "radiant_win": True,
        "duration": 1382,
        "players": [
            {"account_id": 41099157, "player_slot": 0, "hero_id": 6124, "kills": 20, "deaths": 10, "assists": 30, "gold_per_min": 600, "xp_per_min": 700, "last_hits": 100, "denies": 5, "hero_damage": 1200, "tower_damage": 250, "hero_healing": 60, "level": 18, "net_worth": 12000, "win": True, "ability_upgrades_arr": [], "item_0": 0},
            {"account_id": 222, "player_slot": 1, "hero_id": 1, "kills": 8, "deaths": 4, "assists": 12, "gold_per_min": 520, "xp_per_min": 610, "last_hits": 60, "denies": 2, "hero_damage": 700, "tower_damage": 120, "hero_healing": 20, "level": 16, "net_worth": 8000, "win": False, "ability_upgrades_arr": [], "item_0": 0},
        ],
    }


def test_analyze_match_returns_team_score(monkeypatch):
    monkeypatch.setattr(macro_analyzer, "get_match_details", lambda mid: _fake_match_details())
    res = macro_analyzer.analyze_match(8990206260)
    assert res["radiant_score"] == 44
    assert res["dire_score"] == 34
    assert res["radiant_win"] is True


def test_item_notes_scoped_to_hero():
    # У героя без проверок (Kez) не должны выдаваться советы заведённые под Pugna
    res = analyze_items([0, 0, 0, 0, 0, 0], 0, 145)
    assert res["items"] == []
    assert res["notes"] == []


def test_item_notes_for_pugna_when_key_items_missing():
    res = analyze_items([0, 0, 0, 0, 0, 0], 0, 45)
    assert len(res["notes"]) == 2
    assert all("Aghanim" in n or "Aether" in n for n in res["notes"])


def test_item_notes_absent_when_key_items_present():
    res = analyze_items([119, 232, 116, 108, 0, 0], 0, 45)
    assert res["notes"] == []


def test_skill_build_default_hero_not_pugna():
    # Дефолт героя не должен быть Pugna (45) молча для всех
    res = analyze_skill_build([])
    assert res["build"] == []
    assert "Нет данных" in res["notes"][0]
