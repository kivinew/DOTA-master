# -*- coding: utf-8 -*-
"""Тесты analysis/http.py: единый fetch без сети (подмена urlopen)."""

import urllib.error

import analysis.http as http


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _no_sleep(monkeypatch):
    monkeypatch.setattr("analysis.http.time.sleep", lambda s: None)


def test_fetch_json_ok(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=30: _Resp(b'{"a": 1}'),
    )
    assert http.fetch_json("http://x") == {"a": 1}


def test_fetch_json_retries_429_then_ok(monkeypatch):
    _no_sleep(monkeypatch)
    err = urllib.error.HTTPError("http://x", 429, "Too Many", {}, None)
    calls = {"n": 0}

    def fake(req, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            raise err
        return _Resp(b"[1, 2]")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert http.fetch_json("http://x") == [1, 2]
    assert calls["n"] == 2


def test_fetch_json_no_retry_on_404(monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=30):
        calls["n"] += 1
        raise urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert http.fetch_json("http://x") is None
    assert calls["n"] == 1


def test_fetch_json_gives_up_on_network_error(monkeypatch):
    _no_sleep(monkeypatch)

    def fake(req, timeout=30):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert http.fetch_json("http://x", retries=2) is None
