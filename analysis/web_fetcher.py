# -*- coding: utf-8 -*-
"""DOTA_MASTER — парсер страниц OpenDota (альтернатива API)."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from .http import fetch_json as _http_fetch_json, BROWSER_USER_AGENT

# Часовой пояс игрока (Новосибирск, UTC+7, без DST).
# Даты игр храним по местному времени, иначе утренние игры
# (после полуночи) отображаются предыдущим днём (UTC).
LOCAL_TZ = timezone(timedelta(hours=7))


def fetch_matches_from_web(account_id: str, max_recent: int = 20, max_extra: int = 30) -> list[dict]:
    """
    Загрузить данные с OpenDota API.

    Стратегия:
      1. Всегда запрашиваем recentMatches — быстро, ~20 матчей.
      2. Если все 20 уже в базе → новых игр нет, не тратим лишний запрос.
      3. Если самый свежий матч в recentMatches старше 30 минут —
         значит API мог пропустить период (522, задержка). Тогда делаем
         догоняющий запрос к /matches?limit=max_extra (не 100!).
      4. Объединяем результаты, убирая дубликаты по match_id.
    """
    import time as _time

    # Шаг 1: запрашиваем recentMatches
    recent = _fetch_url(
        f"https://api.opendota.com/api/players/{account_id}/recentMatches"
    )
    if not recent:
        # recentMatches не отработал — пробуем fallback
        return _fetch_matches_fallback(account_id, max_extra)

    recent_sorted = sorted(recent, key=lambda m: m.get("start_time", 0), reverse=True)
    if not recent_sorted:
        return []

    # Самый свежий матч
    newest_ts = recent_sorted[0].get("start_time", 0)
    now_ts = _time.time()
    age_minutes = (now_ts - newest_ts) / 60 if newest_ts else 999

    if age_minutes > 30:
        # В recentMatches только старые игры — мог пропуск
        print(f"  Самый свежий матч {age_minutes:.0f} мин назад — возможен пропуск, догнаём...")
        extra = _fetch_matches_fallback(account_id, max_extra)
        if extra:
            # Убираем дубликаты: оставляем только новые из extra
            known_ids = {m.get("match_id") for m in recent}
            new_extra = [m for m in extra if m.get("match_id") not in known_ids]
            recent.extend(new_extra)
            print(f"  Из догоняющих: {len(new_extra)} новых матчей (всего {len(recent)})")
    else:
        print(f"  Самый свежий матч {age_minutes:.0f} мин назад — пропуска нет")

    return recent


def _fetch_url(url: str) -> list[dict]:
    """Загрузить JSON с переданного URL. Возвращает [] при ошибке."""
    print(f"  Загружаю {url}...")
    data = _http_fetch_json(url, user_agent=BROWSER_USER_AGENT)
    if isinstance(data, list) and data:
        print(f"  Получено {len(data)} матчей")
        return data
    return []


def _fetch_matches_fallback(account_id: str, max_extra: int = 30) -> list[dict]:
    """Дополнительный запрос к /matches для получения игр, выпавших из recentMatches."""
    url = f"https://api.opendota.com/api/players/{account_id}/matches?limit={min(max_extra, 100)}&sort=start_time"
    data = _fetch_url(url)
    if data:
        data.sort(key=lambda m: m.get("start_time", 0), reverse=True)
    return data


def parse_match_from_web(data: dict) -> Optional[dict]:
    """
    Преобразовать матч из веб-API в наш внутренний формат.
    
    Ожидаемые поля в data:
    - match_id: int
    - start_time: int (unix timestamp)
    - duration: int (секунды)
    - game_mode: int
    - lobby_type: int
    - player_slot: int (0-4 Radiant, 128-132 Dire)
    - radiant_win: bool
    - kills, deaths, assists: int
    - gold_per_min: float|None
    - xp_per_min: float|None
    - last_hits: int|None
    - denies: int|None
    - hero_id: int
    - hero_name: str|None (иногда отсутствует)
    """
    try:
        match_id = data.get("match_id")
        if not match_id:
            return None
        
        # Дата — по местному времени игрока (см. LOCAL_TZ выше)
        start_time = data.get("start_time")
        if start_time:
            dt_local = datetime.fromtimestamp(start_time, tz=LOCAL_TZ)
            date_iso = dt_local.strftime("%Y-%m-%d")
            date_full = dt_local.strftime("%Y-%m-%d %H:%M:%S +07")
        else:
            date_iso = ""
            date_full = ""
        
        # Герой
        hero_id = data.get("hero_id")
        hero_name = data.get("hero_name", "")
        if not hero_name:
            from .fetcher import load_heroes_cache, get_hero_name
            cache = load_heroes_cache()
            cached = cache.get(str(hero_id))
            if cached:
                hero_name = cached
            elif hero_id:
                hero_name = get_hero_name(hero_id)
        hero_display = hero_name.title() if hero_name else f"Hero_{hero_id}"
        
        # Сторона и результат
        player_slot = data.get("player_slot", 0)
        radiant_win = data.get("radiant_win", False)
        is_radiant = 0 <= player_slot <= 4
        result = "win" if (is_radiant == radiant_win) else "loss"
        
        # Статистика
        kills = data.get("kills", 0)
        deaths = data.get("deaths", 0)
        assists = data.get("assists", 0)
        gpm = data.get("gold_per_min", 0) or 0
        xpm = data.get("xp_per_min", 0) or 0
        last_hits = data.get("last_hits", 0) or 0
        denies = data.get("denies", 0) or 0
        
        # Доп. поля
        duration = data.get("duration", 0)
        game_mode = data.get("game_mode", 0)
        lobby_type = data.get("lobby_type", 0)
        
        # RoTL — в веб-API тоже нет, оставляем 0
        rotl = 0.0
        
        # Драфт — в /matches/{id} есть pick_bans, но в /players/{id}/matches обычно нет
        pick_bans = []
        
        return {
            "date": date_iso,
            "date_full": date_full,
            "hero": hero_display,
            "hero_id": hero_id,
            "role": "",
            "result": result,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "rotl": rotl,
            "last_hits": last_hits,
            "gpm": gpm,
            "xpm": xpm,
            "denies": denies,
            "level": 0,  # в web API обычно нет level
            "net_worth": 0,
            "game_mode": str(game_mode),
            "lobby_type": str(lobby_type),
            "duration": duration,
            "draft_allies": "",
            "draft_enemies": "",
            "notes": "",
            "match_id": match_id,
            "source": "opendota_web",
        }
    except Exception as e:
        print(f"  Ошибка парсинга матча {data.get('match_id')}: {e}")
        return None


def fetch_and_save(account_id: str, max_matches: int = 30) -> int:
    """Загрузить и сохранить матчи из веб-API."""
    from .stats_engine import _load_games, _save_games
    
    # Загружаем: recentMatches + опционально догоняющие (не более max_matches)
    web_matches = fetch_matches_from_web(account_id, max_recent=20, max_extra=min(max_matches, 100))
    if not web_matches:
        return 0
    
    # Ограничиваем итоговый размер
    if len(web_matches) > max_matches:
        web_matches = web_matches[:max_matches]
    
    # Преобразуем в наш формат
    parsed = []
    for m in web_matches:
        game = parse_match_from_web(m)
        if game:
            parsed.append(game)
    
    # Загружаем существующие игры для проверки дубликатов
    existing = _load_games()
    existing_ids = {g.get("match_id") for g in existing if g.get("match_id")}
    
    # Добавляем только новые
    new_games = [g for g in parsed if g.get("match_id") not in existing_ids]
    existing.extend(new_games)
    _save_games(existing)
    
    print(f"  Сохранено {len(new_games)} новых матчей (всего в выборке: {len(parsed)})")
    return len(new_games)


_MEDALS = {1: "Herald", 2: "Guardian", 3: "Crusader", 4: "Archon", 5: "Legend"}


def _mode_label(game_mode: int, avg_rank) -> str:
    """Короткая подпись моды: 'Turbo Archon [4]'."""
    base = {23: "Turbo", 22: "Ranked", 1: "Normal", 4: "Coop"}.get(game_mode, f"Mode {game_mode}")
    try:
        r = int(avg_rank)
        medal = _MEDALS.get(r // 10, "")
        star = r % 10 or 1
        if medal:
            return f"{base} {medal} [{star}]"
    except (TypeError, ValueError):
        pass
    return base


def _time_ago(ts: int) -> str:
    """Относительное время по-местному: '5 мин назад', '2 ч назад'."""
    import time as _t
    mins = max(0, int((_t.time() - ts) / 60))
    if mins < 1:
        return "только что"
    if mins < 60:
        return f"{mins} мин назад"
    hours = mins // 60
    if hours < 24:
        return f"{hours} ч назад"
    return f"{hours // 24} дн назад"


def get_fresh_view(account_id: str, limit: int = 20) -> list[dict]:
    """Живые свежие матчи для страницы /fresh — тот же формат, что fresh_matches.json.

    Ключи: hero, match_id (str), time_ago, result, K, D, A,
    duration "MM:SS", side, game_mode, date (для сортировки).
    """
    from .fetcher import load_heroes_cache, get_hero_name

    raw = fetch_matches_from_web(account_id, max_recent=20, max_extra=10)[:limit]
    if not raw:
        return []
    cache = load_heroes_cache()
    out = []
    for m in raw:
        hero_id = m.get("hero_id")
        hero_name = cache.get(str(hero_id), "") if cache else ""
        if not hero_name and hero_id:
            hero_name = get_hero_name(hero_id)
        hero_display = hero_name.title() if hero_name else f"Hero_{hero_id}"
        slot = m.get("player_slot", 0)
        is_radiant = 0 <= slot <= 4
        result = "win" if (is_radiant == bool(m.get("radiant_win"))) else "loss"
        dur = m.get("duration") or 0
        ts = m.get("start_time") or 0
        out.append({
            "hero": hero_display,
            "match_id": str(m.get("match_id", "")),
            "time_ago": _time_ago(ts) if ts else "",
            "result": result,
            "K": m.get("kills", 0),
            "D": m.get("deaths", 0),
            "A": m.get("assists", 0),
            "duration": f"{dur // 60}:{dur % 60:02d}",
            "side": "Radiant" if is_radiant else "Dire",
            "game_mode": _mode_label(m.get("game_mode", 0), m.get("average_rank")),
            "date": datetime.fromtimestamp(ts, tz=LOCAL_TZ).strftime("%Y-%m-%d %H:%M") if ts else "",
        })
    return out
