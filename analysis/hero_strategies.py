# -*- coding: utf-8 -*-
"""Hero-specific strategy and win/loss factor analysis."""

import statistics
import json
import os

from collections import Counter, defaultdict
from typing import Optional

from .stats_engine import get_games, hero_stats, global_stats


def _load_counter_map():
    """Загрузить карту героев и их контрптиков из data/hero_counters.json (кэш)."""
    _COUNTER_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "hero_counters.json")
    if not os.path.exists(_COUNTER_CACHE_PATH):
        return {}
    try:
        with open(_COUNTER_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def analyze_hero_factors(hero: str, min_games: int = 3) -> Optional[dict]:
    """
    For a given hero, compare winning games vs losing games to reveal what works.
    Returns factors dict or None if not enough games.
    """
    stats = hero_stats(hero)
    games = stats.get("game_list", [])
    if len(games) < min_games:
        return {"hero": hero, "enough_games": False, "games": len(games)}

    wins = [g for g in games if g["result"] == "win"]
    losses = [g for g in games if g["result"] == "loss"]

    if not wins or not losses:
        return {
            "hero": hero,
            "enough_games": True,
            "games": len(games),
            "wins": len(wins),
            "losses": len(losses),
            "note": "All wins or all losses — no comparison possible",
        }

    # Averages for winning and losing games
    win_kills = statistics.mean([g["kills"] for g in wins])
    loss_kills = statistics.mean([g["kills"] for g in losses])
    win_deaths = statistics.mean([g["deaths"] for g in wins])
    loss_deaths = statistics.mean([g["deaths"] for g in losses])
    win_assists = statistics.mean([g["assists"] for g in wins])
    loss_assists = statistics.mean([g["assists"] for g in losses])
    win_rotl = statistics.mean([g["rotl"] for g in wins])
    loss_rotl = statistics.mean([g["rotl"] for g in losses])
    win_gpm = statistics.mean([g["gpm"] for g in wins])
    loss_gpm = statistics.mean([g["gpm"] for g in losses])
    win_xpm = statistics.mean([g["xpm"] for g in wins])
    loss_xpm = statistics.mean([g["xpm"] for g in losses])
    win_lhas = statistics.mean([g["last_hits"] for g in wins])
    loss_lhas = statistics.mean([g["last_hits"] for g in losses])
    win_duration = statistics.mean([g.get("duration", 0) for g in wins])
    loss_duration = statistics.mean([g.get("duration", 0) for g in losses])

    # Count by draft composition (simplified)
    win_drafts = Counter()
    loss_drafts = Counter()
    for g in wins:
        if g.get("draft_allies"):
            for h in g["draft_allies"].split(","):
                win_drafts[h.strip()] += 1
    for g in losses:
        if g.get("draft_allies"):
            for h in g["draft_allies"].split(","):
                loss_drafts[h.strip()] += 1

    # Common allies in wins
    top_win_allies = win_drafts.most_common(5)
    top_loss_allies = loss_drafts.most_common(5)

    return {
        "hero": hero,
        "enough_games": True,
        "games": len(games),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(stats["win_rate"], 1),
        "factors": {
            "kills": round(win_kills - loss_kills, 2),
            "deaths": round(win_deaths - loss_deaths, 2),
            "assists": round(win_assists - loss_assists, 2),
            "rotl": round(win_rotl - loss_rotl, 2),
            "gpm": round(win_gpm - loss_gpm, 2),
            "xpm": round(win_xpm - loss_xpm, 2),
            "last_hits": round(win_lhas - loss_lhas, 2),
            "duration": round(win_duration - loss_duration, 1),
        },
        "top_win_allies": top_win_allies,
        "top_loss_allies": top_loss_allies,
    }


def hero_strategies_report(hero: str) -> str:
    """Generate a text report for a single hero's strategy."""
    analysis = analyze_hero_factors(hero)
    if analysis is None or not analysis.get("enough_games"):
        return f"Недостаточно данных для героя {hero} (играй как минимум 3 игры)."

    lines = [f"# Стратегия для {hero}", ""]
    stats = hero_stats(hero)
    lines.append(f"**Всего игр:** {stats['games']}")
    lines.append(f"**Побед:** {stats['wins']}  **Поражений:** {stats['losses']}")
    lines.append(f"**Win Rate:** {stats['win_rate']}%")
    lines.append(f"**Средний KDA:** {stats['avg_kd']}")
    lines.append(f"**Средний RoTL:** {stats['avg_rotl']}")
    lines.append(f"**Средний GPM/XPM:** {stats['avg_gpm']} / {stats['avg_xpm']}")
    lines.append(f"**Средний Last Hits:** {stats['avg_last_hits']}")
    lines.append("")

    factors = analysis.get("factors")
    if factors:
        lines.append("## Что отличает победы от поражений")
        lines.append("| Показатель | Разница (win - loss) |")
        lines.append("|---|---|")
        for key, val in factors.items():
            if val > 0:
                lines.append(f"| {key} | +{val} (лучше в победах) |")
            elif val < 0:
                lines.append(f"| {key} | {val} (хуже в победах) |")
            else:
                lines.append(f"| {key} | {val} (без разницы) |")
        lines.append("")

    top_win = analysis.get("top_win_allies", [])
    top_loss = analysis.get("top_loss_allies", [])
    if top_win or top_loss:
        lines.append("## Частые союзники")
        lines.append("**В победах:** " + ", ".join(f"{h} ({c})" for h, c in top_win))
        lines.append("**В поражениях:** " + ", ".join(f"{h} ({c})" for h, c in top_loss))
        lines.append("")

    lines.append("## Выводы")
    death_factor = factors.get("deaths", 0) if factors else 0
    gpm_factor = factors.get("gpm", 0) if factors else 0
    rotl_factor = factors.get("rotl", 0) if factors else 0

    advice = []
    if death_factor > 0:
        advice.append(f"В победах больше смертей (на {round(death_factor, 1)} больше в среднем) — возможно, агрессивный стиль работает.")
    if death_factor < 0:
        advice.append(f"В победах меньше смертей (на {round(abs(death_factor), 1)} меньше в среднем) — позиционирование играет роль.")

    if gpm_factor > 0:
        advice.append(f"В победах выше GPM (на +{round(gpm_factor, 1)}) — фарм критичен.")
    if gpm_factor < 0:
        advice.append(f"В победах ниже GPM (на {round(gpm_factor, 1)}) — возможно, статистика сбита или GPM не решает.")

    if rotl_factor > 0:
        advice.append(f"В победах выше RoTL (на +{round(rotl_factor, 1)}) — урон по линии помогает.")

    for a in advice:
        lines.append(f"- {a}")

    if not advice:
        lines.append("- Нет чётких различий между победными и проигрышными играми — нужно больше данных или фокус на таких факторах, как team fight и поддержка.")

    lines.append("")
    return "\n".join(lines)


# ── Контрптика: герои, контрирующие данному герою ──────────────────────────

_COUNTER_MAP = _load_counter_map()


def get_counter_heroes(hero: str) -> list[str]:
    """Вернуть список героев, контрирующих данному герою."""
    raw = _COUNTER_MAP.get(hero)
    if not raw:
        return []
    if isinstance(raw, dict):
        return raw.get("counters") or []
    return raw if isinstance(raw, list) else []


def get_primary_counter(hero: str) -> str | None:
    """Вернуть основной (первый) контрптик или None."""
    counters = get_counter_heroes(hero)
    return counters[0] if counters else None


def counter_note(hero: str) -> str:
    """Вернуть краткую причину, почему данные герои контрируют данному герою."""
    raw = _COUNTER_MAP.get(hero)
    if isinstance(raw, dict):
        return raw.get("note") or ""
    return ""
