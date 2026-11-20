# -*- coding: utf-8 -*-
"""Тесты analysis/hero_strategies.py: порог данных и направление советов."""

from analysis.hero_strategies import analyze_hero_factors, hero_strategies_report
from analysis.stats_engine import add_game


def _mk(result, kills, deaths, assists, gpm=600.0):
    return add_game(hero="Pugna", role="mid", result=result, kills=kills,
                    deaths=deaths, assists=assists, rotl=20.0, last_hits=150,
                    gpm=gpm, xpm=700.0)


def test_report_needs_min_games(isolated_games):
    _mk("win", 8, 2, 10)
    assert "Недостаточно данных" in hero_strategies_report("Pugna")


def test_deaths_advice_direction(isolated_games):
    # В победах смертей МЕНЬШЕ — совет должен говорить «меньше», не «больше»
    _mk("win", 8, 2, 10)
    _mk("win", 9, 3, 11)
    _mk("loss", 4, 10, 6)
    _mk("loss", 5, 11, 5)

    a = analyze_hero_factors("Pugna")
    assert a["enough_games"] is True
    assert a["factors"]["deaths"] < 0  # win − loss отрицателен

    assert "меньше смертей" in hero_strategies_report("Pugna")


def test_all_wins_no_comparison(isolated_games):
    _mk("win", 8, 2, 10)
    _mk("win", 9, 3, 11)
    _mk("win", 7, 1, 12)
    a = analyze_hero_factors("Pugna")
    assert "note" in a  # только победы — сравнивать не с чем
