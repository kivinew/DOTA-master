#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOTA_MASTER — единая загрузка матчей из OpenDota в games.json.

Заменяет fetch_fresh.py, fetch_opendota_fresh.py, fetch_steam.py,
fetch_web_matches.py одним скриптом с выбором источника.

ВНИМАНИЕ: старые fetch-скрипты писали в scripts/games/games.json — теневую
копию, расходившуюся с основной базой games/games.json. Этот скрипт пишет
только в корень проекта через analysis.* (дедупликация по match_id).

Источники (--source):
  web — быстрый: recentMatches + догоняющий запрос (без деталей матча);
  api — медленный, но богатый: детали каждого /matches/{id} (KDA/GPM/XPM/дpафт).
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.config import ACCOUNT_ID  # noqa: E402


def _resolve_account_id(args) -> int | None:
    """--account-id напрямую или --steam-id64 (17 цифр) → account_id."""
    from analysis.fetcher import _steam_id64_to_account_id, resolve_steam_profile

    if args.account_id:
        return int(args.account_id)
    sid = (args.steam_id64 or "").strip()
    if not sid:
        return int(ACCOUNT_ID)
    if sid.isdigit() and len(sid) == 17:
        aid = _steam_id64_to_account_id(sid)
        print(f"  SteamID64 -> account_id={aid}")
        return aid
    print("  Пробую vanity URL (нужен STEAM_API_KEY)...")
    aid = resolve_steam_profile(sid)
    if aid is None:
        print("  Не удалось определить account_id.")
        return None
    return aid


def main() -> None:
    ap = argparse.ArgumentParser(description="DOTA_MASTER — загрузка матчей из OpenDota")
    ap.add_argument("--account-id", help="account_id (по умолчанию из DOTA_ACCOUNT_ID)")
    ap.add_argument("--steam-id64", help="SteamID64 из профиля Steam (17 цифр)")
    ap.add_argument("--max", type=int, default=30, help="максимум матчей (по умолчанию 30)")
    ap.add_argument("--source", choices=("web", "api"), default="web",
                    help="web — быстро без деталей, api — медленно с деталями")
    args = ap.parse_args()

    account_id = _resolve_account_id(args)
    if account_id is None:
        sys.exit(1)

    if args.source == "web":
        from analysis.web_fetcher import fetch_and_save

        print(f"  Быстрая загрузка (web) для account_id={account_id}, max={args.max}...")
        added = fetch_and_save(str(account_id), max_matches=args.max)
    else:
        from analysis.fetcher import get_player_matches, save_matches

        print(f"  Полная загрузка (api) для account_id={account_id}, max={args.max}...")
        matches = get_player_matches(account_id, max_matches=args.max)
        added = save_matches(matches)
        if matches:
            print("  Первые несколько:")
            for m in matches[:3]:
                print(f"    [{m.get('date')}] {m.get('hero')} | {m.get('result')} | "
                      f"KDA={m.get('kills')}/{m.get('deaths')}/{m.get('assists')} | "
                      f"GPM={m.get('gpm')} XPM={m.get('xpm')}")

    print(f"  Готово: добавлено {added} новых игр в games/games.json")


if __name__ == "__main__":
    main()
