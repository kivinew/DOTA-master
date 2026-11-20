# -*- coding: utf-8 -*-
"""DOTA_MASTER — TTL-кэш свежих матчей OpenDota (stale-while-revalidate).

Проблема: страница `/` и `/fresh` на каждую загрузку синхронно ходили в
OpenDota API — при лагах API страница висела десятки секунд.
Решение: свежий кэш (TTL) отдаём сразу; протухший — отдаём сразу и обновляем
в фоновом daemon-потоке; при пустом кэше грузим синхронно один раз.
Только память процесса, на диск ничего не пишет.
"""

import threading
import time

from .web_fetcher import get_fresh_view

TTL_SECONDS = 60.0

_lock = threading.Lock()
_cached_at = 0.0
_cached_data: list = []
_refreshing = False


def _load(account_id: str, limit: int) -> list:
    try:
        return get_fresh_view(account_id, limit=limit) or []
    except Exception:
        return []


def _bg_refresh(account_id: str, limit: int) -> None:
    global _cached_at, _cached_data, _refreshing
    try:
        fresh = _load(account_id, limit)
        if fresh:  # ошибку API не кэшируем — оставляем старые данные
            with _lock:
                _cached_data = fresh
                _cached_at = time.monotonic()
    finally:
        with _lock:
            _refreshing = False


def get_cached_fresh_view(account_id: str, limit: int = 20,
                          ttl: float = TTL_SECONDS) -> tuple[list, bool]:
    """Вернуть (матчи, is_fresh).

    is_fresh=True — данные свежее TTL (или загружены только что синхронно).
    is_fresh=False — отдан протухший кэш, обновление уже летит в фоне.
    ([], False) — данных нет ни в кэше, ни в API.
    """
    global _refreshing, _cached_at, _cached_data
    now = time.monotonic()
    with _lock:
        age = now - _cached_at
        data = list(_cached_data)
        refreshing = _refreshing
    if data and age < ttl:
        return data, True
    if data and not refreshing:
        with _lock:
            _refreshing = True
        threading.Thread(target=_bg_refresh, args=(account_id, limit),
                         daemon=True).start()
        return data, False
    fresh = _load(account_id, limit)
    if fresh:
        with _lock:
            _cached_data = fresh
            _cached_at = time.monotonic()
        return list(fresh), True
    return [], False


def invalidate() -> None:
    """Сбросить кэш (нужно тестам и ручному обновлению)."""
    global _cached_at, _cached_data
    with _lock:
        _cached_at = 0.0
        _cached_data = []
