# -*- coding: utf-8 -*-
"""Тесты analysis/stats_engine.py: хранилище, агрегация, детектор ошибок."""

import csv

from analysis.stats_engine import (
    add_game,
    import_csv,
    get_games,
    get_hero_games,
    hero_stats,
    global_stats,
    detect_errors,
)


def _mk(hero="Pugna", result="win", kills=8, deaths=2, assists=10,
        rotl=20.0, last_hits=150, gpm=600.0, xpm=700.0):
    return add_game(
        hero=hero, role="mid", result=result,
        kills=kills, deaths=deaths, assists=assists, rotl=rotl,
        last_hits=last_hits, gpm=gpm, xpm=xpm,
    )


def test_add_game_normalizes_fields(isolated_games):
    g = _mk(hero="  pugna ", result="WIN")
    assert g["hero"] == "Pugna"
    assert g["result"] == "win"
    assert g["role"] == "mid"
    assert len(get_games()) == 1
    assert len(get_hero_games("Pugna")) == 1
    assert get_hero_games("Warlock") == []


def test_global_and_hero_stats(isolated_games):
    _mk("Pugna", "win")
    _mk("Pugna", "loss", kills=4, deaths=10, assists=6)
    _mk("Warlock", "win")

    s = global_stats()
    assert s["total_games"] == 3
    assert (s["total_wins"], s["total_losses"]) == (2, 1)
    assert s["win_rate"] == round(2 / 3 * 100, 1)
    assert [h["hero"] for h in s["by_hero"]][0] == "Pugna"  # сортировка по играм

    h = hero_stats("Pugna")
    assert (h["games"], h["wins"], h["losses"]) == (2, 1, 1)
    assert h["win_rate"] == 50.0
    assert hero_stats("Invoker") == {"hero": "Invoker", "games": 0}


def test_import_csv_dedupes(isolated_games, tmp_path):
    csv_path = tmp_path / "games.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "date", "hero", "role", "result", "kills", "deaths", "assists",
            "rotl", "last_hits", "gpm", "xpm", "game_mode",
            "draft_allies", "draft_enemies", "notes",
        ])
        w.writeheader()
        w.writerow({"date": "2026-09-20", "hero": "Pugna", "role": "mid",
                    "result": "win", "kills": 8, "deaths": 2, "assists": 10,
                    "rotl": 20, "last_hits": 150, "gpm": 600, "xpm": 700,
                    "game_mode": "22", "draft_allies": "", "draft_enemies": "",
                    "notes": ""})
    assert import_csv(str(csv_path)) == 1
    assert import_csv(str(csv_path)) == 0  # повтор — дубликат, не добавляем


def _game(**kw):
    base = {"hero": "Pugna", "result": "win", "kills": 8, "deaths": 2,
            "assists": 10, "rotl": 20.0, "gpm": 600.0, "xpm": 700.0}
    base.update(kw)
    return base


def test_detect_errors_clean_game():
    assert detect_errors(_game()) == []


def test_detect_errors_skips_unknown_rotl():
    # rotl == 0.0 пишет fetcher при отсутствии данных в OpenDota — не ошибка
    assert detect_errors(_game(rotl=0.0)) == []


def test_detect_errors_flags_known_low_rotl():
    errs = detect_errors(_game(rotl=5.0))
    assert any("RoTL" in e for e in errs)


def test_detect_errors_flags_feeding_and_low_kda():
    assert any("смертей" in e for e in detect_errors(_game(deaths=9)))
    errs = detect_errors(_game(result="loss", kills=0, deaths=10, assists=1))
    assert any("KDA" in e for e in errs)
