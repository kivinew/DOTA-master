# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DOTA_MASTER** — Flask web interface + CLI for Dota 2 match statistics analysis.
- Port: 9999
- Style: Dota 2 dark theme (gold/green/red accents)
- Data: games/games.json (312+ matches), OpenDota API integration
- Language: Russian UI, Python 3.10+

## Common Commands

`
bash
# Install dependencies
pip install -r requirements.txt

# Run Flask server (production mode, no auto-reload)
python app.py
# Or via launcher (handles UTF-8 on Windows)
start_web.bat

# CLI commands
python main.py add              # Interactive add game
python main.py import file.csv  # Import CSV
python main.py report           # Overall stats report
python main.py hero Invoker     # Hero-specific analysis
python main.py list --count 10  # Recent games
python main.py errors           # Games with critical errors
python main.py fetch --steam-id64 76561198001364885 --max 30
python main.py auto-update start --interval 300 --max 100
python main.py fetch-heroes     # Update hero cache from OpenDota

# Fetch matches from OpenDota (scripts/fetch.py is canonical)
python scripts/fetch.py --steam-id64 76561198001364885 --max 30           # web (fast, recentMatches)
python scripts/fetch.py --steam-id64 76561198001364885 --max 30 --source api  # api (full detail)
python scripts/import_matches.py --fresh  # Import from games/fresh_matches.json (deduped)

# Tests (uses tmp storage, doesn't touch games/games.json)
python -m pytest tests/ -q
python -m pytest tests/test_stats_engine.py -q  # single test file
`

## Architecture

### Entry Points
| File | Purpose |
|------|---------|
| app.py | Flask app (port 9999), registers Jinja globals, API + page routes. Uses `run_simple` (no reloader/debugger). Chdirs to project root. |
| main.py | CLI with subcommands (add/import/report/hero/list/errors/fetch/fetch-heroes/auto-update). Inserts project root into sys.path. |
| scripts/fetch.py | Canonical match fetcher (web/api sources), writes to games/games.json via analysis.* |
| scripts/import_matches.py | Import fresh matches from games/fresh_matches.json with dedup |

### Core Modules (analysis/)
| Module | Responsibility |
|--------|----------------|
| config.py | **Single source of truth** for env config (DOTA_ACCOUNT_ID, PORT, DOTA_UPDATE_INTERVAL, DOTA_MAX_MATCHES, DOTA_MASTER_SECRET, DOTA_STEAM_ID64). Use this, don't hardcode. |
| http.py | Shared HTTP client (`fetch_json` with retry on 429/network errors). All network code must use this. |
| fetcher.py | OpenDota API: get_player_matches, normalize_open_dota_match, save_matches, resolve_steam_profile, get_heroes_list. Rate limit 1s, User-Agent: DOTA_MASTER/1.0. |
| web_fetcher.py | OpenDota API (альтернатива API): загрузка recentMatches + догоняющий запрос |
| fresh_cache.py | TTL cache (60s) stale-while-revalidate for fresh matches. `/` and `/fresh` hit this, not API directly. |
| stats_engine.py | Storage, aggregation, detect_errors, merge_games, get_game_by_match_id, in-memory indexes (_match_id_index, _hero_index). Private `_load_games`/`_save_games` — use public API. |
| macro_analyzer.py | Match analysis vs Legend benchmarks (GPM/XPM/LH, deaths, damage). Single request per match. |
| report_generator.py | Text/markdown reports from macro analysis. |
| hero_strategies.py | Win/loss factor analysis per hero (draft, GPM delta, early deaths, contribution). |
| auto_update.py | Background thread updating games.json every N minutes. State in games/.auto_update_state.json. |
| auto_update_daemon.py | Separate process daemon for auto-update. PID in games/.auto_update.pid. |
| icons.py | Item/ability icon URLs (local -> Steam CDN fallback). hero_img_url, item_img_url, ability_img_url. |
| console_utf8.py | UTF-8 stdout/stderr on Windows (fixes cp1251). **Must be called first** in every entry point. |
| template_utils.py | Jinja globals: hero_slug, hero_img_url, item_img_url, ability_img_url, game_mode_name. |

### Data Flow
`
OpenDota API -> fetcher.py/web_fetcher.py -> stats_engine.save_matches()
                                                    v
                                              games/games.json
                                                    v
                          +-------------------------+-------------------------+
                          v                         v                         v
                    stats_engine              macro_analyzer           templates/
                    (aggregation)             (benchmarks)             (Flask pages)
                          v                         v                         v
                    /api/stats               /macro, /match/<id>      index, hero, games, errors, fresh
`

### Templates & Static
- templates/base.html — single layout: header menu, `<main class="container">`, footer
- templates/*.html — extend base.html, define `{% block content %}` — **no custom CSS**
- static/css/dota.css — **all** styling (CSS variables --dota-*, clip-path panels, responsive)
- Version cache-busting: `dota.css?v=N` in base.html (bump on CSS changes)
- static/heroes|items|abilities|js/ — local assets (fallback for CDN)

### Key Routes
| Route | Template | Data |
|-------|----------|------|
| / | index.html | global stats, fresh matches (from TTL cache), top heroes |
| /hero/<hero> | hero.html | hero stats, games, strategy report |
| /games | games.html | paginated match list |
| /fresh | fresh.html | live matches from TTL cache |
| /match/<id> | match_detail.html | full analysis, draft, skill build, items, MVP |
| /errors | errors.html | games with detect_errors flags |
| /macro | macro.html | aggregate macro analysis |
| /report | report.html | markdown report |
| /api/games?page=1&per_page=50 | JSON | paginated games (per_page ≤ 200) |
| /api/* | JSON | same data as pages; errors: `{"status": "error", "message": ...}` |

## Development Notes

### UTF-8 on Windows (Critical)
- **All entry points** call `enable_utf8_console()` **first** (before any print/log): app.py, main.py, scripts/*.py, auto_update_daemon.py, test_fetcher.py
- start_web.bat: `chcp 65001` + `PYTHONUTF8=1` — **keep ASCII-only** (cmd reads .bat in current code page)
- PowerShell: never use `>` for UTF-8 files. Use `Get-Content -Encoding UTF8` or `[IO.File]::ReadAllText(path, [Text.Encoding]::UTF8)`. For logs: `cmd /c "python app.py > server.log 2>&1"`
- All source files: UTF-8 without BOM

### Adding a Page
```html
{% extends "base.html" %}
{% block title %}DOTA_MASTER — Page{% endblock %}
{% block content %}
<h1 class="page-title">🆕 Title</h1>
<p class="page-subtitle">Description</p>
<div class="dota-section">
    <div class="dota-section-title">Section</div>
    ...
</div>
{% endblock %}
```
Use utility classes: `.dota-section`, `.dota-table`, `.stat-card`, `.stats-row`/`.stats-grid`, `.tip-box`, `.btn`/`.btn-primary`, `.error-pill`, `.empty-state`, `.pagination`, `.hero-grid`/`.hero-card`, `.match-preview`, `.hero-large`/`.hero-portrait-large`.
Utility: `.muted`, `.gold`, `.cyan`, `.fs-sm` (0.8rem), `.fs-xs` (0.7rem), `.mono`, `.tc`/`.tl`, `.mt-sm`/`.mt-md`, `.hidden`, `.note-box`, `.inline-code`, `.hero-thumb-sm`, `.stat-value-sm`, `.stat-value-xs`, `.empty-state-sm`.

**After CSS changes:** bump version in base.html (`dota.css?v=N`). **After template changes:** restart server (Flask caches templates, no reloader).

### Icon System (analysis/icons.py)
- `hero_img_url(hero)` — local `static/heroes/{slug}.png` → OpenDota CDN fallback. Uses `HERO_SLUG_MAP` in app.py — extend it, don't hardcode URLs.
- `item_img_url(item_id)` — local via items_cache.json slug → Steam CDN
- `ability_img_url(ability_id)` — local via ability_id_to_slug.json → Steam CDN (dota_react/abilities/)
  - Talents (ID ≥ 6000): transparent 1x1 PNG placeholder (no CDN icons)
  - Aghanim's Scepter/Shard: item icons (ultimate_scepter, aghanims_shard)

### Data Schema (games/games.json)
```
date, hero(Title), role(lower), result(win|loss), kills, deaths, assists, rotl,
last_hits, gpm, xpm, game_mode, draft_allies, draft_enemies, notes,
match_id, source(opendota_web|opendota|csv|manual)
```
- Dedup: CSV by `(date, hero, kills, deaths)`; OpenDota by `match_id`
- `rotl == 0` means "no data from OpenDota" — not flagged as error
- `open(..., encoding="utf-8")`, `json.dump(ensure_ascii=False)`

### Testing
- tests/conftest.py patches `stats_engine.GAMES_DIR` to tmp path (isolated storage)
- Run all: `python -m pytest tests/ -q`
- Coverage: stats_engine, fetcher, hero_strategies, http, fresh_cache, import/merge_games, api
- Run single file: `python -m pytest tests/test_stats_engine.py -q`

### Environment Variables (analysis/config.py)
| Variable | Default | Description |
|----------|---------|-------------|
| DOTA_ACCOUNT_ID | 41099157 | OpenDota account_id |
| DOTA_STEAM_ID64 | — | SteamID64 for vanity resolution |
| PORT | 9999 | Flask port |
| DOTA_UPDATE_INTERVAL | 300 | Auto-update interval (seconds) |
| DOTA_MAX_MATCHES | 100 | Max matches to fetch/store |
| DOTA_MASTER_SECRET | — | Flask secret key |
| STEAM_API_KEY | — | Only for vanity URL resolution in CLI fetch |

### Dependencies
- Python 3.10+
- Runtime: **stdlib only** + Flask (PyYAML optional, markdown>=3.5 for reports)
- Dev: pytest
- `uv pip install -r requirements.txt` (Flask, PyYAML, markdown, pytest)

## Mandatory Rules (from AGENTS.md)

1. **UTF-8 everywhere.** All files UTF-8 no BOM. `enable_utf8_console()` first in every entry point. start_web.bat ASCII-only. PowerShell: no `>` for UTF-8.
2. **Templates/CSS.** New pages: only `{% extends "base.html" %}` + `{% block content %}`, no custom CSS. Use existing utility classes (see README). No inline styles. Bump CSS version in base.html. Restart server after template changes.
3. **Hero portraits.** Use `hero_slug()` / `hero_img_url()` from app.py (local → CDN). Extend `HERO_SLUG_MAP`, don't hardcode URLs in templates.
4. **Game data.** Read/write only via `stats_engine` public API (`get_games`, `add_game`, `save_matches`). Private `_load_games`/`_save_games` — internal only. UTF-8 encoding, `ensure_ascii=False`.
5. **OpenDota fetcher.** Only via `analysis/fetcher.py`: urllib + User-Agent, 1s rate limit, retry on 429. SteamID64 → account_id = SID64 - 76561197960265728. Dates in player local time (UTC+7).
6. **Windows specifics in app.py.** Keep `_SafeStderr`/colorama patch and `_is_process_running` (tasklist) — required for Windows (os.kill(pid,0) and colorama with redirected stderr fail). Use `run_simple`, not `app.run`.
7. **Paths.** app.py chdirs to project root — relative paths (games/, data/, static/) resolve from there. main.py has sys.path.insert for root — preserve.
8. **No secrets in code.** STEAM_API_KEY, DOTA_MASTER_SECRET, DOTA_ACCOUNT_ID — env only.
9. **Don't commit local data.** games/*.json, server.log — local only (in .gitignore).
10. **No unnecessary deps.** No ORM/pandas/external HTTP clients — stdlib + Flask only.
11. **Security in app.py.** Keep security headers (CSP, X-Frame-Options, etc.), rate limiting on /api/*, input validation helpers (sanitize_string, validate_*). Don't remove without replacement.

## Project Status (from UPDATEPLAN.md)

All critical phases completed (as of 2026-09-23):
- **Phase 0 (Critical Bugs):** Fixed report KeyError, inverted death advice, Unicode minus sign, Chinese char in reports, broken HERO_TABLE (now 127 heroes from cache), double API calls in macro/report, dead imports, added requirements.txt + .gitignore. Fixed `detect_errors` false positives on `rotl == 0`.
- **Phase 1 (Hygiene/Docs):** README synchronized, 15 tests added, unified config.py in 4 entry points, fixed import_csv dedup bug (caught by tests).
- **Phase 2 (Quality):** http.py (unified fetch_json), fresh_cache.py (TTL 60s stale-while-revalidate), consolidated scripts/fetch.py + import_matches.py with merge_games() dedup, API pagination + JSON errors. **32 tests pass.**

### Known Legacy Files (Do Not Use)
- Old fetch scripts: `scripts/fetch_fresh.py`, `scripts/fetch_opendota_fresh.py`, `scripts/fetch_steam.py`, `scripts/fetch_web_matches.py` — wrote to `scripts/games/` (shadow copy)
- Old import scripts: `scripts/import_fresh_matches.py` — use `scripts/import_matches.py` instead
- `test_fetcher.py` — manual test, superseded by pytest suite

### Non-Existent Files (Referenced in Old Docs)
- `config.yaml` — doesn't exist, use env vars via config.py
- `analysis/error_detector.py` — doesn't exist, logic in stats_engine.detect_errors()
- `analysis/recommendation.py` — doesn't exist
- `analysis/template_utils.py` — регистрирует Jinja globals: hero_slug, hero_img_url, item_img_url, ability_img_url, game_mode_name, utility functions (max, min, round) via `register_jinja_globals(app)`
- `analysis/template_utils.py` — Jinja globals: hero_slug, hero_img_url, HERO_SLUG_MAP (registered via `register_jinja_globals(app)`)
