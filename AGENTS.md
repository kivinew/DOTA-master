# AGENTS.md — DOTA_MASTER

Анализ статистики игр Dota 2: CLI (`main.py`) + Flask веб-интерфейс (`app.py`, порт 9999), данные из OpenDota API.

## Структура

- `main.py` — CLI: `add`, `import <csv>`, `report`, `hero <name>`, `list`, `errors`, `fetch`, `fetch-heroes`, `auto-update start|stop|status`
- `app.py` — Flask app. Страницы: `/`, `/games` (история + живые матчи, бывшая `/fresh` — редирект на `/games#live`), `/errors`, `/macro` (объединённая «Анализ и отчёт»; `/report` — редирект на `/macro`), `/heroes`, `/hero/<name>`, `/match/<id>`, `/api`, `/healthz`. Запуск через `run_simple`, без reloader/debugger
- `analysis/stats_engine.py` — хранилище `games/games.json`, `add_game`, `import_csv`, `merge_games` (дедуп по `match_id`/CSV-ключу), `global_stats`, `hero_stats`, `detect_errors`, `analyze_all_games`, `get_game_by_match_id`, in-memory indexes (`_match_id_index`, `_hero_index`)
- `analysis/config.py` — единый конфиг через env (`DOTA_ACCOUNT_ID`, `PORT`, `DOTA_UPDATE_INTERVAL`, `DOTA_MAX_MATCHES`, `DOTA_MASTER_SECRET`, `DOTA_STEAM_ID64`); использовать его, не хардкодить
- `analysis/http.py` — единый HTTP-клиент (`fetch_json` с retry); новый сетевой код — только через него
- `analysis/fresh_cache.py` — TTL-кэш (60 c) свежих матчей, stale-while-revalidate; страницы `/` и `/games` (секция живых матчей) идут через него, не напрямую в API
- `analysis/fetcher.py` — OpenDota API (`urllib`, без внешних зависимостей): `get_player_matches`, `normalize_open_dota_match`, `save_matches`, `resolve_steam_profile`, `get_heroes_list`. Дедупликация по `match_id`
- `analysis/web_fetcher.py`, `analysis/macro_analyzer.py`, `analysis/report_generator.py` — свежие матчи, макро-анализ, отчёты (`analyze_match` для детали матча)
- `analysis/hero_strategies.py` — стратегии победы по героям
- `analysis/template_utils.py` — регистрация Jinja globals (`hero_slug`, `hero_img_url`, `HERO_SLUG_MAP`)
- `analysis/console_utf8.py` — `enable_utf8_console()` вызывать первым в каждой точке входа
- `analysis/auto_update.py`, `analysis/auto_update_daemon.py` — фоновое обновление, состояние в `games/.auto_update_state.json`, PID в `games/.auto_update.pid`
- `analysis/icons.py`, `heroes_cache.py`, `item_mapping.py` — URL иконок/портретов, кэш героев (`data/heroes_cache.json`)
- `templates/base.html` + `templates/*.html` — все страницы наследуют `base.html`
- `static/css/dota.css` — единственный CSS-файл; `static/heroes|items|abilities|js/` — ассеты
- `games/games.json` — основная БД; `games/fresh_matches.json`, `games/match_list.json` — кэши
- `scripts/fetch.py` — единая загрузка (`--source web|api`, `--steam-id64`, `--account-id`, `--max`)
- `scripts/import_matches.py` — единый импорт (`--fresh`, `--csv`, `--json`) через `stats_engine.merge_games`
- `tests/` — pytest, хранилище изолируется в tmp (`isolated_games`); запуск: `python -m pytest tests/ -q`
- `start_web.bat` — launcher сервера; `server.log` — лог; `test_fetcher.py` — ручная проверка fetcher

## Команды

```bash
python main.py add
python main.py import <file.csv>   # колонки: date,hero,role,result,kills,deaths,assists,RoTL,last_hits,GPM,XPM,game_mode,draft_allies,draft_enemies,notes
python main.py report
python main.py hero Invoker
python main.py list --count 10
python main.py errors
python main.py fetch --steam-id <SteamID64> --max 50
python main.py fetch-heroes
python scripts/fetch.py --steam-id64 76561198001364885 --max 30 --source web|api
python scripts/import_matches.py --fresh|--csv <file>|--json <file>
# веб:
start_web.bat                      # или: python app.py  -> http://localhost:9999
```

Зависимости: Python 3.10+, только stdlib + Flask (+ `pyyaml` при необходимости, `markdown>=3.5` для отчётов). `uv pip install -r requirements.txt`.

## Обязательные правила

1. **UTF-8 везде.** Все файлы — UTF-8 без BOM. В каждой точке входа (`app.py`, `main.py`, `scripts/*.py`, `test_fetcher.py`, `analysis/auto_update_daemon.py`) первым вызывать `enable_utf8_console()` до первого `print`/лога. `start_web.bat` держать ASCII-only, не менять `chcp 65001` и `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`. В PowerShell не использовать `>` для чтения/записи UTF-8 файлов (`Get-Content -Encoding UTF8`, `[IO.File]::ReadAllText`, `cmd /c "python app.py > server.log 2>&1"`).
2. **Шаблоны/CSS.** Новые страницы: только `{% extends "base.html" %}` + `{% block content %}`, без своего CSS. Использовать готовые классы (`.dota-section`, `.dota-table`, `.stat-card`, `.btn`, `.page-title` и утилиты `.muted`, `.gold`, `.mono` и т.д., см. README). Никаких inline-стилей. После правки CSS bump версии в `base.html` (`dota.css?v=N`). После правки шаблонов перезапускать сервер — Flask кеширует их (reloader выключен).
3. **Портреты героев.** Использовать `hero_slug()` / `hero_img_url()` из `app.py` (локальный `static/heroes/<slug>.png`, fallback `https://cdn.opendota.com/heroes/<slug>.png`). Маппинг в `HERO_SLUG_MAP` — дополнять его, а не хардкодить URL в шаблонах.
4. **Данные игр.** Читать/писать только через функции `stats_engine` (`_load_games`/`_save_games` — приватные, снаружи использовать `get_games`, `add_game`, `save_matches`, `merge_games`). Схема записи: `date, hero(Title), role(lower), result(win|loss), kills, deaths, assists, rotl, last_hits, gpm, xpm, game_mode, draft_allies, draft_enemies, notes, match_id, source`. Дедупликация: по `(date, hero, kills, deaths)` для CSV, по `match_id` для OpenDota. `open(..., encoding="utf-8")`, `json.dump(ensure_ascii=False)`.
5. **OpenDota fetcher.** Только через `analysis/fetcher.py`: `urllib` + `User-Agent: DOTA_MASTER/1.0`, пауза `RATE_LIMIT_DELAY=1.0с`, retry на 429. `SteamID64 -> account_id = SID64 - 76561197960265728`. Даты в локальном времени игрока (UTC+7). Дефолтный `account_id=41099157` (`DOTA_ACCOUNT_ID`, `DOTA_UPDATE_INTERVAL` через env).
6. **Windows-специфика в `app.py`.** Не удалять `_SafeStderr`/патч colorama и `_is_process_running` (tasklist) — без них краш на Windows (`os.kill(pid,0)` и colorama с перенаправленным stderr не работают). Те же причины: запуск через `run_simple`, не `app.run`.
7. **Пути.** `app.py` делает `os.chdir` в корень проекта — относительные пути (`games/`, `data/`, `static/`) резолвятся оттуда. В `main.py` и `scripts/*.py` добавлен `sys.path.insert` корня — сохранять.
8. **Безопасность в `app.py`.** Security headers (CSP, X-Frame-Options, etc.), rate limiting на `/api/*` (in-memory), input validation helpers (`sanitize_string`, `validate_*`). Не убирать без замены.

## Чего не делать

- Не добавлять ORM/pandas/HTTP-клиенты без необходимости — проект на stdlib + Flask.
- Не класть секреты в код: `STEAM_API_KEY`, `DOTA_MASTER_SECRET`, `DOTA_ACCOUNT_ID` — только env.
- Не коммитить/не затирать `games/*.json` и `server.log` без нужды — это локальные данные.
- Не использовать старые `scripts/fetch_*.py`, `scripts/import_*.py` — они пишут в `scripts/games/` (теневая копия).
