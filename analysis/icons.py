# -*- coding: utf-8 -*-
"""DOTA_MASTER — утилиты для иконок предметов и скиллов."""

import os
import json as _json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _item_id(value) -> int:
    """Normalize OpenDota IDs, which may arrive as either ints or strings."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ── Загрузка кэша айтемов ─────────────────────────────────────────────────────

_ITEM_CACHE: dict[int, str] = {}


def _load_item_cache() -> dict[int, str]:
    """Загрузить маппинг id → slug из data/items_cache.json (если есть)."""
    cache_path = os.path.join(PROJECT_ROOT, "data", "items_cache.json")
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = _json.load(f)
        # Поддержка обоих форматов: {id: slug} и {"id": "slug"}
        result = {}
        for k, v in raw.items():
            try:
                result[int(k)] = str(v).strip()
            except (ValueError, TypeError):
                pass
        return result
    except Exception:
        return {}


_ITEM_CACHE = _load_item_cache()


# ── Загрузка кэша скиллов героев ────────────────────────────────────────────────

def _load_ability_cache() -> dict:
    """Загрузить маппинг ability_id -> slug из data/ability_id_to_slug.json."""
    cache_path = os.path.join(PROJECT_ROOT, "data", "ability_id_to_slug.json")
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = _json.load(f)
        # JSON keys are strings, convert to int
        result = {}
        for k, v in raw.items():
            try:
                result[int(k)] = v
            except (ValueError, TypeError):
                pass
        return result
    except Exception:
        return {}


ABILITY_SLUG_CACHE = _load_ability_cache()


# ── Функции получения URL ──────────────────────────────────────────────────────

# Нейтральные предметы (найденные в играх)
NEUTRAL_ITEMS: dict[int, str] = {
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


def item_name(item_id: int) -> str:
    """Человекочитаемое название предмета: из кэша, нейтральный либо Item_{id}."""
    item_id = _item_id(item_id)
    name = _ITEM_CACHE.get(item_id)
    if name:
        return str(name).replace("_", " ").title()
    if item_id in NEUTRAL_ITEMS:
        return NEUTRAL_ITEMS[item_id]
    return f"Item_{item_id}"


def neutral_item_name(neutral_id: int) -> str:
    """Человекочитаемое название нейтрального предмета либо Neutral_{id}."""
    neutral_id = _item_id(neutral_id)
    name = NEUTRAL_ITEMS.get(neutral_id) or _ITEM_CACHE.get(neutral_id)
    if name:
        name = str(name)
        return name.replace("_", " ").title() if name.islower() else name
    return f"Neutral_{neutral_id}"


def hero_item_name(item) -> str:
    """Человекочитаемое название айтема игрока.

    Форматы: int (item_id), ("neutral", id) / ["neutral", id], {"id": .., "name": ..}
    """
    if isinstance(item, dict):
        name = item.get("name")
        if name:
            return str(name)
        return item_name(item.get("id") or 0)
    if isinstance(item, (list, tuple)):
        if item and str(item[0]).lower() == "neutral":
            return neutral_item_name(item[1] or 0)
        return item_name(item[1] or 0)
    return item_name(item or 0)


def item_img_url(item_id: int) -> str:
    """Return a local item icon when available, otherwise a Steam CDN URL.

    IDs are normalized because match payloads may serialize them as strings.
    Paths are resolved from the repository root, independent of the caller's cwd.
    Templates provide a local placeholder if a CDN asset is missing or retired.
    """
    item_id = _item_id(item_id)
    if item_id <= 0:
        return ""

    slug = _ITEM_CACHE.get(item_id)
    if slug:
        local_slug_path = os.path.join(PROJECT_ROOT, "static", "items", f"{slug}.png")
        if os.path.isfile(local_slug_path):
            return f"/static/items/{slug}.png"

    local_id_path = os.path.join(PROJECT_ROOT, "static", "items", f"{item_id}.png")
    if os.path.isfile(local_id_path):
        return f"/static/items/{item_id}.png"

    if slug:
        return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/items/{slug}_lg.png"
    return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/items/{item_id}_lg.png"


def ability_img_url(ability_id: int) -> str:
    """Получить URL иконки скилла для любого героя."""
    if not ability_id:
        return ""

    # Специальные способности — используем иконки предметов
    if ability_id == 6448:  # Aghanim's Scepter
        return "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/items/ultimate_scepter_lg.png"
    if ability_id == 5903:  # Aghanim's Shard
        return "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/items/aghanims_shard_lg.png"
    if ability_id == 6541:  # Moon Shard
        return "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/items/moon_shard_lg.png"

    slug = ABILITY_SLUG_CACHE.get(ability_id)
    if slug:
        # Таланты (slug начинается на special_bonus_) — нет иконок на CDN
        if slug.startswith("special_bonus_"):
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        # Проверяем локальный файл
        local_path = os.path.join("static", "abilities", f"{slug}.png")
        if os.path.exists(local_path):
            return f"/static/abilities/{slug}.png"
        # Fallback: Steam CDN (dota_react format)
        return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/abilities/{slug}.png"

    # Нет в кэше — пробуем локальный файл по ID
    local_id_path = os.path.join("static", "abilities", f"{ability_id}.png")
    if os.path.exists(local_id_path):
        return f"/static/abilities/{ability_id}.png"

    # Fallback: Steam CDN по ID (old format, may 404)
    return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/abilities/{ability_id}_md.png"
