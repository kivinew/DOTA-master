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


@pytest.mark.parametrize(("enemy_hero_id", "expected_counter"), [(2, None), (1, "Anti-Mage")])
def test_match_counterpick_must_be_on_enemy_roster(monkeypatch, enemy_hero_id, expected_counter):
    from analysis import macro_analyzer

    details = {"players": [
        {"account_id": webapp.ACCOUNT_ID, "player_slot": 0, "hero_id": 45},
        {"account_id": 123, "player_slot": 128, "hero_id": enemy_hero_id},
    ], "picks_bans": []}
    monkeypatch.setattr(stats_engine, "get_games", lambda: [])
    monkeypatch.setattr(macro_analyzer, "get_match_details", lambda match_id: details)
    monkeypatch.setattr(macro_analyzer, "analyze_match", lambda *args, **kwargs: {"hero_name": "Pugna"})
    monkeypatch.setattr(webapp, "render_template", lambda template, **context: webapp.jsonify({
        "counter_list": context["counter_list"], "primary": context["primary"]
    }))

    response = _client().get("/match/9098079575")
    assert response.status_code == 200
    if expected_counter:
        assert response.json["counter_list"] == [expected_counter]
        assert response.json["primary"] == expected_counter
    else:
        assert response.json["counter_list"] == []
        assert response.json["primary"] is None


def test_games_and_errors_pages_are_reachable():
    client = _client()
    for path in ("/games", "/games/", "/errors", "/errors/"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.mimetype == "text/html"


def test_games_and_errors_accept_legacy_incomplete_records(monkeypatch):
    records = [{"match_id": "12345", "date": "2026-11-20", "hero": "Invoker",
                "result": "loss", "K": "1", "D": "9", "A": "2"}]
    monkeypatch.setattr(webapp, "get_games", lambda: records)
    monkeypatch.setattr(stats_engine, "get_games", lambda: records)
    client = _client()
    assert client.get("/games").status_code == 200
    errors = client.get("/errors")
    assert errors.status_code == 200
    assert "9 смертей" in errors.get_data(as_text=True)


def test_dashboard_nav_has_no_pugna_shortcut(monkeypatch):
    monkeypatch.setattr(webapp, "load_fresh_matches", lambda: {"fresh_matches": [], "account_id": None})
    html = _client().get("/").get_data(as_text=True)
    nav = html.split("<nav class=\"nav-bar\">", 1)[1].split("</nav>", 1)[0]
    assert 'href="/games' in nav
    assert 'href="/errors' in nav
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


def test_games_rows_are_clickable_with_literal_match_id():
    """Строка игры открывает /match/<id>: id подставляется Jinja, не JS-переменной."""
    html = _client().get("/games").get_data(as_text=True)
    assert "onclick=\"window.location.href='/match/900000'" in html
    assert "+ g.match_id" not in html
    assert "tabindex=\"0\"" in html


def test_macro_page_falls_back_to_local_games_when_opendota_is_down(monkeypatch):
    """Сеть/API недоступны — /macro считается по локальной базе с баннером."""
    from analysis import macro_analyzer

    monkeypatch.setattr(macro_analyzer, "get_recent_matches_batch", lambda *a, **kw: [])
    response = _client().get("/macro")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "OpenDota сейчас недоступен" in body
    assert "Сводка (7 матчей)" in body


def test_macro_page_empty_state_when_no_data_at_all(monkeypatch, tmp_path):
    """Ни API, ни локальной базы — понятное пустое состояние, а не 500."""
    from analysis import macro_analyzer

    monkeypatch.setattr(stats_engine, "get_games", lambda: [])
    monkeypatch.setattr(macro_analyzer, "get_recent_matches_batch", lambda *a, **kw: [])
    response = _client().get("/macro")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Нет данных для анализа" in body
    assert "Обновить матчи" in body


def test_report_page_falls_back_to_local_games(monkeypatch):
    """Отчёт строится по локальной базе, когда OpenDota недоступен."""
    from analysis import report_generator

    monkeypatch.setattr(report_generator, "get_recent_matches_batch", lambda *a, **kw: [])
    response = _client().get("/report")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "OpenDota сейчас недоступен" in body
    assert "Сводка (7 матчей)" in body


def test_macro_page_renders_summary_for_recent_matches(monkeypatch):
    """Нормальный ответ API: сводка строится по analyze_all_matches-структуре."""
    from analysis import macro_analyzer

    fake = [
        {"match_id": 1, "hero_id": 74, "player_slot": 0, "radiant_win": True, "duration": 2400,
         "kills": 8, "deaths": 3, "assists": 12, "gold_per_min": 620, "xp_per_min": 730,
         "last_hits": 240, "denies": 12, "hero_damage": 22000, "tower_damage": 3200,
         "hero_healing": 0, "level": 22, "net_worth": 21000},
        {"match_id": 2, "hero_id": 45, "player_slot": 128, "radiant_win": True, "duration": 2100,
         "kills": 3, "deaths": 9, "assists": 7, "gold_per_min": 380, "xp_per_min": 430,
         "last_hits": 70, "denies": 2, "hero_damage": 9000, "tower_damage": 300,
         "hero_healing": 0, "level": 16, "net_worth": 11000},
    ]
    monkeypatch.setattr(macro_analyzer, "get_recent_matches_batch", lambda *a, **kw: fake)
    response = _client().get("/macro")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Сводка (2 матчей)" in body
    assert "50.0%" in body


def test_games_today_shortcut_uses_local_player_time():
    """«Сегодня» фильтрует по дате в часовом поясе игрока (UTC+7), не UTC."""
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=7))
    today = datetime.now(tz).date().isoformat()
    records = [
        {"match_id": 1, "date": f"{today}T09:15:00", "hero": "Pugna", "result": "win",
         "kills": 6, "deaths": 2, "assists": 9, "game_mode": 22},
        {"match_id": 2, "date": "2020-01-01T09:15:00", "hero": "Axe", "result": "loss",
         "kills": 2, "deaths": 8, "assists": 3, "game_mode": 22},
    ]
    stats_engine._save_games(records)

    page = _client().get("/games").get_data(as_text=True)
    assert "Сегодня (1)" in page

    filtered = _client().get(f"/games?date_from={today}&date_to={today}").get_data(as_text=True)
    assert filtered.count("match-row-clickable") == 1
    # Имена героев есть и в выпадающем списке фильтра — проверяем блок таблицы.
    table = filtered.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert "Pugna" in table and "Axe" not in table


def test_fresh_page_redirects_to_games_live_section():
    """/fresh объединён с /games: старый адрес ведёт на секцию живых матчей."""
    client = _client()
    plain = client.get("/fresh")
    assert plain.status_code == 302
    assert plain.headers["Location"].endswith("/games#live")

    refresh = client.get("/fresh?refresh=1")
    assert refresh.status_code == 302
    assert refresh.headers["Location"].endswith("/games?refresh=1#live")


def test_games_page_contains_live_matches_section(monkeypatch):
    """На /games есть секция живых матчей (бывшая /fresh) и история."""
    monkeypatch.setattr(webapp, "load_fresh_matches", lambda: {
        "fresh_matches": [{
            "hero": "Pugna", "match_id": "770000001", "time_ago": "5 мин назад",
            "result": "win", "K": 9, "D": 2, "A": 14, "duration": "40:00",
            "side": "Radiant", "game_mode": 22, "date": "2026-11-21 18:00",
        }],
        "account_id": 41099157, "live": True,
    })
    body = _client().get("/games").get_data(as_text=True)
    assert "Свежие матчи из OpenDota (1)" in body
    assert "Живой ответ OpenDota" in body
    assert "770000001" in body
    assert "/games?refresh=1#live" in body
    # история из базы тоже на месте
    assert "match-row-clickable" in body


def test_navigation_has_no_separate_fresh_entry():
    """В меню больше нет отдельного пункта «Свежие» — страница объединена."""
    html = _client().get("/games").get_data(as_text=True)
    nav = html.split('<nav class="nav-bar">', 1)[1].split("</nav>", 1)[0]
    assert "/fresh" not in nav
    assert 'href="/games' in nav
