# Тестирование fetcher.py
import sys
import os

# UTF-8 для консоли (кириллица в выводе) — до всех остальных импортов и print
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.fetcher import (
    _steam_id64_to_account_id,
    _account_id_to_steam_id64,
    normalize_open_dota_match,
    get_heroes_list,
    load_heroes_cache,
)

print("=" * 50)
print("Тест 1: Конвертация SteamID64 <-> account_id")
print("=" * 50)

# Известный пример: SteamID64 пользователя = 76561198000000000 (упрощённо)
# account_id ≈ 76561198000000000 - 76561197960265728 = ~39734272
test_sid64 = 76561198000000000
aid = _steam_id64_to_account_id(test_sid64)
back = _account_id_to_steam_id64(aid)
print(f"  SteamID64: {test_sid64}")
print(f"  account_id: {aid}")
print(f"  обратно: {back}")
assert back == test_sid64, "Обратная конвертация не сходится!"
print("  OK: конвертация обратима")

print()
print("=" * 50)
print("Тест 2: normalize_open_dota_match")
print("=" * 50)

sample_match = {
    "match_id": 1234567890,
    "match_time": 1694500000,  # 2023-09-11
    "hero_id": 10,
    "hero_name": "lion",
    "kills": 12,
    "deaths": 4,
    "assists": 22,
    "gold_per_min": 340,
    "xp_per_min": 510,
    "last_hits": 160,
    "is_radiant": True,
    "radiant_win": True,
    "game_mode": 2,
    "lobby_type": 7,
    "duration": 2300,
    "pick_bans": [
        {"is_pick": True, "hero_id": 10, "hero_name": "Lion", "team": 1},
        {"is_pick": True, "hero_id": 1, "hero_name": "Anti-Mage", "team": 2},
        {"is_pick": False, "hero_id": 7, "hero_name": "Pudge", "team": 1},
        {"is_pick": True, "hero_id": 2, "hero_name": "Axe", "team": 1},
    ],
}

norm = normalize_open_dota_match(sample_match)
print("Нормализованная запись:")
for k, v in norm.items():
    print(f"  {k}: {v}")

assert norm["hero"] == "Lion"
assert norm["result"] == "win"
assert norm["kills"] == 12
assert norm["deaths"] == 4
assert norm["draft_allies"] == "Lion, Axe"
assert norm["draft_enemies"] == "Anti-Mage"
print("OK: все поля распаршены верно")

print()
print("=" * 50)
print("Тест 3: load_heroes_cache")
print("=" * 50)
heroes = load_heroes_cache()
if heroes:
    print(f"  Загружено {len(heroes)} героев из кэша")
    print(f"  Пример: 10 -> {heroes.get('10', 'Нет в кэше')}")
else:
    print("  Кэш пока пуст (не было вызовов get_heroes_list)")

print()
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
