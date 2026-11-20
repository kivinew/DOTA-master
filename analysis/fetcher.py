# -*- coding: utf-8 -*-
"""Fetches DOTA 2 match history from OpenDota API."""

import json
import os
import time
import urllib.parse
from typing import Optional

from .http import fetch_json as _http_fetch_json, USER_AGENT as DEFAULT_USER_AGENT

BASE_URL = "https://api.opendota.com/api"

# OpenDota rate limiting: ~1000 req/hour for anonymous, but be conservative
RATE_LIMIT_DELAY = 1.0  # seconds between requests


def _fetch_json(url: str, retries: int = 3) -> Optional[dict | list]:
    """Fetch JSON from URL with retries and user-agent (см. analysis/http.py)."""
    return _http_fetch_json(url, retries=retries)


def _steam_id64_to_account_id(steam_id64: str) -> int:
    """Convert SteamID64 to SteamID32 (account_id) for OpenDota API."""
    # SteamID64 is a 64-bit integer; account_id = SteamID64 - 76561197960265728
    sid64 = int(steam_id64)
    return sid64 - 76561197960265728


def _account_id_to_steam_id64(account_id: int) -> int:
    """Convert SteamID32 back to SteamID64."""
    return account_id + 76561197960265728


def resolve_steam_profile(vanity_url: str) -> Optional[int]:
    """
    Resolve a Steam vanity URL (e.g. 'myusername') or profile ID to account_id.
    Uses the Steam Web API — requires a Steam Web API key.
    Without a key we cannot reliably resolve vanity URLs.
    Returns account_id on success, None otherwise.
    """
    # Try to read API key from environment
    api_key = os.environ.get("STEAM_API_KEY") or ""
    if not api_key:
        print("  Warning: STEAM_API_KEY not set — cannot resolve vanity URLs reliably")
        return None

    url = (
        f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
        f"?key={api_key}&vanityurl={urllib.parse.quote(vanity_url)}"
    )
    data = _fetch_json(url, retries=2)
    if data and data.get("response", {}).get("success") == 1:
        return int(data["response"]["steamid"])
    return None


def get_player_matches(
    account_id: int,
    max_matches: int = 100,
    skip_duplicates: Optional[set] = None,
    enrich_missing: bool = True,
) -> list[dict]:
    """
    Fetch recent matches for a DOTA 2 player from OpenDota.

    Args:
        account_id: SteamID32 (account_id) of the player.
        max_matches: maximum number of matches to return.
        skip_duplicates: set of match_id to skip (for incremental fetch).
        enrich_missing: если True, для каждого матча дьём /matches/{match_id}
            и берём свои данные из массива players[].

    Returns:
        List of match dicts (normalized to our internal format).
    """
    url = f"{BASE_URL}/players/{account_id}/recentMatches"
    print(f"  Fetching matches for account_id={account_id} from OpenDota...")
    data = _fetch_json(url)
    if not data:
        # fallback на старый эндпоинт
        data = _fetch_json(f"{BASE_URL}/players/{account_id}/matches")
    if not data:
        return []

    matches = []
    seen_ids = skip_duplicates or set()
    for m in data:
        match_id = m.get("match_id")
        if match_id in seen_ids:
            continue
        # OpenDota list endpoint не содержит gold_per_min/xp_per_min/last_hits
        # — дёргаем детали и нормализуем
        full = _fetch_match_details(match_id, account_id=account_id)
        if full:
            parsed = normalize_open_dota_match(m, full)
        else:
            parsed = normalize_open_dota_match(m, None)
        if parsed:
            matches.append(parsed)
            seen_ids.add(match_id)
        if len(matches) >= max_matches:
            break
        time.sleep(RATE_LIMIT_DELAY)

    print(f"  Got {len(matches)} new matches (skipped {len(seen_ids)} existing)")
    return matches


def _fetch_match_details(match_id: int, account_id: int = None) -> Optional[dict]:
    """Загрузить полные данные матча из /matches/{match_id}.

    Возвращает dict с ключами:
        player_data: dict {player_slot: {...}} — данные игроков из массива players[]
        (kills, deaths, assists, gold_per_min, xp_per_min, last_hits,
         denies, level, net_worth, items, is_radiant, is_our_player)
        radiant_win: bool
        duration: int
        game_mode: int
        lobby_type: int
        start_time: int
        pick_bans: list | None
        account_id: int | None  (из raw данных, может быть None в новых матчах)
    """
    url = f"{BASE_URL}/matches/{match_id}"
    data = _fetch_json(url)
    if not data:
        return None

    player_data = {}
    for p in data.get("players", []):
        slot = p.get("player_slot")
        if slot is None:
            continue
        is_our_player = p.get("account_id") == account_id
        player_data[slot] = {
            "kills": p.get("kills", 0),
            "deaths": p.get("deaths", 0),
            "assists": p.get("assists", 0),
            "gold_per_min": p.get("gold_per_min"),
            "xp_per_min": p.get("xp_per_min"),
            "last_hits": p.get("last_hits"),
            "denies": p.get("denies"),
            "level": p.get("level"),
            "net_worth": p.get("net_worth"),
            "items": [
                (i.get("name_local") or i.get("name") or "")
                for i in (p.get("items") or [])
                if i
            ],
            "is_radiant": 0 <= slot <= 4,
            "is_our_player": is_our_player,
        }

    return {
        "player_data": player_data,
        "radiant_win": data.get("radiant_win"),
        "duration": data.get("duration", 0),
        "game_mode": data.get("game_mode", 0),
        "lobby_type": data.get("lobby_type", 0),
        "start_time": data.get("start_time"),
        "pick_bans": data.get("pick_bans"),
        "account_id": data.get("account_id"),  # may be None in newer matches
    }


def normalize_open_dota_match(raw: dict, enriched: Optional[dict] = None) -> Optional[dict]:
    """
    Convert an OpenDota match object into our internal game record format.

    Args:
        raw: response from /players/{account_id}/matches (list endpoint).
             May lack gold_per_min/xp_per_min/last_hits.
        enriched: optional data from /matches/{match_id} (details endpoint),
                 may contain player_data dict keyed by player_slot.

    Fields mapping:
      - date: match_time / start_time -> ISO date
      - hero: hero_id -> hero name via heroes cache or embedded table
      - result: radiant_win + player_slot -> 'win'/'loss'
        (player_slot 0-4 = Radiant, 128-132 = Dire)
      - kills, deaths, assists: from enriched.player_data[player_slot] if present,
        else from raw (fallback for endpoints that include them)
      - gpm, xpm: same
      - last_hits: same
      - denies: optional
      - game_mode: lobby_type / game_mode
      - draft: pick_bans (если есть в ответе, иначе '')
    """
    try:
        match_id = raw.get("match_id")
        if not match_id:
            return None

        # Timestamp
        ts = raw.get("match_time") or raw.get("start_time")
        if ts is None:
            return None
        import datetime as dt
        # Местное время игрока (UTC+7): утренние игры иначе падают на прошлый день
        dt_local = dt.datetime.fromtimestamp(ts, tz=dt.timezone(dt.timedelta(hours=7)))
        date_iso = dt_local.date().isoformat()

        # Hero
        hero_name = raw.get("hero_name") or ""
        hero_id = raw.get("hero_id")
        if not hero_name and hero_id:
            cache = load_heroes_cache()
            if not cache:
                print("  Кэш героев пуст — загружаю из OpenDota...")
                get_heroes_list()
                cache = load_heroes_cache()
            cached_name = cache.get(str(hero_id))
            if cached_name:
                hero_name = cached_name
            else:
                hero_name = get_hero_name(hero_id)
        hero_display = hero_name.title() if hero_name else f"Hero_{hero_id}"

        # Result: player_slot determines side; radiant_win determines outcome
        player_slot = raw.get("player_slot", 0)
        radiant_win = raw.get("radiant_win", False)
        # Если radiant_win есть в enriched — возьмём оттуда
        if not radiant_win and enriched and "radiant_win" in enriched:
            radiant_win = enriched.get("radiant_win", False)
        is_radiant = 0 <= player_slot <= 4  # Radiant slots
        result = "win" if (is_radiant == radiant_win) else "loss"

        # Player stats: ищем нашего игрока по флагу is_our_player в enriched,
        # fallback на player_slot из списка матчей
        player_stats = {}
        if enriched:
            player_data = enriched.get("player_data", {})
            # Попытка 1: найдём игрока по флагу is_our_player (account_id сопоставлен в enriched)
            for p_slot, p_data in player_data.items():
                if p_data.get("is_our_player"):
                    player_stats = p_data
                    player_slot = p_slot  # перезапишем для is_radiant
                    is_radiant = 0 <= p_slot <= 4
                    result = "win" if (is_radiant == radiant_win) else "loss"
                    break
            # Попытка 2: fallback на player_slot из списка матчей
            if not player_stats:
                player_stats = player_data.get(player_slot, {})
        kills = player_stats.get("kills", raw.get("kills", 0))
        deaths = player_stats.get("deaths", raw.get("deaths", 0))
        assists = player_stats.get("assists", raw.get("assists", 0))
        gpm = player_stats.get("gold_per_min", raw.get("gold_per_min"))
        xpm = player_stats.get("xp_per_min", raw.get("xp_per_min"))
        last_hits = player_stats.get("last_hits", raw.get("last_hits"))
        denies = player_stats.get("denies", 0)
        level = player_stats.get("level", 0)
        net_worth = player_stats.get("net_worth", 0)
        items = player_stats.get("items", [])

        if gpm is None:
            gpm = raw.get("gold_per_min", 0) or 0
        if xpm is None:
            xpm = raw.get("xp_per_min", 0) or 0
        if last_hits is None:
            last_hits = raw.get("last_hits", 0) or 0

        # Game metadata — prefer from enriched, fallback to raw
        game_mode = enriched.get("game_mode", raw.get("game_mode", 0)) if enriched else raw.get("game_mode", 0)
        lobby_type = enriched.get("lobby_type", raw.get("lobby_type", 0)) if enriched else raw.get("lobby_type", 0)
        duration = enriched.get("duration", raw.get("duration", 0)) if enriched else raw.get("duration", 0)
        # Если start_time есть в enriched, используем его (часто детали богаче)
        if enriched and "start_time" in enriched and enriched["start_time"]:
            ts_alt = enriched["start_time"]
            if ts is None or ts == 0:
                ts = ts_alt
                dt_local = dt.datetime.fromtimestamp(ts, tz=dt.timezone(dt.timedelta(hours=7)))
                date_iso = dt_local.date().isoformat()

        # Draft: prefer pick_bans from enriched, fallback to raw
        pick_bans = enriched.get("pick_bans") if enriched else raw.get("pick_bans", [])
        if pick_bans is None:
            pick_bans = raw.get("pick_bans", [])
        draft_allies = _extract_draft(pick_bans, team=1 if is_radiant else 2)
        draft_enemies = _extract_draft(pick_bans, team=2 if is_radiant else 1)

        # RoTL proxy: OpenDota doesn't provide RoTL; set to 0 for now
        rotl = 0.0

        # Notes: empty for now
        notes = ""

        return {
            "date": date_iso,
            "hero": hero_display,
            "role": "",                       # not provided by OpenDota
            "result": result,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "rotl": rotl,
            "last_hits": last_hits,
            "gpm": gpm,
            "xpm": xpm,
            "denies": denies,
            "level": level,
            "net_worth": net_worth,
            "game_mode": str(game_mode),
            "lobby_type": str(lobby_type),
            "duration": duration,
            "draft_allies": draft_allies,
            "draft_enemies": draft_enemies,
            "notes": notes,
            "match_id": match_id,
            "source": "opendota",
        }
    except Exception as e:
        print(f"  Failed to normalize match {raw.get('match_id')}: {e}")
        return None


def _extract_draft(pick_bans: list, team: int) -> str:
    """Extract hero names for one team from pick_bans list."""
    heroes = []
    for pb in pick_bans:
        if pb.get("team") == team and pb.get("is_pick"):
            hid = pb.get("hero_id")
            name = pb.get("hero_name", "")
            if name:
                heroes.append(name.title())
            elif hid:
                heroes.append(f"Hero_{hid}")
    return ", ".join(heroes) if heroes else ""


def get_hero_name(hero_id: int) -> str:
    """
    Look up hero name from hero_id.
    Uses cached hero list from /heroes endpoint first, falls back to embedded table.
    """
    cache = load_heroes_cache()
    if cache and str(hero_id) in cache:
        return cache[str(hero_id)]
    
    # Fallback embedded table (for when API/cache is unavailable).
    # Сгенерировано из data/heroes_cache.json (OpenDota /heroes, 127 героев).
    HERO_TABLE = {
        1: "Anti-Mage",
        2: "Axe",
        3: "Bane",
        4: "Bloodseeker",
        5: "Crystal Maiden",
        6: "Drow Ranger",
        7: "Earthshaker",
        8: "Juggernaut",
        9: "Mirana",
        10: "Morphling",
        11: "Shadow Fiend",
        12: "Phantom Lancer",
        13: "Puck",
        14: "Pudge",
        15: "Razor",
        16: "Sand King",
        17: "Storm Spirit",
        18: "Sven",
        19: "Tiny",
        20: "Vengeful Spirit",
        21: "Windranger",
        22: "Zeus",
        23: "Kunkka",
        25: "Lina",
        26: "Lion",
        27: "Shadow Shaman",
        28: "Slardar",
        29: "Tidehunter",
        30: "Witch Doctor",
        31: "Lich",
        32: "Riki",
        33: "Enigma",
        34: "Tinker",
        35: "Sniper",
        36: "Necrophos",
        37: "Warlock",
        38: "Beastmaster",
        39: "Queen of Pain",
        40: "Venomancer",
        41: "Faceless Void",
        42: "Wraith King",
        43: "Death Prophet",
        44: "Phantom Assassin",
        45: "Pugna",
        46: "Templar Assassin",
        47: "Viper",
        48: "Luna",
        49: "Dragon Knight",
        50: "Dazzle",
        51: "Clockwerk",
        52: "Leshrac",
        53: "Nature's Prophet",
        54: "Lifestealer",
        55: "Dark Seer",
        56: "Clinkz",
        57: "Omniknight",
        58: "Enchantress",
        59: "Huskar",
        60: "Night Stalker",
        61: "Broodmother",
        62: "Bounty Hunter",
        63: "Weaver",
        64: "Jakiro",
        65: "Batrider",
        66: "Chen",
        67: "Spectre",
        68: "Ancient Apparition",
        69: "Doom",
        70: "Ursa",
        71: "Spirit Breaker",
        72: "Gyrocopter",
        73: "Alchemist",
        74: "Invoker",
        75: "Silencer",
        76: "Outworld Destroyer",
        77: "Lycan",
        78: "Brewmaster",
        79: "Shadow Demon",
        80: "Lone Druid",
        81: "Chaos Knight",
        82: "Meepo",
        83: "Treant Protector",
        84: "Ogre Magi",
        85: "Undying",
        86: "Rubick",
        87: "Disruptor",
        88: "Nyx Assassin",
        89: "Naga Siren",
        90: "Keeper of the Light",
        91: "Io",
        92: "Visage",
        93: "Slark",
        94: "Medusa",
        95: "Troll Warlord",
        96: "Centaur Warrunner",
        97: "Magnus",
        98: "Timbersaw",
        99: "Bristleback",
        100: "Tusk",
        101: "Skywrath Mage",
        102: "Abaddon",
        103: "Elder Titan",
        104: "Legion Commander",
        105: "Techies",
        106: "Ember Spirit",
        107: "Earth Spirit",
        108: "Underlord",
        109: "Terrorblade",
        110: "Phoenix",
        111: "Oracle",
        112: "Winter Wyvern",
        113: "Arc Warden",
        114: "Monkey King",
        119: "Dark Willow",
        120: "Pangolier",
        121: "Grimstroke",
        123: "Hoodwink",
        126: "Void Spirit",
        128: "Snapfire",
        129: "Mars",
        131: "Ringmaster",
        135: "Dawnbreaker",
        136: "Marci",
        137: "Primal Beast",
        138: "Muerta",
        145: "Kez",
        155: "Largo",
    }
    return HERO_TABLE.get(hero_id, f"Hero_{hero_id}")


def get_heroes_list() -> list[dict]:
    """
    Get full hero list from OpenDota (with localized names).
    Caches to data/heroes_cache.json.
    """
    cache_path = os.path.join(os.path.dirname(__file__), "..", "data", "heroes_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = f"{BASE_URL}/heroes"
    print("  Fetching hero list from OpenDota...")
    data = _fetch_json(url)
    if data:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    return []


def load_heroes_cache() -> dict:
    """Load cached hero list into a {hero_id: name} mapping."""
    cache_path = os.path.join(os.path.dirname(__file__), "..", "data", "heroes_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            heroes = json.load(f)
        return {str(h.get("id")): h.get("localized_name", h.get("name", "")).replace("npc_dota_hero_", "").title() for h in heroes}
    return {}


def save_matches(games: list[dict]) -> int:
    """Save fetched games to games.json (append, deduplicate by match_id)."""
    from .stats_engine import _load_games, _save_games

    existing = _load_games()
    existing_ids = {g.get("match_id") for g in existing if g.get("match_id")}
    new_games = [g for g in games if g.get("match_id") not in existing_ids]
    existing.extend(new_games)
    _save_games(existing)
    return len(new_games)
