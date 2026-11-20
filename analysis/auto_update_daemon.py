#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOTA_MASTER — демон автообновления статистики.

Запускается как отдельный процесс: `uv run python analysis/auto_update_daemon.py`.
Держит поток обновления в живых пока не получит SIGTERM / Ctrl+C.
"""

import signal
import sys
import os
import time
import logging

# Ensure we can import from project root
PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
sys.path.insert(0, PROJECT_ROOT)

# UTF-8 для консоли (кириллица в логах демона) — до logging.basicConfig
from analysis.console_utf8 import enable_utf8_console  # noqa: E402

enable_utf8_console()

from analysis.auto_update import (
    start_auto_update,
    stop_auto_update,
    get_auto_update_status,
    _read_pid,
    _is_running,
)
from analysis.config import ACCOUNT_ID, UPDATE_INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [daemon] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dota_auto_update_daemon")


def _handle_sigterm(signum, frame):
    logger.info("Получен сигнал %d, остановка..." % signum)
    stop_auto_update()
    sys.exit(0)


def _handle_sigint(signum, frame):
    logger.info("Получен Ctrl+C, остановка...")
    stop_auto_update()
    sys.exit(0)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="DOTA_MASTER автоматическое обновление (демон)"
    )
    parser.add_argument(
        "--account-id", default=ACCOUNT_ID, help="account_id игрока (по умолчанию из DOTA_ACCOUNT_ID)"
    )
    parser.add_argument(
        "--interval", type=int, default=UPDATE_INTERVAL, help="Интервал в секундах (по умолчанию из DOTA_UPDATE_INTERVAL)"
    )
    parser.add_argument(
        "--max", type=int, default=30, help="Максимум матчей за раз (по умолчанию 30)"
    )
    args = parser.parse_args()

    # Обработчики сигналов
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigint)

    logger.info(
        f"Запуск демона автообновления: account_id={args.account_id}, "
        f"interval={args.interval}с, max={args.max}"
    )

    t = start_auto_update(
        account_id=args.account_id,
        interval_seconds=args.interval,
        max_matches=args.max,
        owner="daemon",
    )

    logger.info("Демон работает, ожидание сигнала завершения...")
    try:
        while _is_running(os.getpid()):
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Ctrl+C получен, останавливаем...")
        stop_auto_update()


if __name__ == "__main__":
    main()
