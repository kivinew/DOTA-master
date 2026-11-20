# -*- coding: utf-8 -*-
"""Тесты merge_games и конвертера fresh_matches (scripts/import_matches.py)."""

from analysis.stats_engine import merge_games, get_games
from scripts.import_matches import (
    fresh_view_to_game,
    parse_time_ago,
    parse_duration,
)


def _game(**kw):
    base = {"date": "2026-09-20", "hero": "Pugna", "role": "", "result": "win",
            "kills": 5, "deaths": 3, "assists": 10, "rotl": 0.0, "last_hits": 0,
            "gpm": 0, "xpm": 0, "game_mode": "", "draft_allies": "",
            "draft_enemies": "", "notes": ""}
    base.update(kw)
    return base


def test_merge_dedupes_by_match_id(isolated_games):
    assert merge_games([_game(match_id=111)]) == 1
    assert merge_games([_game(match_id=111)]) == 0
    assert len(get_games()) == 1


def test_merge_str_and_int_match_id_are_same(isolated_games):
    assert merge_games([_game(match_id=222)]) == 1
    assert merge_games([_game(match_id="222")]) == 0  # str из fresh-файла


def test_merge_csv_key_fallback_without_match_id(isolated_games):
    assert merge_games([_game()]) == 1
    assert merge_games([_game()]) == 0
    assert merge_games([_game(kills=9)]) == 1  # другой K/D — новая игра


def test_fresh_view_to_game():
    m = {"hero": "Pugna", "match_id": "8997290205", "time_ago": "28 minutes ago",
         "result": "win", "K": 2, "D": 2, "A": 15, "duration": "26:44",
         "side": "Dire", "game_mode": "Turbo Crusader [5]"}
    g = fresh_view_to_game(m)
    assert g["hero"] == "Pugna"
    assert g["match_id"] == 8997290205
    assert (g["kills"], g["deaths"], g["assists"]) == (2, 2, 15)
    assert g["source"] == "opendota_web"
    assert len(g["date"]) == 10  # YYYY-MM-DD


def test_parse_helpers():
    assert parse_duration("26:44") == 26 * 60 + 44
    assert parse_duration("bad") == 0
    assert len(parse_time_ago("28 minutes ago")) == 10
    assert len(parse_time_ago("28 мин назад")) == 10
    assert len(parse_time_ago("2 ч назад")) == 10
    assert len(parse_time_ago("только что")) == 10
