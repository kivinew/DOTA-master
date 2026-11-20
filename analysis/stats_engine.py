# -*- coding: utf-8 -*-
"""DOTA_MASTER — движок статистики игр в DOTA 2."""

import csv
import json
import os
import statistics
from datetime import datetime, date as DateType
from collections import defaultdict, Counter
from typing import Any

GAMES_DIR = "games"
DATA_DIR = "data"
REPORTS_DIR = "reports"

if not os.path.isdir(GAMES_DIR):
    os.makedirs(GAMES_DIR, exist_ok=True)
if not os.path.isdir(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.isdir(REPORTS_DIR):
    os.makedirs(REPORTS_DIR, exist_ok=True)


# In-memory cache and indexes
_games_cache: list[dict] | None = None
_match_id_index: dict[str, int] | None = None  # match_id -> index in games list
_hero_index: dict[str, list[int]] | None = None  # hero -> list of indices
_cache_games_dir: str | None = None  # Track which GAMES_DIR the cache belongs to


def _game_path():
    return os.path.join(GAMES_DIR, "games.json")


def _invalidate_cache() -> None:
    """Clear cached games and indexes."""
    global _games_cache, _match_id_index, _hero_index
    _games_cache = None
    _match_id_index = None
    _hero_index = None


def _ensure_cache_valid() -> None:
    """Invalidate cache if GAMES_DIR has changed (e.g., in tests)."""
    global _cache_games_dir
    current_dir = os.path.abspath(GAMES_DIR)
    if _cache_games_dir != current_dir:
        _invalidate_cache()
        _cache_games_dir = current_dir


def _build_indexes(games: list[dict]) -> None:
    """Build in-memory indexes for fast lookups."""
    global _match_id_index, _hero_index
    _match_id_index = {}
    _hero_index = defaultdict(list)
    for i, g in enumerate(games):
        mid = g.get("match_id")
        if mid is not None:
            _match_id_index[str(mid)] = i
        hero = g.get("hero")
        if hero:
            _hero_index[hero.strip().title()].append(i)


def _load_games() -> list[dict]:
    global _games_cache
    _ensure_cache_valid()
    if _games_cache is not None:
        return _games_cache
    path = _game_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            _games_cache = json.load(f)
    else:
        _games_cache = []
    _build_indexes(_games_cache)
    return _games_cache


def _save_games(games: list[dict]) -> None:
    with open(_game_path(), "w", encoding="utf-8") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)
    _invalidate_cache()
    # Re-load to rebuild indexes
    _load_games()


def add_game(
    hero: str,
    role: str,
    result: str,          # 'win' / 'loss'
    kills: int,
    deaths: int,
    assists: int,
    rotl: float,            # rotations per game (уменьшение вражеской линии)
    last_hits: int,
    gpm: float,
    xpm: float,
    game_mode: str = "",
    draft_allies: str = "",
    draft_enemies: str = "",
    notes: str = "",
    date: str = None,
) -> dict:
    """Добавить одну игру в хранилище."""
    if date is None:
        date = DateType.today().isoformat()
    game = {
        "date": date,
        "hero": hero.strip().title(),
        "role": role.strip().lower(),
        "result": result.strip().lower(),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "rotl": rotl,
        "last_hits": last_hits,
        "gpm": gpm,
        "xpm": xpm,
        "game_mode": game_mode.strip(),
        "draft_allies": draft_allies.strip(),
        "draft_enemies": draft_enemies.strip(),
        "notes": notes.strip(),
    }
    games = _load_games()
    games.append(game)
    _save_games(games)
    return game


def import_csv(filepath: str) -> int:
    """Импорт из CSV. Возвращает количество добавленных игр."""
    games = _load_games()
    # Ключи приводим к строкам: в CSV всё строки, в games.json числа —
    # иначе ("8" != 8) и дедупликация молча не срабатывает.
    def _key(date, hero, kills, deaths):
        return (str(date or "").strip(), str(hero or "").strip().title(),
                str(kills).strip(), str(deaths).strip())
    existing_dates = {_key(g["date"], g["hero"], g["kills"], g["deaths"]) for g in games}
    count = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = _key(row.get("date", ""), row.get("hero", ""),
                       row.get("kills", ""), row.get("deaths", ""))
            if key in existing_dates:
                continue
            game = {
                "date": row.get("date", ""),
                "hero": row.get("hero", "").strip().title(),
                "role": row.get("role", "").strip().lower(),
                "result": row.get("result", "loss").strip().lower(),
                "kills": int(row.get("kills", 0) or 0),
                "deaths": int(row.get("deaths", 0) or 0),
                "assists": int(row.get("assists", 0) or 0),
                "rotl": float(row.get("rotl", 0) or 0),
                "last_hits": int(row.get("last_hits", 0) or 0),
                "gpm": float(row.get("gpm", 0) or 0),
                "xpm": float(row.get("xpm", 0) or 0),
                "game_mode": row.get("game_mode", "").strip(),
                "draft_allies": row.get("draft_allies", "").strip(),
                "draft_enemies": row.get("draft_enemies", "").strip(),
                "notes": row.get("notes", "").strip(),
            }
            games.append(game)
            existing_dates.add(key)
            count += 1
    _save_games(games)
    return count


def _dedup_key(game: dict) -> tuple:
    """Ключ дедупликации: всё строками (в CSV числа — строки, в JSON — int)."""
    return (
        str(game.get("date", "") or "").strip(),
        str(game.get("hero", "") or "").strip().title(),
        str(game.get("kills", 0)).strip(),
        str(game.get("deaths", 0)).strip(),
    )


def merge_games(new_games: list[dict]) -> int:
    """Добавить игры с дедупликацией: по match_id (если есть), иначе по CSV-ключу.

    Возвращает число добавленных. На диск пишет только если есть новые.
    """
    games = _load_games()
    # Use pre-built index for match_id lookups
    have_ids = set(_match_id_index.keys()) if _match_id_index else set()
    have_csv = {_dedup_key(g) for g in games}
    added = 0
    for g in new_games:
        g = dict(g)
        if g.get("hero"):
            g["hero"] = str(g["hero"]).strip().title()
        mid = g.get("match_id")
        if (mid is not None and str(mid) in have_ids) or _dedup_key(g) in have_csv:
            continue
        games.append(g)
        added += 1
        if mid is not None:
            have_ids.add(str(mid))
        have_csv.add(_dedup_key(g))
    if added:
        _save_games(games)
    return added


def get_games() -> list[dict]:
    return _load_games()


def get_game_by_match_id(match_id: int | str) -> dict | None:
    """Get a single game by match_id using the index (O(1))."""
    games = _load_games()
    idx = _match_id_index.get(str(match_id)) if _match_id_index else None
    if idx is not None and idx < len(games):
        return games[idx]
    return None


def get_hero_games(hero: str) -> list[dict]:
    hero = hero.strip().title()
    games = _load_games()
    indices = _hero_index.get(hero, []) if _hero_index else []
    return [games[i] for i in indices if i < len(games)]


def hero_stats(hero: str) -> dict:
    games = get_hero_games(hero)
    if not games:
        return {"hero": hero, "games": 0}
    wins = [g for g in games if g["result"] == "win"]
    losses = [g for g in games if g["result"] == "loss"]
    kd = [g["kills"] + g["assists"] - g["deaths"] for g in games]  # упрощённая KDA-разность
    rotls = [g["rotl"] for g in games]
    gpms = [g["gpm"] for g in games]
    xpms = [g["xpm"] for g in games]
    lhas = [g["last_hits"] for g in games]
    deaths_list = [g["deaths"] for g in games]
    return {
        "hero": hero,
        "games": len(games),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(games) * 100, 1),
        "avg_kd": round(statistics.mean(kd), 2) if kd else 0,
        "avg_rotl": round(statistics.mean(rotls), 2) if rotls else 0,
        "avg_gpm": round(statistics.mean(gpms), 1) if gpms else 0,
        "avg_xpm": round(statistics.mean(xpms), 1) if xpms else 0,
        "avg_last_hits": round(statistics.mean(lhas), 1) if lhas else 0,
        "avg_deaths": round(statistics.mean(deaths_list), 1) if deaths_list else 0,
        "max_deaths_in_game": max(deaths_list) if deaths_list else 0,
        "game_list": games,
    }


def global_stats() -> dict:
    games = _load_games()
    if not games:
        return {"total_games": 0}
    wins = [g for g in games if g["result"] == "win"]
    losses = [g for g in games if g["result"] == "loss"]
    kd_vals = [g["kills"] + g["assists"] - g["deaths"] for g in games]
    rotls = [g["rotl"] for g in games]
    gpms = [g["gpm"] for g in games]
    xpms = [g["xpm"] for g in games]
    lhas = [g["last_hits"] for g in games]
    deaths_list = [g["deaths"] for g in games]
    by_hero = defaultdict(list)
    for g in games:
        by_hero[g["hero"]].append(g)
    hero_stats = []
    for h, games_list in by_hero.items():
        h_wins = [g for g in games_list if g["result"] == "win"]
        h_losses = [g for g in games_list if g["result"] == "loss"]
        h_gpms = [g["gpm"] for g in games_list if g.get("gpm")]
        h_xpms = [g["xpm"] for g in games_list if g.get("xpm")]
        h_lh = [g["last_hits"] for g in games_list if g.get("last_hits")]
        h_kd = [g["kills"] + g["assists"] - g["deaths"] for g in games_list]
        hero_stats.append({
            "hero": h,
            "games": len(games_list),
            "wins": len(h_wins),
            "losses": len(h_losses),
            "win_rate": round(len(h_wins) / len(games_list) * 100, 1),
            "avg_kd": round(statistics.mean(h_kd), 2) if h_kd else 0,
            "avg_gpm": round(statistics.mean(h_gpms), 1) if h_gpms else 0,
            "avg_xpm": round(statistics.mean(h_xpms), 1) if h_xpms else 0,
            "avg_lh": round(statistics.mean(h_lh), 1) if h_lh else 0,
        })
    return {
        "total_games": len(games),
        "total_wins": len(wins),
        "total_losses": len(losses),
        "win_rate": round(len(wins) / len(games) * 100, 1),
        "avg_kd": round(statistics.mean(kd_vals), 2) if kd_vals else 0,
        "avg_gpm": round(statistics.mean(gpms), 1) if gpms else 0,
        "avg_xpm": round(statistics.mean(xpms), 1) if xpms else 0,
        "avg_lh": round(statistics.mean(lhas), 1) if lhas else 0,
        "avg_deaths": round(statistics.mean(deaths_list), 1) if deaths_list else 0,
        "by_hero": sorted(hero_stats, key=lambda x: -x["games"]),
    }


def detect_errors(game: dict) -> list[str]:
    """Пометить критические ошибки в одной игре."""
    errors = []
    d = game["deaths"]
    k = game["kills"]
    a = game["assists"]
    rotl = game["rotl"]
    gpm = game["gpm"]
    xpm = game["xpm"]
    # KDA < 0.5 и проигрыш — попадает в неэффективные игры
    if d > 0 and (k + a) / d < 0.5 and game["result"] == "loss":
        errors.append(f"Низкий KDA ({round((k+a)/d, 2)}) в проигравшей игре — выбывание из фокуса")
    # RoTL < 10 — почти отсутствие работы на линии.
    # rotl == 0 означает «нет данных» (OpenDota его не отдаёт, fetcher пишет 0.0),
    # такие игры не помечаем, чтобы не зашумлять отчёт ложными ошибками.
    if 0 < rotl < 10:
        errors.append(f"RoTL={rotl} — почти нет урона по линии, трудно влияет на карту")
    # много смертей до получения опыта (предположительно)
    if d >= 8:
        errors.append(f"{d} смертей — перебор, нужно пересмотреть позиционирование")
    # GPM низкий относительно XPM
    if gpm > 0 and xpm > 0 and gpm < xpm * 0.6:
        errors.append(f"GPM ({gpm}) значительно ниже XPM ({xpm}) — недополучали фарм при наличии доступа к линиям")
    return errors


def analyze_all_games() -> dict:
    games = _load_games()
    out = {
        "total": len(games),
        "errors_summary": {},  # error -> count
        "hero_errors": defaultdict(list),  # hero -> [error_text]
        "strategies": {},  # hero -> {win_factors, loss_factors}
    }
    for g in games:
        errs = detect_errors(g)
        for e in errs:
            out["errors_summary"][e] = out["errors_summary"].get(e, 0) + 1
            out["hero_errors"][g["hero"]].append(f"[{g['date']}] {e}")

    # Построение факторов победы/проигрыша для каждого героя
    by_hero = defaultdict(list)
    for g in games:
        by_hero[g["hero"]].append(g)

    for hero, gs in by_hero.items():
        wins = [g for g in gs if g["result"] == "win"]
        losses = [g for g in gs if g["result"] == "loss"]
        win_games = wins or losses  # чтобы не делить на 0
        # Сравниваем средние
        factors = {}
        if wins and losses:
            factors["kills_gap"] = round(
                statistics.mean([g["kills"] for g in wins]) -
                statistics.mean([g["kills"] for g in losses]), 2)
            factors["deaths_gap"] = round(
                statistics.mean([g["deaths"] for g in wins]) -
                statistics.mean([g["deaths"] for g in losses]), 2)
            factors["rotl_gap"] = round(
                statistics.mean([g["rotl"] for g in wins]) -
                statistics.mean([g["rotl"] for g in losses]), 2)
            factors["gpm_gap"] = round(
                statistics.mean([g["gpm"] for g in wins]) -
                statistics.mean([g["gpm"] for g in losses]), 2)
        else:
            factors["kills_gap"] = factors["deaths_gap"] = factors["rotl_gap"] = factors["gpm_gap"] = None
        out["strategies"][hero] = {
            "win_games": len(wins),
            "loss_games": len(losses),
            "factors": factors,
        }
    return out
