# -*- coding: utf-8 -*-
"""Тесты Flask API через test_client (без запуска сервера и без сети).

Используются только read-only ручки (/api/games, /api/stats, /api/hero, /api/errors, /api/fresh_matches) — живые запросы
к OpenDota здесь не выполняются.
"""

import json

import pytest

import app as webapp
from analysis import stats_engine


@pytest.fixture(autouse=True)
def seeded_game_history(tmp_path, monkeypatch):
    """Keep API tests deterministic and independent of ignored local game data."""
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    records = []
    for index in range(7):
        records.append({
            "match_id": 900000 + index,
            "date": f"2026-11-{20 - index:02d}T12:30:00",
            "hero": "Pugna" if index < 5 else "Axe",
            "result": "win" if index % 2 == 0 else "loss",
            "kills": 6 + index, "deaths": 2 + index % 3, "assists": 9,
            "role": "support", "game_mode": 1, "gpm": 420 + index,
            "xpm": 510 + index, "last_hits": 80 + index, "rotl": 0,
            "notes": "",
        })
    (games_dir / "games.json").write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr(stats_engine, "GAMES_DIR", str(games_dir))
    stats_engine._invalidate_cache()
    yield
    stats_engine._invalidate_cache()


def _client():

    return webapp.app.test_client()


def test_match_page_fetches_details_only_once(monkeypatch):
    from analysis import macro_analyzer

    calls = []
    monkeypatch.setattr(stats_engine, "get_games", lambda: [])
    monkeypatch.setattr(macro_analyzer, "get_match_details", lambda match_id: calls.append(match_id) or None)
    response = _client().get("/match/9098079575")
    assert response.status_code == 404
    assert calls == [9098079575]


def test_games_and_errors_pages_are_reachable():
    client = _client()
    for path in ("/games", "/errors"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.mimetype == "text/html"


def test_dashboard_nav_has_no_pugna_shortcut(monkeypatch):
    monkeypatch.setattr(webapp, "load_fresh_matches", lambda: {"fresh_matches": [], "account_id": None})
    html = _client().get("/").get_data(as_text=True)
    nav = html.split("<nav class=\"nav-bar\">", 1)[1].split("</nav>", 1)[0]
    assert 'href="/games"' in nav
    assert 'href="/errors"' in nav
    assert "/hero/Pugna" not in nav


def test_theme_switch_uses_one_layout_stylesheet(monkeypatch):
    monkeypatch.setattr(webapp, "load_fresh_matches", lambda: {"fresh_matches": [], "account_id": None})
    html = _client().get("/").get_data(as_text=True)
    assert "css/dota.css" in html
    assert "dota-light-theme.css" not in html


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


def test_api_date_to_includes_matches_from_that_calendar_day():
    d = _client().get("/api/games?hero=Pugna&date_to=2026-11-20&per_page=200").get_json()
    assert d["total"] == 5
    assert any(game["date"].startswith("2026-11-20") for game in d["games"])


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


def test_api_validates_against_catalog_not_player_history():
    r = _client().get("/api/hero/Invoker/stats")
    assert r.status_code == 200
    assert r.get_json()["stats"]["games"] == 0


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
