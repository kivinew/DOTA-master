# -*- coding: utf-8 -*-
"""DOTA_MASTER — макро-анализ матчей.

Сравнивает показатели игрока с эталонными для ранга Legend (50-59),
находит частые ошибки и даёт рекомендации по макро-игре.
"""

import json
import os
import statistics
from datetime import timezone, timedelta
from collections import Counter, defaultdict
from typing import Optional

from .http import fetch_json as _http_fetch_json

# Load ability display names from local file
def _load_ability_names() -> dict:
    """Загрузить маппинг ability_id -> display_name из data/ability_names.json."""
    cache_path = os.path.join("data", "ability_names.json")
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # JSON keys are strings, convert to int
        return {int(k): v for k, v in raw.items()}
    except Exception:
        return {}

ABILITY_DISPLAY_NAMES = _load_ability_names()

# ── Конфигурация ──────────────────────────────────────────────────────────────

from .config import ACCOUNT_ID, STEAM_ID64
LOCAL_TZ = timezone(timedelta(hours=7))

# Эталонные значения для ранга Legend (50-59) — Turbo/Normal
# Источник: усреднённые данные Dotabuff/Stratz за 2025-2026
BENCHMARKS = {
    "gpm": {"low": 450, "mid": 600, "high": 750},      # gold per minute
    "xpm": {"low": 500, "mid": 700, "high": 900},      # xp per minute
    "lhpm": {"low": 4.0, "mid": 6.0, "high": 8.0},     # last hits per minute
    "dpm": {"low": 400, "mid": 600, "high": 800},      # hero damage per minute
    "td": {"low": 1000, "mid": 3000, "high": 6000},    # tower damage total
    "deaths": {"good": 4, "warn": 7, "bad": 10},       # deaths per game
    "kda": {"low": 2.0, "mid": 3.5, "high": 5.0},      # (K+A)/D
}

# Прокачка Pugna (hero_id=45) — эталонный билд для Turbo
# ability IDs: 5186=Decrepify, 5187=Nether Blast, 5188=Nether Ward, 5189=Life Drain, 6448=Aghanim's Scepter, 5903=Aghanim's Shard, 6541=Moon Shard
PUGNA_SKILL_NAMES = {
    5186: "Decrepify",
    5187: "Nether Blast",
    5188: "Nether Ward",
    5189: "Life Drain",
    6448: "Aghanim Scepter",
    5903: "Aghanim Shard",
    6541: "Moon Shard",
}

# Рекомендации по макро-игре
MACRO_TIPS = {
    "low_gpm": [
        "Твой GPM ниже нормы для ранга. Смотри на миникарту и не теряй время в пустую.",
        "После каждой волны крипов — зачисти нейтральный лагерь. Не стой в луже.",
        "Если линия ушла далеко — фарм в джангле, не теряй время ожидая.",
    ],
    "low_xpm": [
        "Твой XPM низкий. Ты пропускаешь крипов или слишком умираешь.",
        "Старайся быть рядом с умирающими крипами или героями для получения опыта.",
        "Используй Town Portal для возврата на линию после смерти.",
    ],
    "low_lh": [
        "Мало ластхитов. Практикуй тайминги в тренировке.",
        "Используй способности для быстрого зачищения волн, если герой позволяет.",
        "Не забывай про дайны — это золото тебе и опыт врагу.",
    ],
    "high_deaths": [
        "Слишком много смертей. Проверяй миникарту после каждого каста.",
        "Не лез в бой без видения — жди пока враги покажутся на карте.",
        "Держи дистанцию — герой уязвим, не стой в первых рядах.",
    ],
    "low_tower": [
        "Мало урона по башням. После драки — сразу пуш линию.",
        "Цель игры — уничтожить казну, а не убить героев.",
        "Используй Nether Ward для защиты башен и контроля территории.",
    ],
    "low_hero_dmg": [
        "Мало урона по героям. Участвуй в драках, но не умирай.",
        "Decrepify на вражеского керри в начале драки = огромный вклад.",
        "Life Drain — не только для убийств, но и для фарма в джангле.",
    ],
    "good": [
        "Отличная игра! Продолжай в том же духе.",
        "Твой вклад в команду значителен — ты делаешь разницу.",
    ],
}

# ── Загрузка данных ───────────────────────────────────────────────────────────

def _fetch_json(url: str, timeout: int = 30) -> Optional[dict | list]:
    """Загрузить JSON с API (см. analysis/http.py)."""
    return _http_fetch_json(url, timeout=timeout)


def get_match_details(match_id: int) -> Optional[dict]:
    """Загрузить детали матча."""
    return _fetch_json(f"https://api.opendota.com/api/matches/{match_id}")


def get_player_match(match_id: int, account_id: int = ACCOUNT_ID) -> Optional[dict]:
    """Найти данные игрока в матче."""
    d = get_match_details(match_id)
    if not d:
        return None
    for p in d.get("players", []):
        if p.get("account_id") == account_id:
            return p
    return None


# ── Анализ билда ─────────────────────────────────────────────────────────────

# Загружаем имена скиллов для героев из локального кэша (data/hero_ability_names.json)
def _load_hero_ability_names() -> dict:
    """Загрузить маппинг hero_id -> {ability_id: ability_name} из data/hero_ability_names.json."""
    cache_path = os.path.join("data", "hero_ability_names.json")
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # JSON keys are strings, convert to int
        result = {}
        for hero_id_str, ability_map in raw.items():
            try:
                hero_id = int(hero_id_str)
                result[hero_id] = {int(k): v for k, v in ability_map.items()}
            except (ValueError, TypeError):
                pass
        return result
    except Exception:
        return {}


def _clean_ability_name(name: str) -> str:
    """Очистить шаблонные строки типа '+{s:bonus_...} Name' до 'Name'."""
    import re
    if not name:
        return name
    m = re.search(r"\}(.*)", name)
    if m:
        cleaned = m.group(1)
    else:
        cleaned = name
    cleaned = re.sub(r"^[\+\-\%\s\ds]*", "", cleaned)
    cleaned = re.sub(r"\{[^}]+\}", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = re.sub(r"\{[^}]+\}", "", name).strip()
        cleaned = re.sub(r"^[\+\-\%\s\ds]*", "", cleaned).strip()
    return cleaned if cleaned else name


HERO_ABILITIES = _load_hero_ability_names()

# Применяем очистку ко всем загруженным названиям способностей
for hero_id in HERO_ABILITIES:
    HERO_ABILITIES[hero_id] = {
        k: _clean_ability_name(v) for k, v in HERO_ABILITIES[hero_id].items()
    }


def analyze_skill_build(ability_upgrades: list[int], hero_id: int = 0) -> dict:
    """Анализ последовательности прокачки скиллов для любого героя."""
    if not ability_upgrades:
        return {"build": [], "notes": ["Нет данных о прокачке"]}

    # Получаем имена скиллов для этого героя (из heroes_cache.json если есть)
    ability_names = HERO_ABILITIES.get(hero_id, {})
    # Фоллбэк на глобальный маппинг ability_names.json
    for aid, name in ABILITY_DISPLAY_NAMES.items():
        if aid not in ability_names:
            ability_names[aid] = name

    # Фильтруем: убираем таланты (обычно ID > 6000 или специальные ID),
    # Aghanim's Scepter (6448), Aghanim's Shard (5903), Moon Shard (6541)
    # Оставляем только базовые скиллы (обычно ID < 6000, исключая специальные)
    SPECIAL_ABILITIES = {6448, 5903, 6541, 775, 776, 777, 778, 779, 780, 781, 782, 783, 784, 785, 786, 787, 788, 789, 790}
    # Таланты обычно имеют ID в диапазоне 6000+ или конкретные ID

    build = []
    for a in ability_upgrades:
        # Пропускаем специальные способности (Скиптер/Шард/Мун шард)
        if a in SPECIAL_ABILITIES:
            continue
        # Пропускаем таланты (ID >= 6000) — у них нет иконок, не показываем в билде
        if a >= 6000:
            continue
        name = ability_names.get(a, f"Ability_{a}")
        build.append({"id": a, "name": name})

    notes = []
    skill_counts = Counter(ability_upgrades)

    # Для героя с известными скиллами можно добавить специфические проверки
    # Пока общая логика: проверяем что ульт взят до 7 уровня (первый скилл с ID не в базовых 3)
    # Базовые скиллы обычно берутся на 1-5 уровнях, ульт на 6
    basic_skills = set()
    for aid, count in skill_counts.items():
        if aid in SPECIAL_ABILITIES or aid >= 6000:
            continue
        name = ability_names.get(aid, f"Ability_{aid}")
        # Исключаем улучшения талантов и специальные способности (они содержат слова типа Cooldown, Duration, Range и т.п.)
        improvement_keywords = ["Cooldown", "Duration", "Range", "Radius", "Per ", "Hits ", "Corruption", "Recovery", "Regeneration", "Mana ", "Movement ", "Armor ", "Heal ", "Damage Per"]
        if any(kw in name for kw in improvement_keywords):
            continue
        basic_skills.add(aid)

    # Найти ульт (обычно 4-й базовый скилл, берется на 6+ уровне)
    # Эвристика: ульт — это скилл, который берется только 1-3 раза и обычно позже
    ult_ability_id = None
    for aid in ability_upgrades:
        if aid in SPECIAL_ABILITIES or aid >= 6000:
            continue
        if aid not in basic_skills:
            continue
        # Проверяем, когда впервые взят этот скилл
        first_idx = ability_upgrades.index(aid)
        if first_idx >= 5:  # 6-й уровень (0-indexed = 5)
            # Это может быть ульт
            ult_ability_id = aid
            ult_name = ability_names.get(aid, f"Ability_{aid}")
            if first_idx > 6:
                notes.append(f"⚠️ {ult_name} взят поздно (уровень {first_idx + 1}). Обычно на 6-7.")
            elif first_idx < 5:
                notes.append(f"⚠️ {ult_name} взят рано (уровень {first_idx + 1}). Обычно на 6-7.")
            break

    # Проверить что базовые скиллы прокачаны до макса
    # Ульта макс 3 уровня (6/12/18), базовые скиллы макс 4 уровня
    for aid in basic_skills:
        if aid in SPECIAL_ABILITIES or aid >= 6000:
            continue
        count = skill_counts.get(aid, 0)
        skill_name = ability_names.get(aid, f"Ability_{aid}")
        max_level = 3 if aid == ult_ability_id else 4
        if count < max_level:
            notes.append(f"⚠️ {skill_name} прокачан {count}/{max_level} — ключевой скилл.")

    return {"build": build, "notes": notes, "skill_counts": dict(skill_counts)}


# ── Анализ айтемов ───────────────────────────────────────────────────────────

# Ключевые айтемы для проверки по героям: hero_id -> список проверок.
# Каждая проверка — (обязательный_айтом, альтернативный_айтом, текст_рекомендации).
# Советы выдаются только для героя из этой маппинга: рекомендации «протекают»
# на всех героев подряд, поэтому проверки должны быть привязаны к конкретному герою.
KEY_ITEM_CHECKS: dict[int, list[tuple[int, int, str]]] = {
    45: [  # Pugna — хрупкий спеллкастер, держи дистанцию и дальность каста
        (119, 100, "⚠️ Нет Hex или Aghanim's — ключевые айтемы для этого героя."),
        (232, 108, "ℹ️ Нет Aether Lens/Octarine Core — дальность каста страдает."),
    ],
}


def analyze_items(items: list[int], neutral: int = 0, hero_id: int = 0) -> dict:
    """Анализ финальных айтемов (без таймингов, только наличие).
    Имена берутся из data/items_cache.json (501 предмет), неизвестные — Item_{id}.
    Предметы с id=0 (пустой слот) исключаются.
    Рекомендации по ключевым айтемам выдаются только для hero_id из KEY_ITEM_CHECKS.
    """
    from analysis.icons import _ITEM_CACHE

    NEUTRAL_ITEMS = {
        1864: "Pupil's Gift",
        1592: "Trusty Shovel",
        389: "Nemesis Cloak",
        1583: "Mind Breaker",
        1640: "Rattler Charm",
        1637: "Doubloon",
        1638: "Galactic Finch",
        1158: "Whisper of the Dread",
        1593: "Pig Pole",
        1595: "Wand of the Brine",
    }

    found = []
    for item_id in items:
        if not item_id:
            continue  # пустой слот
        name = _ITEM_CACHE.get(item_id)
        if name:
            found.append({"id": item_id, "name": name.replace("_", " ").title()})
        elif item_id in NEUTRAL_ITEMS:
            found.append({"id": item_id, "name": NEUTRAL_ITEMS[item_id]})
        else:
            found.append({"id": item_id, "name": f"Item_{item_id}"})

    if neutral:
        neutral_name = NEUTRAL_ITEMS.get(neutral) or _ITEM_CACHE.get(neutral)
        if neutral_name:
            found.append({"id": neutral, "name": neutral_name.replace("_", " ").title() if neutral_name.islower() else neutral_name})
        elif neutral:
            found.append({"id": neutral, "name": f"Neutral_{neutral}"})

    # Рекомендации только по айтемам конкретного героя (KEY_ITEM_CHECKS)
    notes = []
    for required, alternative, note in KEY_ITEM_CHECKS.get(hero_id or 0, []):
        if required in items or alternative in items:
            continue  # один из ключевых айтемов уже есть — рекомендация не нужна
        notes.append(note)

    return {"items": found, "notes": notes}


# ── Основной анализ матча ────────────────────────────────────────────────────

_MATCH_DETAILS_UNSET = object()


def analyze_match(
    match_id: int,
    account_id: int = ACCOUNT_ID,
    player_slot: Optional[int] = None,
    match_data=_MATCH_DETAILS_UNSET,
) -> Optional[dict]:
    """Analyze one match; callers may pass already-fetched details to avoid duplicate API calls."""
    d = get_match_details(match_id) if match_data is _MATCH_DETAILS_UNSET else match_data
    if not d:
        return None
    p = None
    for pl in d.get("players", []):
        if pl.get("account_id") == account_id:
            p = pl
            break
    if p is None and player_slot is not None:
        for pl in d.get("players", []):
            if pl.get("player_slot") == player_slot:
                p = pl
                break
    if p is None:
        return None

    duration = p.get("duration", 1)
    dur_min = duration / 60.0

    # Итоговый счет
    radiant_score = d.get("radiant_score")
    dire_score = d.get("dire_score")
    radiant_win = bool(d.get("radiant_win", False))

    # Базовые метрики
    kills = p.get("kills", 0)
    deaths = p.get("deaths", 0)
    assists = p.get("assists", 0)
    gpm = p.get("gold_per_min", 0)
    xpm = p.get("xp_per_min", 0)
    lh = p.get("last_hits", 0)
    denies = p.get("denies", 0)
    hd = p.get("hero_damage", 0)
    td = p.get("tower_damage", 0)
    hh = p.get("hero_healing", 0)
    level = p.get("level", 0)
    net_worth = p.get("net_worth", 0)

    lhpm = lh / dur_min if dur_min > 0 else 0
    dpm = hd / dur_min if dur_min > 0 else 0
    kda = (kills + assists) / max(deaths, 1)

    # ── Вычисление MVP ──────────────────────────────────────────────────────────
    def _calc_mvp_score(p):
        """Взвешенная оценка игрока для определения MVP + бонус за победу."""
        kills = p.get("kills", 0)
        deaths = p.get("deaths", 0)
        assists = p.get("assists", 0)
        gpm = p.get("gold_per_min", 0)
        hd = p.get("hero_damage", 0)
        kda = (kills + assists) / max(deaths, 1)
        # KDA (важнее всего) + GPM/100 + HD/1000 + бонус за победу
        score = kda * 3 + gpm / 100 + hd / 1000
        if p.get("win") == 1:  # Бонус за победу
            score += 10
        return score

    for pl in d.get("players", []):
        pl["_mvp"] = _calc_mvp_score(pl)

    # Найти MVP
    mvp_player = max(d.get("players", []), key=lambda p: p.get("_mvp", 0), default=None)
    mvp_team = None
    if mvp_player:
        mvp_slot = mvp_player.get("player_slot", 0)
        mvp_team = "Radiant" if 0 <= mvp_slot <= 4 else "Dire"
    our_team = []
    enemy_team = []
    our_slot = p.get("player_slot", 0)
    is_radiant = 0 <= our_slot <= 4
    for pl in d.get("players", []):
        if pl.get("account_id") == ACCOUNT_ID:
            continue
        pl_slot = pl.get("player_slot", 0)
        if is_radiant:
            (our_team if (0 <= pl_slot <= 4) else enemy_team).append(pl)
        else:
            (our_team if (128 <= pl_slot <= 132) else enemy_team).append(pl)

    def _avg(lst, key, default=0):
        vals = [x.get(key, 0) or 0 for x in lst if x.get(key) is not None]
        return sum(vals) / len(vals) if vals else default

    # Среднее LH/мин по команде
    team_lhpms = [x.get("last_hits", 0) / max(x.get("duration", 1) / 60, 0.1) for x in our_team]
    team_avg = {
        "gpm": round(_avg(our_team, "gold_per_min")),
        "xpm": round(_avg(our_team, "xp_per_min")),
        "kills": round(_avg(our_team, "kills"), 1),
        "deaths": round(_avg(our_team, "deaths"), 1),
        "lhpm": round(statistics.mean(team_lhpms), 2) if team_lhpms else 0,
    }
    enemy_avg = {
        "gpm": round(_avg(enemy_team, "gold_per_min")),
        "xpm": round(_avg(enemy_team, "xp_per_min")),
        "kills": round(_avg(enemy_team, "kills"), 1),
    }

    # Процент вклада в команду
    team_total_kills = sum(x.get("kills", 0) for x in our_team) + kills
    team_total_hd = sum(x.get("hero_damage", 0) for x in our_team) + hd
    team_total_td = sum(x.get("tower_damage", 0) for x in our_team) + td
    team_total_healing = sum(x.get("hero_healing", 0) for x in our_team) + hh
    team_total_lh = sum(x.get("last_hits", 0) for x in our_team) + lh + denies
    team_total_gold = sum(x.get("gold_per_min", 0) for x in our_team) + gpm
    team_total_xp = sum(x.get("xp_per_min", 0) for x in our_team) + xpm
    kill_part = round(kills / max(team_total_kills, 1) * 100, 1)
    damage_part = round(hd / max(team_total_hd, 1) * 100, 1)
    tower_part = round(td / max(team_total_td, 1) * 100, 1)
    healing_part = round(hh / max(team_total_healing, 1) * 100, 1)
    lh_part = round((lh + denies) / max(team_total_lh, 1) * 100, 1)
    gpm_part = round(gpm / max(team_total_gold, 1) * 100, 1)
    xpm_part = round(xpm / max(team_total_xp, 1) * 100, 1)

    # Рейтинг в матче по GPM
    all_gpms = sorted([pl.get("gold_per_min", 0) for pl in d.get("players", [])], reverse=True)
    gpm_rank = all_gpms.index(gpm) + 1 if gpm in all_gpms else "?"

    # Оценка по бенчмаркам
    scores = {}
    scores["gpm"] = "low" if gpm < BENCHMARKS["gpm"]["low"] else ("mid" if gpm < BENCHMARKS["gpm"]["mid"] else "high")
    scores["xpm"] = "low" if xpm < BENCHMARKS["xpm"]["low"] else ("mid" if xpm < BENCHMARKS["xpm"]["mid"] else "high")
    scores["lhpm"] = "low" if lhpm < BENCHMARKS["lhpm"]["low"] else ("mid" if lhpm < BENCHMARKS["lhpm"]["mid"] else "high")
    scores["dpm"] = "low" if dpm < BENCHMARKS["dpm"]["low"] else ("mid" if dpm < BENCHMARKS["dpm"]["mid"] else "high")
    scores["td"] = "low" if td < BENCHMARKS["td"]["low"] else ("mid" if td < BENCHMARKS["td"]["mid"] else "high")
    scores["deaths"] = "good" if deaths <= BENCHMARKS["deaths"]["good"] else ("warn" if deaths <= BENCHMARKS["deaths"]["warn"] else "bad")
    scores["kda"] = "low" if kda < BENCHMARKS["kda"]["low"] else ("mid" if kda < BENCHMARKS["kda"]["mid"] else "high")
    scores["kill_part"] = "low" if kill_part < 15 else ("mid" if kill_part < 25 else "high")

    # Рекомендации
    tips = []
    if scores["gpm"] == "low":
        tips.extend(MACRO_TIPS["low_gpm"][:2])
    if scores["xpm"] == "low":
        tips.extend(MACRO_TIPS["low_xpm"][:1])
    if scores["lhpm"] == "low":
        tips.extend(MACRO_TIPS["low_lh"][:1])
    if scores["deaths"] in ("warn", "bad"):
        tips.extend(MACRO_TIPS["high_deaths"][:2])
    if scores["td"] == "low":
        tips.extend(MACRO_TIPS["low_tower"][:1])
    if scores["dpm"] == "low":
        tips.extend(MACRO_TIPS["low_hero_dmg"][:1])
    if gpm < team_avg["gpm"]:
        tips.append(f"📉 Твой GPM ниже среднего по команде ({gpm} vs {team_avg['gpm']}). Фарми эффективнее или проси пространство.")
    if kill_part < 15:
        tips.append(f"🤝 Твой вклад в убийства всего {kill_part}%. Участвуй в драках активнее.")
    if not tips:
        tips.extend(MACRO_TIPS["good"][:1])

    # Анализ билда
    skill_analysis = analyze_skill_build(p.get("ability_upgrades_arr", []), p.get("hero_id") or 0)

    # Анализ айтемов
    items = [p.get(f"item_{i}", 0) for i in range(6)]
    item_analysis = analyze_items(items, p.get("item_neutral", 0), p.get("hero_id") or 0)

    # MVP Radiant и Dire (compute before return)
    radiant_mvp = max([pl for pl in d.get("players", []) if 0 <= pl.get("player_slot", 0) <= 4], key=lambda p: p.get("_mvp", 0), default=None)
    dire_mvp = max([pl for pl in d.get("players", []) if 128 <= pl.get("player_slot", 0) <= 132], key=lambda p: p.get("_mvp", 0), default=None)

    return {
        "match_id": match_id,
        "hero_id": p.get("hero_id"),
        "hero_name": _hero_name(p.get("hero_id", 0)),
        "result": "win" if p.get("win") else "loss",
        "radiant_win": radiant_win,
        "duration": duration,
        "radiant_score": radiant_score,
        "dire_score": dire_score,
        "level": level,
        "net_worth": net_worth,
        "kills": kills, "deaths": deaths, "assists": assists,
        "gpm": gpm, "xpm": xpm,
        "last_hits": lh, "denies": denies,
        "lhpm": round(lhpm, 2),
        "hero_damage": hd, "tower_damage": td, "hero_healing": hh,
        "dpm": round(dpm, 1),
        "kda": round(kda, 2),
        "kill_part": kill_part,
        "damage_part": damage_part,
        "tower_part": tower_part,
        "healing_part": healing_part,
        "lh_part": lh_part,
        "gpm_part": gpm_part,
        "xpm_part": xpm_part,
        "gpm_rank": gpm_rank,
        "team_avg": team_avg,
        "enemy_avg": enemy_avg,

        "mvp_radiant": {
            "name": radiant_mvp.get("personaname", "?") if radiant_mvp else "?",
            "hero_id": radiant_mvp.get("hero_id", 0) if radiant_mvp else 0,
            "hero_name": _hero_name(radiant_mvp.get("hero_id", 0)) if radiant_mvp else "?",
            "team": "Radiant",
            "kda": round((radiant_mvp.get("kills", 0) + radiant_mvp.get("assists", 0)) / max(radiant_mvp.get("deaths", 1), 1), 2) if radiant_mvp else 0,
            "kills": radiant_mvp.get("kills", 0) if radiant_mvp else 0,
            "deaths": radiant_mvp.get("deaths", 0) if radiant_mvp else 0,
            "assists": radiant_mvp.get("assists", 0) if radiant_mvp else 0,
            "gpm": radiant_mvp.get("gold_per_min", 0) if radiant_mvp else 0,
            "xpm": radiant_mvp.get("xp_per_min", 0) if radiant_mvp else 0,
            "score": round(radiant_mvp.get("_mvp", 0), 1) if radiant_mvp else 0,
        } if radiant_mvp else None,
        "mvp_dire": {
            "name": dire_mvp.get("personaname", "?") if dire_mvp else "?",
            "hero_id": dire_mvp.get("hero_id", 0) if dire_mvp else 0,
            "hero_name": _hero_name(dire_mvp.get("hero_id", 0)) if dire_mvp else "?",
            "team": "Dire",
            "kda": round((dire_mvp.get("kills", 0) + dire_mvp.get("assists", 0)) / max(dire_mvp.get("deaths", 1), 1), 2) if dire_mvp else 0,
            "kills": dire_mvp.get("kills", 0) if dire_mvp else 0,
            "deaths": dire_mvp.get("deaths", 0) if dire_mvp else 0,
            "assists": dire_mvp.get("assists", 0) if dire_mvp else 0,
            "gpm": dire_mvp.get("gold_per_min", 0) if dire_mvp else 0,
            "xpm": dire_mvp.get("xp_per_min", 0) if dire_mvp else 0,
            "score": round(dire_mvp.get("_mvp", 0), 1) if dire_mvp else 0,
        } if dire_mvp else None,
        "scores": scores,
        "tips": tips,
        "skill_build": skill_analysis,
        "item_build": item_analysis,
    }


# ── Агрегация по всем играм ──────────────────────────────────────────────────

def get_recent_matches_batch(account_id: int = ACCOUNT_ID, limit: int = 20) -> list[dict]:
    """Загрузить recentMatches одним запросом (быстро)."""
    return _fetch_json(f"https://api.opendota.com/api/players/{account_id}/recentMatches?limit={limit}") or []


def analyze_from_recent(raw_match: dict) -> dict:
    """Проанализировать матч прямо из recentMatches (без доп. запросов)."""
    duration = raw_match.get("duration", 1)
    dur_min = duration / 60.0

    kills = raw_match.get("kills", 0)
    deaths = raw_match.get("deaths", 0)
    assists = raw_match.get("assists", 0)
    gpm = raw_match.get("gold_per_min", 0)
    xpm = raw_match.get("xp_per_min", 0)
    lh = raw_match.get("last_hits", 0)
    denies = raw_match.get("denies", 0)
    hd = raw_match.get("hero_damage", 0)
    td = raw_match.get("tower_damage", 0)
    hh = raw_match.get("hero_healing", 0)
    level = raw_match.get("level", 0)
    net_worth = raw_match.get("net_worth", 0)
    hero_id = raw_match.get("hero_id", 0)
    slot = raw_match.get("player_slot", 0)
    radiant_win = bool(raw_match.get("radiant_win", False))

    lhpm = lh / dur_min if dur_min > 0 else 0
    dpm = hd / dur_min if dur_min > 0 else 0
    kda = (kills + assists) / max(deaths, 1)

    scores = {}
    scores["gpm"] = "low" if gpm < BENCHMARKS["gpm"]["low"] else ("mid" if gpm < BENCHMARKS["gpm"]["mid"] else "high")
    scores["xpm"] = "low" if xpm < BENCHMARKS["xpm"]["low"] else ("mid" if xpm < BENCHMARKS["xpm"]["mid"] else "high")
    scores["lhpm"] = "low" if lhpm < BENCHMARKS["lhpm"]["low"] else ("mid" if lhpm < BENCHMARKS["lhpm"]["mid"] else "high")
    scores["dpm"] = "low" if dpm < BENCHMARKS["dpm"]["low"] else ("mid" if dpm < BENCHMARKS["dpm"]["mid"] else "high")
    scores["td"] = "low" if td < BENCHMARKS["td"]["low"] else ("mid" if td < BENCHMARKS["td"]["mid"] else "high")
    scores["deaths"] = "good" if deaths <= BENCHMARKS["deaths"]["good"] else ("warn" if deaths <= BENCHMARKS["deaths"]["warn"] else "bad")
    scores["kda"] = "low" if kda < BENCHMARKS["kda"]["low"] else ("mid" if kda < BENCHMARKS["kda"]["mid"] else "high")

    tips = []
    if scores["gpm"] == "low": tips.append("📉 GPM ниже нормы — больше фарми.")
    if scores["lhpm"] == "low": tips.append("⚒️ Мало ластхитов — практикуй тайминги.")
    if scores["deaths"] in ("warn", "bad"): tips.append("💀 Много смертей — смотри миникарту.")
    if scores["td"] == "low": tips.append("🏰 Мало урона по башням — пуш после драки.")
    if scores["dpm"] == "low": tips.append("⚔️ Мало урона по героям — участвуй в боях.")
    if not tips: tips.append("✅ Показатели в норме.")

    return {
        "match_id": raw_match.get("match_id"),
        "hero_id": hero_id,
        "hero_name": _hero_name(hero_id),
        "result": "win" if (0 <= slot <= 4) == radiant_win else "loss",
        "duration": duration,
        "radiant_win": radiant_win,
        "radiant_score": raw_match.get("radiant_score"),
        "dire_score": raw_match.get("dire_score"),
        "level": level,
        "net_worth": net_worth,
        "kills": kills, "deaths": deaths, "assists": assists,
        "gpm": gpm, "xpm": xpm,
        "last_hits": lh, "denies": denies,
        "lhpm": round(lhpm, 2),
        "hero_damage": hd, "tower_damage": td, "hero_healing": hh,
        "dpm": round(dpm, 1),
        "kda": round(kda, 2),
        "kill_part": 0, "damage_part": 0, "tower_part": 0,
        "gpm_rank": 0, "team_avg": {}, "enemy_avg": {},
        "scores": scores, "tips": tips,
        "skill_build": {"build": [], "notes": []},
        "item_build": {"items": [], "notes": []},
    }


def analyze_all_matches(match_ids: list[int] = None, max_matches: int = 20) -> dict:
    """Быстрый анализ через recentMatches (один запрос)."""
    raw_matches = get_recent_matches_batch(limit=max_matches)
    matches = []
    for raw in raw_matches[:max_matches]:
        m = analyze_from_recent(raw)
        matches.append(m)

    if not matches:
        return {"matches_analyzed": 0, "error": "Нет данных"}

    avg_gpm = round(statistics.mean([m["gpm"] for m in matches]), 1)
    avg_xpm = round(statistics.mean([m["xpm"] for m in matches]), 1)
    avg_lhpm = round(statistics.mean([m["lhpm"] for m in matches]), 2)
    avg_deaths = round(statistics.mean([m["deaths"] for m in matches]), 1)
    avg_kda = round(statistics.mean([m["kda"] for m in matches]), 2)
    avg_td = round(statistics.mean([m["tower_damage"] for m in matches]), 0)
    avg_dpm = round(statistics.mean([m["dpm"] for m in matches]), 1)

    error_counter = Counter()
    for m in matches:
        for key, val in m["scores"].items():
            if val in ("low", "bad", "warn"):
                error_counter[key] += 1

    general_tips = []
    if avg_deaths > BENCHMARKS["deaths"]["warn"]:
        general_tips.append("💀 Средний смерти высокий. Смотри миникарту, не лез без видения.")
    if avg_lhpm < BENCHMARKS["lhpm"]["mid"]:
        general_tips.append("📉 Средний LH/мин низкий. Больше фарми.")
    if avg_gpm < BENCHMARKS["gpm"]["mid"]:
        general_tips.append("📉 Средний GPM ниже нормы. Фарми эффективнее.")
    if avg_td < BENCHMARKS["td"]["mid"]:
        general_tips.append("🏰 Мало урона по башням. После драки — пуш.")
    if not general_tips:
        general_tips.append("✅ Показатели в норме. Продолжай в том же духе.")

    wins = sum(1 for m in matches if m["result"] == "win")
    win_rate = round(wins / len(matches) * 100, 1)

    return {
        "matches_analyzed": len(matches),
        "win_rate": win_rate,
        "avg_gpm": avg_gpm, "avg_xpm": avg_xpm,
        "avg_lhpm": avg_lhpm, "avg_deaths": avg_deaths,
        "avg_kda": avg_kda, "avg_tower_damage": avg_td, "avg_dpm": avg_dpm,
        "top_errors": error_counter.most_common(5),
        "general_tips": general_tips,
        "matches": matches,
    }


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _hero_name(hero_id: int) -> str:
    """Получить имя героя по ID из кэша."""
    cache_path = os.path.join("data", "heroes_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if isinstance(cache, list):
            for h in cache:
                if h.get("id") == hero_id:
                    return h.get("localized_name", h.get("name", f"Hero_{hero_id}"))
        elif isinstance(cache, dict):
            return cache.get(str(hero_id), f"Hero_{hero_id}")
    return f"Hero_{hero_id}"


def get_recent_match_ids(account_id: int = ACCOUNT_ID, limit: int = 20) -> list[int]:
    """Получить ID последних матчей."""
    data = _fetch_json(f"https://api.opendota.com/api/players/{account_id}/recentMatches")
    if not data:
        return []
    return [m["match_id"] for m in data[:limit]]


def get_player_slots(account_id: int = ACCOUNT_ID, limit: int = 100) -> dict[int, int]:
    """Получить player_slot для последних матчей (match_id → slot)."""
    data = _fetch_json(f"https://api.opendota.com/api/players/{account_id}/recentMatches")
    if not data:
        return {}
    return {m["match_id"]: m.get("player_slot", 0) for m in data[:limit]}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    print("Загрузка последних матчей...")
    ids = get_recent_match_ids(limit=10)
    print(f"Найдено {len(ids)} матчей")
    result = analyze_all_matches(ids, max_matches=10)
    print(json.dumps(result, ensure_ascii=False, indent=2))
