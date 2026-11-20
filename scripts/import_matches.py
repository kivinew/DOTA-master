#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOTA_MASTER — единый импорт матчей в games.json.

Заменяет import_fresh.py + import_fresh_matches.py (у тех нет дедупликации —
повторный запуск плодит дубли, роль угадывается по стороне, match_id теряется).

Источники: --fresh (games/fresh_matches.json, по умолчанию), --csv PATH,
--json PATH (список записей внутреннего формата). Дедупликация через
stats_engine.merge_games: по match_id, иначе по дате/герою/K/D.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.stats_engine import merge_games, get_games, global_stats  # noqa: E402


def parse_time_ago(s: str) -> str:
    """'28 minutes ago' / '28 мин назад' / '2 ч назад' → дата ISO (YYYY-MM-DD)."""
    now = datetime.now()
    if not s:
        return now.date().isoformat()
    s = s.strip().lower()
    if s in ("только что", "just now"):
        return now.date().isoformat()
    m = re.match(r"(\d+)\s*(мин|минут|minutes?)", s)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).date().isoformat()
    m = re.match(r"(\d+)\s*(ч|час|hours?)", s)
    if m or "an hour" in s:
        hours = int(m.group(1)) if m else 1
        return (now - timedelta(hours=hours)).date().isoformat()
    m = re.match(r"(\d+)\s*(дн|дней|days?)", s)
    if m or "day ago" in s:
        days = int(m.group(1)) if m else 1
        return (now - timedelta(days=days)).date().isoformat()
    return now.date().isoformat()


def parse_duration(s: str) -> int:
    """'26:44' → секунды."""
    try:
        mm, ss = str(s).strip().split(":")
        return int(mm) * 60 + int(ss)
    except (ValueError, AttributeError):
        return 0


def fresh_view_to_game(m: dict) -> dict:
    """Запись fresh_matches.json (вид get_fresh_view) → внутренний формат."""
    raw_mid = m.get("match_id")
    try:
        match_id = int(str(raw_mid))
    except (TypeError, ValueError):
        match_id = raw_mid
    return {
        "date": parse_time_ago(m.get("time_ago", "")),
        "hero": str(m.get("hero", "Unknown") or "Unknown"),
        "role": "",  # сторона Radiant/Dire — не роль; не угадываем
        "result": str(m.get("result", "loss") or "loss").lower(),
        "kills": int(m.get("K", 0) or 0),
        "deaths": int(m.get("D", 0) or 0),
        "assists": int(m.get("A", 0) or 0),
        "rotl": 0.0,  # OpenDota не отдаёт — «нет данных», не ошибка
        "last_hits": 0,
        "gpm": 0,
        "xpm": 0,
        "game_mode": str(m.get("game_mode", "") or ""),
        "draft_allies": "",
        "draft_enemies": "",
        "notes": "",
        "match_id": match_id,
        "source": "opendota_web",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="DOTA_MASTER — импорт матчей в games.json")
    ap.add_argument("--fresh", action="store_true",
                    help="импорт из games/fresh_matches.json (по умолчанию)")
    ap.add_argument("--csv", help="импорт из CSV (колонки как в main.py import)")
    ap.add_argument("--json", help="импорт из JSON-списка записей внутреннего формата")
    args = ap.parse_args()

    from analysis.stats_engine import import_csv

    total_added = 0
    if args.csv:
        n = import_csv(args.csv)
        print(f"CSV {args.csv}: добавлено {n}")
        total_added += n
    if args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("games", [])
        n = merge_games(rows)
        print(f"JSON {args.json}: добавлено {n} из {len(rows)}")
        total_added += n
    if args.fresh or not (args.csv or args.json):
        path = os.path.join(PROJECT_ROOT, "games", "fresh_matches.json")
        if not os.path.exists(path):
            print(f"Файл не найден: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = [fresh_view_to_game(m) for m in data.get("fresh_matches", [])]
        n = merge_games(rows)
        print(f"fresh_matches.json: добавлено {n} из {len(rows)}")
        total_added += n

    stats = global_stats()
    print(f"\nДобавлено всего: {total_added}. В базе: {stats.get('total_games', len(get_games()))} игр "
          f"({stats.get('total_wins', '?')}W/{stats.get('total_losses', '?')}L, "
          f"WR={stats.get('win_rate', '?')}%)")


if __name__ == "__main__":
    main()
