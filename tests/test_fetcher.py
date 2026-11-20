# -*- coding: utf-8 -*-
"""Тесты analysis/fetcher.py без сети: нормализация и конвертация SteamID."""

from analysis.fetcher import (
    _steam_id64_to_account_id,
    _account_id_to_steam_id64,
    get_hero_name,
    normalize_open_dota_match,
)


def test_steam_id_roundtrip():
    sid64 = "76561198001364885"
    assert _account_id_to_steam_id64(_steam_id64_to_account_id(sid64)) == int(sid64)


def _raw(**kw):
    base = {"match_id": 123, "match_time": 1700000000, "hero_id": 45,
            "hero_name": "Pugna", "player_slot": 0, "radiant_win": True,
            "kills": 5, "deaths": 3, "assists": 10, "gold_per_min": 600,
            "xp_per_min": 700, "last_hits": 150, "game_mode": 22,
            "lobby_type": 7, "duration": 2400}
    base.update(kw)
    return base


def test_normalize_win_loss_by_side():
    assert normalize_open_dota_match(_raw(), None)["result"] == "win"
    # Dire-слот (128) при победе Radiant — поражение
    assert normalize_open_dota_match(
        _raw(player_slot=128, radiant_win=True), None)["result"] == "loss"


def test_normalize_fields():
    g = normalize_open_dota_match(_raw(), None)
    assert (g["hero"], g["kills"], g["deaths"], g["assists"]) == ("Pugna", 5, 3, 10)
    assert (g["gpm"], g["xpm"], g["last_hits"]) == (600, 700, 150)
    assert g["source"] == "opendota"


def test_normalize_prefers_enriched_player():
    enriched = {"player_data": {0: {"kills": 9, "deaths": 1, "assists": 20,
                                    "gold_per_min": 700, "xp_per_min": 800,
                                    "last_hits": 200, "is_our_player": True,
                                    "is_radiant": True}},
                "radiant_win": True, "duration": 2400,
                "game_mode": 22, "lobby_type": 7}
    g = normalize_open_dota_match(_raw(kills=0), enriched)
    assert (g["kills"], g["deaths"], g["assists"]) == (9, 1, 20)


def test_hero_name_fallback_table():
    assert get_hero_name(45) == "Pugna"
    assert get_hero_name(999999) == "Hero_999999"
