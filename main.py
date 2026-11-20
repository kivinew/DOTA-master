# -*- coding: utf-8 -*-
"""DOTA_MASTER — CLI интерфейс: добавление игр, анализ, отчёты, фetch с OpenDota."""

import argparse
import sys
import os
import logging
from datetime import datetime

# Ensure we can import from parent package even when run as script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# UTF-8 для консоли (кириллица в выводе CLI) — до первого print/лога
from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.stats_engine import (
    add_game,
    import_csv,
    get_games,
    get_hero_games,
    hero_stats,
    global_stats,
    detect_errors,
    analyze_all_games,
)
from analysis.hero_strategies import hero_strategies_report
from analysis.config import ACCOUNT_ID as DEFAULT_ACCOUNT_ID
from analysis.fetcher import (
    get_player_matches,
    save_matches,
    resolve_steam_profile,
    get_heroes_list,
    load_heroes_cache,
    _steam_id64_to_account_id,
    BASE_URL,
    _fetch_json,
)
from analysis.auto_update import (
    start_auto_update,
    stop_auto_update,
    get_auto_update_status,
)
import json


def cmd_add(args):
    """Hand-run add with prompts."""
    print("=" * 50)
    print("Добавление игры в DOTA_MASTER")
    print("=" * 50)

    hero = input("Герой (на английском или транслитом): ").strip()
    if not hero:
        print("Герой обязателен.")
        return

    role = input("Роль (carry / mid / offlane / support / soft): ").strip().lower() or "support"
    result = input("Результат (win/loss): ").strip().lower() or "loss"
    if result not in ("win", "loss"):
        print("Результат должен быть win или loss.")
        return

    kills = int(input("Kills (число): ") or 0)
    deaths = int(input("Deaths (число): ") or 0)
    assists = int(input("Assists (число): ") or 0)
    rotl = float(input("RoTL (число): ") or 0)
    last_hits = int(input("Last Hits (число): ") or 0)
    gpm = float(input("GPM (число): ") or 0)
    xpm = float(input("XPM (число): ") or 0)
    game_mode = input("Game Mode (например cm, lrd, lance, etc.): ").strip() or ""
    draft_allies = input("Союзные герои (через запятую): ").strip() or ""
    draft_enemies = input("Вражеские герои (через запятую): ").strip() or ""
    notes = input("Заметки (описание ошибок, мысли): ").strip() or ""

    game = add_game(
        hero=hero,
        role=role,
        result=result,
        kills=kills,
        deaths=deaths,
        assists=assists,
        rotl=rotl,
        last_hits=last_hits,
        gpm=gpm,
        xpm=xpm,
        game_mode=game_mode,
        draft_allies=draft_allies,
        draft_enemies=draft_enemies,
        notes=notes,
    )
    print(f"\nИгра добавлена: {hero} | win_rate={result} | kills={kills} deaths={deaths} assists={assists}")


def cmd_import(args):
    """Import CSV file."""
    path = args.file
    if not os.path.exists(path):
        print(f"Файл не найден: {path}")
        return
    try:
        count = import_csv(path)
        print(f"Добавлено {count} игр из {path}")
    except Exception as e:
        print(f"Ошибка импорта: {e}")


def cmd_report(args):
    """Print overall report."""
    try:
        stats = global_stats()
        if not stats or stats["total_games"] == 0:
            print("Нет сохранённых игр. Добавьте игру через 'add' или импортируйте CSV.")
            return

        print("=" * 50)
        print("DOTA_MASTER — Общий отчёт")
        print("=" * 50)
        print(f"Всего игр: {stats['total_games']}")
        print(f"Побед: {stats['total_wins']}  Поражений: {stats['total_losses']}")
        print(f"Win Rate: {stats.get('win_rate', 0)}%")
        print(f"Средний KDA: {stats.get('avg_kd', 0)}")
        games_all = get_games()
        avg_rotl = round(sum(g.get('rotl', 0) or 0 for g in games_all) / len(games_all), 2) if games_all else 0
        print(f"Средний RoTL: {avg_rotl}")
        print(f"Средний GPM: {stats.get('avg_gpm', 0)}  XPM: {stats.get('avg_xpm', 0)}")
        print(f"Средний Last Hits: {stats.get('avg_lh', 0)}")
        print()
        print("Статистика по героям (топ):")
        for h in stats.get("by_hero", [])[:10]:
            print(f"  {h['hero']}: {h['games']} игр, {h['wins']}W/{h['losses']}L, WR={h['win_rate']}%")
        print()

        # Критические ошибки
        analysis = analyze_all_games()
        errors = analysis.get("errors_summary", {})
        if errors:
            print("Критические ошибки (встречаются в играх):")
            for error_text, count in sorted(errors.items(), key=lambda x: -x[1]):
                print(f"  [{count} раз] {error_text}")
        else:
            print("Критических ошибок не обнаружено (или мало данных).")

        print()
        print("Стратегии по героям (топ-5 по количеству игр):")
        for h in stats.get("by_hero", [])[:5]:
            hero_name = h["hero"]
            report = hero_strategies_report(hero_name)
            # only print first 3 lines to keep terminal readable
            for line in report.splitlines()[:3]:
                print(f"  {line}")

    except Exception as e:
        print(f"Ошибка отчёта: {e}")


def cmd_hero(args):
    """Show detailed hero analysis."""
    hero_name = args.hero
    if not hero_name:
        print("Укажите героя: main.py hero <name>")
        return
    try:
        report = hero_strategies_report(hero_name)
        print(report)
    except Exception as e:
        print(f"Ошибка анализа: {e}")


def cmd_fetch(args):
    """Fetch matches from OpenDota."""
    # Determine steam id input
    steam_input = args.steam_id
    if not steam_input:
        steam_input = input("SteamID64 (длинный ID из профиля Steam) или vanity URL: ").strip()

    if not steam_input:
        print("Отмена: SteamID не указан.")
        return

    # Try to resolve
    account_id = None
    # Check if it looks like a numeric SteamID64
    if steam_input.isdigit() and len(steam_input) == 17:
        account_id = _steam_id64_to_account_id(steam_input)
        print(f"  Распознан SteamID64 -> account_id={account_id}")
    else:
        # Try to treat as vanity URL
        print("  Пытаемся определить через vanity URL...")
        resolved = resolve_steam_profile(steam_input)
        if resolved:
            account_id = resolved
            print(f"  Распознано: account_id={account_id}")
        else:
            print("  Не удалось определить account_id. Убедитесь что STEAM_API_KEY установлен в переменных окружения.")
            return

    if account_id is None:
        print("  Не могу определить account_id. Попробуйте указать SteamID64 напрямую.")
        return

    max_games = args.max or 50
    print(f"  Загружаю до {max_games} игр из OpenDota...")
    matches = get_player_matches(account_id, max_matches=max_games)
    if not matches:
        print("  Не получил матчи. Проверьте account_id и соединение.")
        return

    saved = save_matches(matches)
    print(f"  Сохранено {saved} новых игр в games.json")

    # Print summary of first few
    print("  Первые несколько:")
    for m in matches[:3]:
        print(f"    [{m.get('date')}] {m.get('hero')} | {m.get('result')} | KDA={m.get('kills')}/{m.get('deaths')}/{m.get('assists')} | GPM={m.get('gpm')} | XPM={m.get('xpm')}")


def cmd_fetch_heroes(args):
    """Download heroes list from OpenDota."""
    print("Загружаю список героев из OpenDota...")
    heroes = get_heroes_list()
    if heroes:
        print(f"Загружено {len(heroes)} героев в data/heroes_cache.json")
    else:
        print("Не удалось загрузить список героев.")


def cmd_list(args):
    """List recent games."""
    games = get_games()
    if not games:
        print("Нет сохранённых игр.")
        return
    count = args.count or 10
    print(f"Последние {count} игр:")
    for g in games[-count:]:
        print(f"  [{g.get('date')}] {g.get('hero')} | {g.get('result')} | K={g.get('kills')} D={g.get('deaths')} A={g.get('assists')} | GPM={g.get('gpm')} XPM={g.get('xpm')} | RoTL={g.get('rotl')}")


def cmd_errors(args):
    """List games with critical errors."""
    games = get_games()
    if not games:
        print("Нет игр для проверки.")
        return
    print("Игры с критическими ошибками:")
    found = False
    for g in games:
        errs = detect_errors(g)
        if errs:
            found = True
            print(f"  [{g.get('date')}] {g.get('hero')} | {g.get('result')} | " + " | ".join(errs))
    if not found:
        print("  Критических ошибок не найдено.")


    


def cmd_au_start(args):
    """Запустить автообновление."""
    account_id = str(args.account_id or DEFAULT_ACCOUNT_ID)
    interval = args.interval
    max_matches = args.max
    try:
        start_auto_update(account_id, interval, max_matches)
        print("Автообновление запущено:")
        print(f"  account_id: {account_id}")
        print(f"  интервал: {interval} сек ({interval // 60} мин)")
        print(f"  max матчей: {max_matches}")
    except Exception as e:
        print(f"Ошибка запуска: {e}")
def cmd_au_stop(args):
    """Остановить автообновление."""
    stopped = stop_auto_update()
    if stopped:
        print("Автообновление остановлено.")
    else:
        print("Автообновление не было запущено.")


def cmd_au_status(args):
    """Показать статус автообновления."""
    status = get_auto_update_status()
    if not status["running"]:
        print("Автообновление: не запущено")
        return
    print("Автообновление: активно")
    print(f"  account_id: {status['account_id']}")
    interval = int(status['interval_seconds'])
    print(f"  интервал: {interval} сек ({interval // 60} мин)")
    print(f"  последнее обновление: {status['last_update'] or 'ещё не было'}")
    print(f"  добавлено за сессию: {status['games_added']} матчей")


def main():
    parser = argparse.ArgumentParser(description="DOTA_MASTER — анализ статистики DOTA 2")
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    # add
    subparsers.add_parser("add", help="Добавить игру (ручной ввод)").set_defaults(func=cmd_add)

    # import
    imp = subparsers.add_parser("import", help="Импорт из CSV")
    imp.add_argument("file", help="CSV-файл для импорта")
    imp.set_defaults(func=cmd_import)

    # report
    subparsers.add_parser("report", help="Показать общий отчёт").set_defaults(func=cmd_report)

    # hero
    hr = subparsers.add_parser("hero", help="Анализ конкретного героя")
    hr.add_argument("hero", help="Название героя")
    hr.set_defaults(func=cmd_hero)

    # fetch
    ft = subparsers.add_parser("fetch", help="Загрузить матчи из OpenDota")
    ft.add_argument("--steam-id", help="SteamID64 или vanity URL")
    ft.add_argument("--max", type=int, default=50, help="Максимум игр (по умолчанию 50)")
    ft.set_defaults(func=cmd_fetch)

    # fetch-heroes
    fh = subparsers.add_parser("fetch-heroes", help="Скачать список героев из OpenDota")
    fh.set_defaults(func=cmd_fetch_heroes)

    # list
    lst = subparsers.add_parser("list", help="Показать последние игры")
    lst.add_argument("--count", type=int, default=10, help="Сколько игр показать (по умолчанию 10)")
    lst.set_defaults(func=cmd_list)

    # errors
    subparsers.add_parser("errors", help="Показать критические ошибки").set_defaults(func=cmd_errors)

    # auto-update
    au = subparsers.add_parser("auto-update", help="Управление автообновлением статистики")
    au_sub = au.add_subparsers(dest="au_command")

    au_start = au_sub.add_parser("start", help="Запустить автообновление")
    au_start.add_argument("--account-id", help="account_id игрока (по умолчанию из DOTA_ACCOUNT_ID)")
    au_start.add_argument("--interval", type=int, default=300, help="Интервал в секундах (по умолчанию 300 = 5 мин)")
    au_start.add_argument("--max", type=int, default=100, help="Максимум матчей за раз (по умолчанию 100)")
    au_start.set_defaults(func=cmd_au_start)

    au_stop = au_sub.add_parser("stop", help="Остановить автообновление")
    au_stop.set_defaults(func=cmd_au_stop)

    au_status = au_sub.add_parser("status", help="Показать статус автообновления")
    au_status.set_defaults(func=cmd_au_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()