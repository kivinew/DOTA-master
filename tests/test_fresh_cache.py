# -*- coding: utf-8 -*-
"""Тесты analysis/fresh_cache.py: TTL-кэш без сети (подмена get_fresh_view)."""

import analysis.fresh_cache as fc


def _sample():
    return [{"hero": "Pugna", "match_id": "1", "result": "win",
             "K": 2, "D": 2, "A": 15}]


def test_fresh_then_served_from_cache(monkeypatch):
    fc.invalidate()
    calls = {"n": 0}

    def fake(account_id, limit=20):
        calls["n"] += 1
        return _sample()

    monkeypatch.setattr(fc, "get_fresh_view", fake)
    try:
        data, fresh = fc.get_cached_fresh_view("1", limit=5)
        assert fresh is True and data == _sample()
        data2, fresh2 = fc.get_cached_fresh_view("1", limit=5)
        assert fresh2 is True and data2 == _sample()
        assert calls["n"] == 1  # второй раз — из кэша, без запроса
    finally:
        fc.invalidate()


def test_empty_when_api_down(monkeypatch):
    fc.invalidate()
    monkeypatch.setattr(fc, "get_fresh_view", lambda a, limit=20: [])
    try:
        assert fc.get_cached_fresh_view("1") == ([], False)
    finally:
        fc.invalidate()


def test_stale_served_immediately(monkeypatch):
    fc.invalidate()
    monkeypatch.setattr(fc, "get_fresh_view", lambda a, limit=20: _sample())
    try:
        fc.get_cached_fresh_view("1", ttl=60)
        # ttl=0 → кэш протух: отдать старое сразу, обновление летит в фоне
        data, fresh = fc.get_cached_fresh_view("1", ttl=0)
        assert data == _sample() and fresh is False
    finally:
        fc.invalidate()
