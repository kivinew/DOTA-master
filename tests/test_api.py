# -*- coding: utf-8 -*-
"""Тесты Flask API через test_client (без запуска сервера и без сети).

Используются только read-only ручки (/api/games, /api/stats, /api/hero, /api/errors, /api/fresh_matches) — живые запросы
к OpenDota здесь не выполняются.
"""

import app as webapp


def _client():
    return webapp.app.test_client()


def test_api_games_pagination():
    d = _client().get("/api/games?page=1&per_page=5").get_json()
    assert d["status"] == "success"
    assert (d["page"], d["per_page"]) == (1, 5)
    assert d["total"] >= len(d["games"])
    assert len(d["games"]) <= 5
    assert d["total_pages"] >= 1


def test_api_games_second_page_differs():
    c = _client()
    p1 = c.get("/api/games?page=1&per_page=3").get_json()["games"]
    p2 = c.get("/api/games?page=2&per_page=3").get_json()["games"]
    assert p1 and p2
    assert [g.get("match_id") for g in p1] != [g.get("match_id") for g in p2]


def test_api_games_caps_per_page():
    d = _client().get("/api/games?per_page=9999").get_json()
    assert d["per_page"] == 200


def test_api_404_is_json():
    r = _client().get("/api/nope")
    assert r.status_code == 404
    assert r.get_json() == {"status": "error", "message": "Not found"}


def test_api_stats_ok():
    r = _client().get("/api/stats")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert d["stats"]["total_games"] > 0


def test_api_hero_stats():
    r = _client().get("/api/hero/Pugna/stats")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert d["hero"] == "Pugna"
    assert "stats" in d
    assert d["stats"]["games"] > 0


def test_api_hero_analysis():
    r = _client().get("/api/hero/Pugna/analysis")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert d["hero"] == "Pugna"
    assert "analysis" in d
    assert isinstance(d["analysis"], str)


def test_api_hero_games():
    r = _client().get("/api/games/Pugna")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert d["hero"] == "Pugna"
    assert "games" in d
    assert d["total"] > 0


def test_api_errors():
    r = _client().get("/api/errors")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert "errors" in d
    assert "total" in d


def test_api_fresh_matches():
    r = _client().get("/api/fresh_matches")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert "fresh_matches" in d
    assert "account_id" in d


def test_api_auto_update_status():
    r = _client().get("/api/auto-update/status")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "success"
    assert "data" in d
    assert "running" in d["data"]
