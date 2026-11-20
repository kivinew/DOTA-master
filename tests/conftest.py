# -*- coding: utf-8 -*-
"""Pytest-фикстуры DOTA_MASTER: изоляция хранилища игр во временной папке."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import stats_engine  # noqa: E402


@pytest.fixture
def isolated_games(tmp_path, monkeypatch):
    """Подменить GAMES_DIR на tmp, чтобы тесты не трогали games/games.json."""
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    monkeypatch.setattr(stats_engine, "GAMES_DIR", str(games_dir))
    return str(games_dir)
