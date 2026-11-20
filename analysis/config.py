# -*- coding: utf-8 -*-
"""DOTA_MASTER — централизованная конфигурация через переменные окружения.

Все дефолты (account_id, порт, интервалы, secret) живут здесь, а не разбросаны
по `app.py` / `main.py` / `macro_analyzer.py` / `auto_update_daemon.py`.
"""

import os
import secrets


def _int_env(name: str, default: int) -> int:
    """Прочитать int из env, при мусоре — дефолт."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# OpenDota account_id игрока (SteamID32). SteamID64 — через DOTA_STEAM_ID64.
ACCOUNT_ID: int = int(os.environ.get("DOTA_ACCOUNT_ID", "41099157"))
STEAM_ID64: str = os.environ.get("DOTA_STEAM_ID64", "76561198001364885")

# Веб-сервер и фоновое обновление
PORT: int = _int_env("PORT", 9999)
UPDATE_INTERVAL: int = _int_env("DOTA_UPDATE_INTERVAL", 300)  # секунды
MAX_MATCHES: int = _int_env("DOTA_MAX_MATCHES", 100)

# Flask secret: только из env; без него — одноразовый (сессии сгорят при рестарте).
# Приложение не использует сессии, поэтому эфемерный ключ безопасен для dev.
SECRET_KEY: str = os.environ.get("DOTA_MASTER_SECRET") or secrets.token_hex(32)
