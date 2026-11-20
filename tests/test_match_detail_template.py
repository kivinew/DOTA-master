# -*- coding: utf-8 -*-
"""Regression coverage for compact match summary UI."""

from flask import render_template

from app import app


def test_match_detail_has_one_score_compact_counter_and_item_fallback():
    match = {
        "match_id": 9098079575, "hero_name": "Invoker", "hero_id": 74,
        "result": "win", "radiant_win": True, "radiant_score": 24, "dire_score": 18,
        "tips": [], "skill_build": {"build": [], "notes": []},
        "item_build": {"items": [{"id": "1", "name": "Blink"}], "notes": []},
        "kills": 4, "deaths": 2, "assists": 10, "kda": 7,
        "gpm": 500, "xpm": 600, "dpm": 300, "lhpm": 4,
        "tower_damage": 1000, "tower_part": 20, "kill_part": 30,
        "damage_part": 25, "gpm_part": 20, "xpm_part": 20, "lh_part": 20,
        "team_avg": {"gpm": 450, "xpm": 550, "deaths": 5},
        "mvp_radiant": None, "mvp_dire": None,
    }
    with app.test_request_context("/match/9098079575"):
        html = render_template(
            "match_detail.html", match=match, picks_bans=[],
            counter_list=["Axe", "Invoker"], primary="Axe",
        )

    assert html.count("final-score") == 1
    assert "counter-matchup" in html
    assert "item-tooltip" in html
    assert "item_placeholder.svg" in html
    assert "/static/items/blink.png" in html
