#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOTA_MASTER — Flask веб-интерфейс для анализа статистики игр в DOTA 2.
Порт 9999, стиль DOTA 2, портреты героев с OpenDota CDN.
"""

import sys
import os
import io

# ── Fix 0: принудительный UTF-8 для stdout/stderr ─────────────────────────
# Windows по умолчанию использует ANSI-кодировку консоли (cp1251), поэтому:
#   * при `python app.py > server.log` печать «—» или «◄» падает с
#     UnicodeEncodeError: 'charmap' codec can't encode character;
#   * при chcp 1251 + PYTHONIOENCODING=utf-8 русские буквы в консоли
#     превращаются в кракозябры («РџСЂРёРІРµС‚» вместо «Привет»).
# Поэтому переключаем code page консоли на 65001 и потоки в UTF-8
# (см. analysis/console_utf8.py). Работает и при перенаправлении вывода.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.report_generator import generate_full_report
from analysis.fresh_cache import get_cached_fresh_view
from analysis import fresh_cache
from analysis import config as _cfg  # env: DOTA_ACCOUNT_ID, PORT, DOTA_UPDATE_INTERVAL...
from analysis.template_utils import register_jinja_globals
import markdown

# ── Markdown → HTML (using Python-Markdown) ───────────────────────────────

_md = markdown.Markdown(
    extensions=["tables", "fenced_code", "codehilite", "toc"],
    output_format="html5",
)

def markdown_to_html(text: str) -> str:
    """Convert Markdown to HTML using Python-Markdown."""
    if not text:
        return ""
    return _md.convert(text)

# ── Fix 1: colorama crash on Windows console ─────────────────────────────
# werkzeug._internal._log uses _ColorStreamHandler → colorama.AnsiToWin32(sys.stderr)
# This crashes when sys.stderr is not a valid Windows console handle.
# Replace sys.stderr with a wrapper that has no fileno() so colorama gives up gracefully.
class _SafeStderr(io.TextIOWrapper):
    """Wrapper around BytesIO that writes to original stderr but has no fileno()."""
    def __init__(self):
        super().__init__(io.BytesIO(), encoding='utf-8')
    def fileno(self):
        raise AttributeError("fileno")
    def write(self, data):
        sys.__stderr__.write(data)
        sys.__stderr__.flush()

sys.stderr = _SafeStderr()

# Now patch colorama to handle the AttributeError gracefully
try:
    import colorama
    import colorama.ansitowin32
    _orig_ansi_init = colorama.ansitowin32.AnsiToWin32.__init__

    def _patched_ansi_init(self, stream, strip=None, convert=None, autoreset=False):
        try:
            _orig_ansi_init(self, stream, strip=strip, convert=convert, autoreset=autoreset)
        except (OSError, IOError, AttributeError, ValueError):
            self.stream = stream
            self.convert = False
            self.strip = False
            self.autoreset = False
            self.win32_calls = None
            self.wrapped = stream

    colorama.ansitowin32.AnsiToWin32.__init__ = _patched_ansi_init
except ImportError:
    pass

# ── Fix 2: os.kill(pid, 0) doesn't work on Windows ───────────────────────
# Replace with Windows-compatible process existence check
import subprocess

def _is_process_running(pid: int) -> bool:
    """Check if a process is running (Windows-compatible)."""
    if sys.platform == "win32":
        try:
            # Use tasklist to check if process exists
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=5
            )
            return str(pid) in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

# Monkey-patch the function in auto_update module before importing it
import analysis.auto_update as _au_module
_au_module._is_running = _is_process_running

import json
import math
import threading
import time
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, request

# Местное время игрока (UTC+7) — те же даты, что пишет web_fetcher.
_LOCAL_TZ = timezone(timedelta(hours=7))
from werkzeug.serving import run_simple

# Ensure import from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from analysis.stats_engine import (
    get_games,
    global_stats,
    hero_stats,
    detect_errors,
    analyze_all_games,
    get_hero_games,
)
from analysis.hero_strategies import (
    hero_strategies_report,
    get_counter_heroes,
    get_primary_counter,
)
from analysis.config import ACCOUNT_ID
from analysis.auto_update import (
    start_auto_update,
    stop_auto_update,
    get_auto_update_status,
)


# ── Flask приложение ────────────────────────────────────────────────────────

app = Flask(__name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static")

# Register Jinja globals from template_utils
register_jinja_globals(app)

app.config["SECRET_KEY"] = _cfg.SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ── Security: Security Headers ───────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Content Security Policy - restrictive but allows inline scripts/styles for our template
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://cdn.opendota.com https://cdn.cloudflare.steamstatic.com https://steamcdn-a.akamaihd.net; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # HSTS - only if using HTTPS (commented out for dev)
    # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Security: Rate Limiting ──────────────────────────────────────────────────
# Simple in-memory rate limiter (use Redis in production)
from collections import defaultdict
from time import time

_rate_limit_store = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 100  # per window

def _check_rate_limit(key: str, max_requests: int = None, window: int = None) -> bool:
    """Check if request is within rate limit. Returns True if allowed."""
    max_requests = max_requests or _RATE_LIMIT_MAX_REQUESTS
    window = window or _RATE_LIMIT_WINDOW
    now = time()
    # Clean old entries
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]
    if len(_rate_limit_store[key]) >= max_requests:
        return False
    _rate_limit_store[key].append(now)
    return True

@app.before_request
def rate_limit():
    """Apply rate limiting to API endpoints."""
    if request.path.startswith("/api/"):
        # Use IP + endpoint as key
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        key = f"{client_ip}:{request.path}"
        # Stricter limits for write operations
        max_req = 20 if request.method in ("POST", "PUT", "DELETE", "PATCH") else 100
        if not _check_rate_limit(key, max_requests=max_req):
            return api_error("Rate limit exceeded. Please slow down.", 429)


# ── Security: Input Validation Helpers ────────────────────────────────────────
import re

def sanitize_string(value: str, max_len: int = 100) -> str:
    """Sanitize string input: strip, limit length, remove control chars."""
    if not isinstance(value, str):
        return ""
    # Remove control characters except newlines/tabs
    value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    return value.strip()[:max_len]

def validate_hero_name(hero: str) -> bool:
    """Validate a hero against the OpenDota hero catalog, not only played heroes.

    API requests for an otherwise valid hero should not fail just because the
    local match history is empty or the player has never picked that hero.
    """
    if not isinstance(hero, str):
        return False
    try:
        catalog_path = os.path.join(os.path.dirname(__file__), "data", "heroes_cache.json")
        with open(catalog_path, "r", encoding="utf-8") as catalog_file:
            catalog = json.load(catalog_file)
        known_heroes = {entry.get("localized_name") for entry in catalog if isinstance(entry, dict)}
        return hero.strip() in known_heroes
    except (OSError, ValueError, TypeError):
        return hero.strip() in get_all_heroes()

def validate_match_id(match_id) -> bool:
    """Validate match_id is a positive integer."""
    try:
        mid = int(match_id)
        return mid > 0
    except (ValueError, TypeError):
        return False

def validate_date_string(date_str: str) -> bool:
    """Validate date string is YYYY-MM-DD."""
    if not date_str:
        return True
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date_str))

def validate_kda_value(kda) -> bool:
    """Validate KDA is a reasonable float."""
    try:
        val = float(kda)
        return 0 <= val <= 1000
    except (ValueError, TypeError):
        return False


# ── Вспомогательные функции ──────────────────────────────────────────────────

def load_fresh_matches():
    """Свежие матчи: TTL-кэш живых данных OpenDota, при сбое — файл."""
    try:
        live, fresh = get_cached_fresh_view(_cfg.ACCOUNT_ID, limit=20)
        if live:
            return {"fresh_matches": live, "account_id": _cfg.ACCOUNT_ID, "live": fresh}
        # Пустой ответ API отличим от «ещё не загружали»: это важно в UI.
        source_note = "empty"
    except Exception:
        source_note = "error"
    path = os.path.join("games", "fresh_matches.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("fresh_matches"):
            return data
    return {"fresh_matches": [], "account_id": _cfg.ACCOUNT_ID or None,
            "live": False, "source_note": source_note}


def _safe_number(value, default=0):
    """Convert possibly stale/imported metric values to finite numbers."""
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError, OverflowError):
        return default


def _normalize_game_record(record):
    """Give old/manual match records the fields required by the web tables."""
    if not isinstance(record, dict):
        return None
    game = dict(record)
    game["hero"] = str(game.get("hero") or game.get("localized_name") or "Unknown hero").strip()
    game["date"] = str(game.get("date") or "")
    result = str(game.get("result") or "").strip().lower()
    game["result"] = "win" if result in ("win", "won", "victory") else "loss"
    game["role"] = str(game.get("role") or "")
    game["game_mode"] = game.get("game_mode") or ""
    game["notes"] = str(game.get("notes") or "")
    game["match_id"] = _safe_number(game.get("match_id"), 0)
    for field, aliases in {
        "kills": ("kills", "K"), "deaths": ("deaths", "D"),
        "assists": ("assists", "A"), "last_hits": ("last_hits", "lh"),
        "gpm": ("gpm", "GPM"), "xpm": ("xpm", "XPM"),
        "rotl": ("rotl", "RoTL"),
    }.items():
        value = next((game.get(key) for key in aliases if game.get(key) is not None), 0)
        game[field] = _safe_number(value, 0)
    return game


def get_games_data(page: int = 1, per_page: int = 50,
                   hero_filter: str = None, result_filter: str = None,
                   date_from: str = None, date_to: str = None,
                   min_kda: float = None, max_kda: float = None):
    """Get paginated games with optional filters."""
    games = [normalized for record in get_games()
             if (normalized := _normalize_game_record(record)) is not None]

    # Apply filters
    if hero_filter:
        games = [g for g in games if g.get("hero") == hero_filter]

    if result_filter:
        games = [g for g in games if g.get("result") == result_filter]

    if date_from:
        games = [g for g in games if str(g.get("date", ""))[:10] >= date_from]

    if date_to:
        # Compare date-only values so matches played later on the end date are
        # included even when the stored timestamp contains a time component.
        games = [g for g in games if str(g.get("date", ""))[:10] <= date_to]

    if min_kda is not None:
        games = [g for g in games if (g.get("kills", 0) + g.get("assists", 0)) / max(g.get("deaths", 1), 1) >= min_kda]

    if max_kda is not None:
        games = [g for g in games if (g.get("kills", 0) + g.get("assists", 0)) / max(g.get("deaths", 1), 1) <= max_kda]

    # Sort by date desc, then match_id desc
    games = sorted(games, key=lambda g: (g.get("date", ""), g.get("match_id", 0)), reverse=True)

    total = len(games)
    start = (page - 1) * per_page
    end = start + per_page
    return games[start:end], total


def get_all_heroes():
    """Get list of all unique heroes from valid match records."""
    heroes = {
        str(game.get("hero")).strip()
        for game in get_games()
        if isinstance(game, dict) and game.get("hero")
    }
    return sorted(heroes)


def get_top_heroes(limit=8):
    stats = global_stats()
    if not stats.get("by_hero"):
        return []
    return stats["by_hero"][:limit]


# ── API endpoints ────────────────────────────────────────────────────────────

def api_error(message: str, code: int):
    """Единый формат ошибок API: {"status": "error", "message": ...}."""
    return jsonify({"status": "error", "message": message}), code


@app.errorhandler(404)
def _handle_404(e):
    if request.path.startswith("/api"):
        return api_error("Not found", 404)
    return e


@app.errorhandler(500)
def _handle_500(e):
    if request.path.startswith("/api"):
        return api_error("Internal error", 500)
    return e


@app.route("/api", methods=["GET"])
def api_page():
    return render_template("api.html")


@app.route("/api/games", methods=["GET"])
def api_get_games():
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 50, type=int) or 50
    page = max(1, page)
    per_page = min(max(1, per_page), 200)

    # Filter parameters
    hero_filter = sanitize_string(request.args.get("hero", ""), 50)
    result_filter = sanitize_string(request.args.get("result", ""), 10)
    date_from = sanitize_string(request.args.get("date_from", ""), 20)
    date_to = sanitize_string(request.args.get("date_to", ""), 20)
    min_kda = request.args.get("min_kda", type=float)
    max_kda = request.args.get("max_kda", type=float)

    # Validate
    if result_filter not in ("win", "loss", ""):
        result_filter = ""
    if date_from and not validate_date_string(date_from):
        date_from = ""
    if date_to and not validate_date_string(date_to):
        date_to = ""
    if min_kda is not None and not validate_kda_value(min_kda):
        min_kda = None
    if max_kda is not None and not validate_kda_value(max_kda):
        max_kda = None

    games, total = get_games_data(
        page=page, per_page=per_page,
        hero_filter=hero_filter or None,
        result_filter=result_filter or None,
        date_from=date_from or None,
        date_to=date_to or None,
        min_kda=min_kda,
        max_kda=max_kda
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return jsonify({
        "status": "success",
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "games": games,
    })


@app.route("/api/games/<hero>", methods=["GET"])
def api_get_hero_games(hero):
    hero = sanitize_string(hero, 50)
    if not validate_hero_name(hero):
        return api_error("Invalid hero name", 400)
    games = sorted(get_hero_games(hero), key=lambda g: (g.get("date", ""), g.get("match_id", 0)), reverse=True)
    return jsonify({
        "status": "success",
        "hero": hero,
        "games": games,
        "total": len(games),
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    stats = global_stats()
    return jsonify({"status": "success", "stats": stats})


@app.route("/api/hero/<hero>/stats", methods=["GET"])
def api_hero_stats(hero):
    hero = sanitize_string(hero, 50)
    if not validate_hero_name(hero):
        return api_error("Invalid hero name", 400)
    stats = hero_stats(hero)
    return jsonify({"status": "success", "hero": hero, "stats": stats})


@app.route("/api/hero/<hero>/analysis", methods=["GET"])
def api_hero_analysis(hero):
    hero = sanitize_string(hero, 50)
    if not validate_hero_name(hero):
        return api_error("Invalid hero name", 400)
    report = hero_strategies_report(hero)
    return jsonify({"status": "success", "hero": hero, "analysis": report})


# Health check endpoint
@app.route("/healthz", methods=["GET"])
def health_check():
    """Health check endpoint for monitoring."""
    return jsonify({
        "status": "healthy",
        "service": "DOTA_MASTER",
        "version": "1.0"
    }), 200


@app.route("/api/errors", methods=["GET"])
def api_errors():
    games = sorted(get_games(), key=lambda g: (g.get("date", ""), g.get("match_id", 0)), reverse=True)
    errors_list = []
    for g in games:
        errs = detect_errors(g)
        if errs:
            errors_list.append({
                "date": g.get("date", ""),
                "hero": g.get("hero", ""),
                "result": g.get("result", ""),
                "kills": g.get("kills", 0),
                "deaths": g.get("deaths", 0),
                "assists": g.get("assists", 0),
                "errors": errs,
            })
    return jsonify({"status": "success", "errors": errors_list, "total": len(errors_list)})


@app.route("/api/fresh_matches", methods=["GET"])
def api_fresh_matches():
    data = load_fresh_matches()
    fresh_sorted = sorted(data.get("fresh_matches", []), key=lambda m: (m.get("date", ""), m.get("match_id", 0)), reverse=True)
    return jsonify({
        "status": "success",
        "fresh_matches": fresh_sorted,
        "account_id": data.get("account_id"),
    })


@app.route("/api/auto-update/status", methods=["GET"])
def api_auto_update_status():
    return jsonify({"status": "success", "data": get_auto_update_status()})

@app.route("/api/auto-update/start", methods=["POST"])
def api_auto_update_start():
    account_id = request.form.get("account_id") or request.args.get("account_id") or _cfg.ACCOUNT_ID
    interval = request.form.get("interval", request.args.get("interval"), type=int) or _cfg.UPDATE_INTERVAL
    max_matches = request.form.get("max_matches", request.args.get("max_matches"), type=int) or _cfg.MAX_MATCHES
    start_auto_update(account_id, interval_seconds=interval, max_matches=max_matches)
    return jsonify({"status": "success", "message": "Автообновление запущено"})

@app.route("/api/auto-update/stop", methods=["POST"])
def api_auto_update_stop():
    stopped = stop_auto_update()
    return jsonify({"status": "success", "stopped": stopped})


# ── Страницы ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    stats = global_stats()
    fresh = load_fresh_matches()
    fresh_sorted = sorted(fresh.get("fresh_matches", []), key=lambda m: (m.get("date", ""), m.get("match_id", 0)), reverse=True)
    top_heroes = get_top_heroes(8)
    return render_template("index.html",
        stats=stats,
        fresh_matches=fresh_sorted,
        top_heroes=top_heroes,
        total_games=len(get_games()))


@app.route("/hero/<hero>")
def hero_page(hero):
    stats = hero_stats(hero)
    games = sorted(get_hero_games(hero), key=lambda g: (g.get("date", ""), int(g.get("match_id", 0)) if g.get("match_id") else 0), reverse=True)
    report = hero_strategies_report(hero)
    return render_template("hero.html",
        hero=hero,
        stats=stats,
        games=games,
        report=report,
        total_games=len(get_games()))


@app.route("/errors/")
@app.route("/errors")
def errors_page():
    games = [normalized for record in get_games()
             if (normalized := _normalize_game_record(record)) is not None]
    games.sort(key=lambda g: (g.get("date", ""), g.get("match_id", 0)), reverse=True)
    errors_list = []
    for g in games:
        errs = detect_errors(g)
        if errs:
            errors_list.append({
                "date": g.get("date", ""),
                "hero": g.get("hero", ""),
                "result": g.get("result", ""),
                "kills": g.get("kills", 0),
                "deaths": g.get("deaths", 0),
                "assists": g.get("assists", 0),
                "errors": errs,
            })
    return render_template("errors.html",
        errors=errors_list,
        total_games=len(get_games()),
        total_errors=len(errors_list))


@app.route("/games/")
@app.route("/games")
def games_page():
    page_num = request.args.get("page", 1, type=int)
    page_num = max(1, page_num)
    per_page = 50

    # Get filter parameters
    hero_filter = request.args.get("hero", "").strip()
    result_filter = request.args.get("result", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    min_kda = request.args.get("min_kda", type=float)
    max_kda = request.args.get("max_kda", type=float)

    # Validate date format (YYYY-MM-DD)
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if date_from and not date_pattern.match(date_from):
        date_from = None
    if date_to and not date_pattern.match(date_to):
        date_to = None

    # Validate KDA bounds
    if min_kda is not None and (min_kda < 0 or min_kda > 1000):
        min_kda = None
    if max_kda is not None and (max_kda < 0 or max_kda > 1000):
        max_kda = None

    games, total = get_games_data(
        page=page_num, per_page=per_page,
        hero_filter=hero_filter or None,
        result_filter=result_filter or None,
        date_from=date_from,
        date_to=date_to,
        min_kda=min_kda,
        max_kda=max_kda
    )

    all_heroes = get_all_heroes()
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Даты для быстрых фильтров «Сегодня / 7 дней». Считаем по местному
    # времени игрока (UTC+7), иначе утренние игры попадают в «вчера».
    today = datetime.now(_LOCAL_TZ).date()
    week_ago = today - timedelta(days=6)
    all_games = [_normalize_game_record(r) for r in get_games()]
    games_today = sum(1 for g in all_games
                      if g and str(g.get("date", ""))[:10] == today.isoformat())

    return render_template("games.html",
        games=games,
        total_games=total,
        page=page_num,
        per_page=per_page,
        total_pages=total_pages,
        all_heroes=all_heroes,
        today=today.isoformat(),
        week_ago=week_ago.isoformat(),
        games_today=games_today,
        games_today_str=f"{today:%d.%m}")


@app.route("/fresh")
def fresh_page():
    # refresh=1 — обойти TTL-кэш и заново запросить OpenDota (кнопка «Обновить»)
    if request.args.get("refresh"):
        try:
            fresh_cache.invalidate()
        except Exception:
            pass
    fresh = load_fresh_matches()
    fresh_sorted = sorted(fresh.get("fresh_matches", []), key=lambda m: (m.get("date", ""), m.get("match_id", 0)), reverse=True)
    return render_template("fresh.html",
        fresh_matches=fresh_sorted,
        account_id=fresh.get("account_id"),
        live=fresh.get("live"),
        source_note=fresh.get("source_note"),
        total_games=len(get_games()))


def _analyze_with_local_fallback(max_matches: int):
    """Живой макро-анализ OpenDota, при сбое/отсутствии данных — по games.json."""
    from analysis.macro_analyzer import analyze_all_matches, empty_macro_analysis

    try:
        analysis = analyze_all_matches(max_matches=max_matches)
    except Exception as exc:
        print(f"  macro: живой анализ недоступен — {exc}")
        analysis = empty_macro_analysis()

    if analysis.get("matches"):
        return analysis

    local = analyze_all_matches(max_matches=max_matches, source="local")
    if local.get("matches"):
        local["fallback_reason"] = "open_dota_unavailable"
        return local
    return analysis


@app.route("/macro")
def macro_page():
    # Шаблон macro.html написан под структуру analyze_all_matches
    # (top_errors, general_tips, avg_lhpm), поэтому берём данные оттуда,
    # а не из generate_full_report.
    analysis = _analyze_with_local_fallback(max_matches=100)
    return render_template("macro.html", analysis=analysis)


@app.route("/api/macro", methods=["GET"])
def api_macro():
    limit = request.args.get("limit", 100, type=int)
    analysis = generate_full_report(max_matches=limit)
    return jsonify({"status": "success", **analysis})


@app.route("/match/<int:match_id>")
def match_detail_page(match_id):
    from analysis.macro_analyzer import analyze_match, get_match_details, get_player_slots, _hero_name
    from analysis.stats_engine import get_games
    
    # Найти матч в локальной БД
    local_match = None
    for g in get_games():
        if g.get("match_id") == match_id:
            local_match = g
            break
    
    # Детали загружаем один раз и используем повторно в анализаторе.
    # Ранее route сначала запрашивал список недавних матчей, затем детали,
    # а analyze_match ещё раз скачивал те же детали.
    d = get_match_details(match_id)
    player_slot = None
    
    # Наш игрок в матче: сначала ищем по account_id, затем по hero_id из локальной БД
    if d:
        for pl in d.get("players", []):
            if pl.get("account_id") == ACCOUNT_ID:
                player_slot = pl.get("player_slot")
                break
        if player_slot is None and local_match:
            hero_id = local_match.get("hero_id")
            if hero_id:
                for pl in d.get("players", []):
                    if pl.get("hero_id") == hero_id:
                        player_slot = pl.get("player_slot")
                        break

    # Редкий fallback для матчей, где OpenDota скрыл account_id, а локальная
    # запись не содержит hero_id. Не выполняем запрос списка матчей в обычном случае.
    if d and player_slot is None and not (local_match and local_match.get("hero_id")):
        try:
            player_slot = get_player_slots(limit=100).get(match_id)
        except Exception:
            pass
    
    analysis = analyze_match(match_id, player_slot=player_slot, match_data=d)
    if not analysis:
        return "Матч не найден", 404

    # Определить сторону игрока (0=Radiant, 1=Dire).
    our_team = None
    if d:
        for pl in d.get("players", []):
            if pl.get("account_id") == ACCOUNT_ID:
                slot = pl.get("player_slot", -1)
                our_team = 1 if slot >= 128 else 0
                break
    if our_team is None:
        inferred_slot = player_slot
        if inferred_slot is None and local_match:
            inferred_slot = local_match.get("player_slot")
        try:
            if inferred_slot is not None:
                our_team = 1 if int(inferred_slot) >= 128 else 0
        except (TypeError, ValueError):
            pass
    if our_team is None and d and local_match and local_match.get("result") in ("win", "loss"):
        # В старых записях мог сохраниться только результат и radiant_win.
        if d.get("radiant_win") is not None:
            our_team = 0 if ((local_match["result"] == "win") == bool(d["radiant_win"]) ) else 1

    picks_bans = d.get("picks_bans", []) if d else []

    # Показываем контрпики только если соответствующий герой действительно есть
    # среди соперников этой игры. Не подставляем общий counter из базы вне матча.
    player_hero_name = analysis.get("hero_name", "")
    known_counters = {str(hero).casefold() for hero in get_counter_heroes(player_hero_name)}
    enemy_team = 1 - our_team if our_team is not None else None
    enemy_hero_names = []
    if d and enemy_team is not None:
        for pl in d.get("players", []):
            slot = pl.get("player_slot", -1)
            team = 0 if 0 <= slot <= 4 else 1 if 128 <= slot <= 132 else None
            if team == enemy_team and pl.get("hero_id"):
                enemy_hero_names.append(_hero_name(pl["hero_id"]))
        for pick in picks_bans:
            if pick.get("is_pick") and pick.get("team") == enemy_team:
                hero_id = pick.get("hero_id")
                if hero_id:
                    enemy_hero_names.append(pick.get("hero_name") or _hero_name(hero_id))

    _enemy_counters = list(dict.fromkeys(
        name for name in enemy_hero_names if name and name.casefold() in known_counters
    ))
    preferred_counter = get_primary_counter(player_hero_name)
    _primary_counter = next(
        (name for name in _enemy_counters if name.casefold() == str(preferred_counter).casefold()),
        _enemy_counters[0] if _enemy_counters else None,
    )

    # Построить маппинг hero_id -> player data из players
    hero_to_player = {}
    if d:
        for pl in d.get("players", []):
            hero_id = pl.get("hero_id")
            if hero_id is not None:
                hero_to_player[hero_id] = pl

    # Функция для определения позиции (1-5) из player_slot
    def slot_to_position(slot):
        if slot is None:
            return None
        if 0 <= slot <= 4:
            return slot + 1  # Radiant: 0->1, 1->2, 2->3, 3->4, 4->5
        if 128 <= slot <= 132:
            return slot - 127  # Dire: 128->1, 129->2, 130->3, 131->4, 132->5
        return None

    # Функция извлечения айтемов из данных игрока
    def extract_items(pl):
        items = []
        for i in range(6):
            item_id = pl.get(f"item_{i}", 0)
            if item_id:
                items.append(item_id)
        neutral = pl.get("item_neutral", 0)
        if neutral:
            items.append(("neutral", neutral))
        return items

    # Если picks_bans пустой (не Captain's Mode) — заполняем из players
    if d and not picks_bans:
        for pl in d.get("players", []):
            hero_id = pl.get("hero_id")
            slot = pl.get("player_slot", -1)
            team = 0 if 0 <= slot <= 4 else 1 if 128 <= slot <= 132 else -1
            if team >= 0 and hero_id:
                            picks_bans.append({
                                "team": team,
                                "is_pick": True,
                                "hero_id": hero_id,
                                "player_slot": slot,
                                "position": slot_to_position(slot),
                                "hero_items": extract_items(pl),
                                "kills": pl.get("kills"),
                                "deaths": pl.get("deaths"),
                                "assists": pl.get("assists"),
                            })
    # Дополнить picks_bans героями из players (если API вернул не все)
    elif d and picks_bans:
        existing_picks = {(p.get("team"), p.get("hero_id")) for p in picks_bans if p.get("is_pick")}
        for pl in d.get("players", []):
            hero_id = pl.get("hero_id")
            slot = pl.get("player_slot", -1)
            team = 0 if 0 <= slot <= 4 else 1 if 128 <= slot <= 132 else -1
            if team >= 0 and (team, hero_id) not in existing_picks:
                            picks_bans.append({
                                "team": team,
                                "is_pick": True,
                                "hero_id": hero_id,
                                "player_slot": slot,
                                "position": slot_to_position(slot),
                                "hero_items": extract_items(pl),
                                "kills": pl.get("kills"),
                                "deaths": pl.get("deaths"),
                                "assists": pl.get("assists"),
                            })
        # Добавить position и items к существующим пикам
        for p in picks_bans:
                    hero_id = p.get("hero_id")
                    if hero_id in hero_to_player:
                        pl = hero_to_player[hero_id]
                        if "position" not in p:
                            p["player_slot"] = pl.get("player_slot")
                            p["position"] = slot_to_position(pl.get("player_slot"))
                        if "hero_items" not in p:
                            p["hero_items"] = extract_items(pl)
                        if "kills" not in p:
                            p["kills"] = pl.get("kills")
                        if "deaths" not in p:
                            p["deaths"] = pl.get("deaths")
                        if "assists" not in p:
                            p["assists"] = pl.get("assists")

    for p in picks_bans:
        p["hero_name"] = _hero_name(p.get("hero_id", 0))
        # Убедиться что position есть для всех
        hero_id = p.get("hero_id")
        if "position" not in p and hero_id in hero_to_player:
            p["player_slot"] = hero_to_player[hero_id].get("player_slot")
            p["position"] = slot_to_position(hero_to_player[hero_id].get("player_slot"))
        if "hero_items" not in p and hero_id in hero_to_player:
            p["hero_items"] = extract_items(hero_to_player[hero_id])
    return render_template(
        "match_detail.html",
        match=analysis,
        picks_bans=picks_bans,
        our_team=our_team,
        counter_list=_enemy_counters,
        primary=_primary_counter,
    )


@app.route("/report")
def report_page():
    report = generate_full_report(max_matches=100)
    if not report.get("matches"):
        # OpenDota недоступен — строим отчёт по локальной базе games.json.
        local = generate_full_report(max_matches=100, source="local")
        if local.get("matches"):
            local["fallback_reason"] = "open_dota_unavailable"
            report = local
    # Конвертируем markdown в HTML для отображения
    report['report'] = markdown_to_html(report.get('report', ''))
    return render_template("report.html", report=report)


@app.route("/heroes")
def heroes_page():
    stats = global_stats()
    return render_template("heroes.html", stats=stats)


# ── Запуск ──────────────────────────────────────────────────────────────────

# Настройки — из analysis/config.py (env: DOTA_ACCOUNT_ID, DOTA_UPDATE_INTERVAL, PORT)
DEFAULT_ACCOUNT_ID = _cfg.ACCOUNT_ID
AUTO_UPDATE_INTERVAL = _cfg.UPDATE_INTERVAL


def main():
    port = _cfg.PORT
    print(f"\n{'='*55}")
    print(f"  DOTA_MASTER — Web Interface (стиль DOTA 2)")
    print(f"{'='*55}")
    print(f"  Локально:   http://localhost:{port}")
    print(f"  В сети:     http://<ваш-ip>:{port}")
    print(f"  Статистика: {len(get_games())} игр в базе")
    print(f"  Портреты:   https://cdn.opendota.com/heroes/")
    print(f"  Автообновление: каждые {AUTO_UPDATE_INTERVAL} сек (account_id={DEFAULT_ACCOUNT_ID})")
    print(f"{'='*55}\n")

    # Запустить автообновление в фоне
    start_auto_update(
        account_id=DEFAULT_ACCOUNT_ID,
        interval_seconds=AUTO_UPDATE_INTERVAL,
        max_matches=100,
    )

    # Запуск через run_simple (без click-баннера, чтобы избежать краша click на Windows)
    run_simple(
        hostname="0.0.0.0",
        port=port,
        application=app,
        use_reloader=False,
        use_debugger=False,
        threaded=True,
        static_files=None,
    )


if __name__ == "__main__":
    main()

