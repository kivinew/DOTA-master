# -*- coding: utf-8 -*-
"""DOTA_MASTER — автообновление статистики игр каждые N минут.

Фоновый поток периодически загружает свежие матчи с OpenDota
и добавляет новые в games/games.json (исключая дубликаты по match_id).

Состояние хранится в файлах проекта, чтобы работало между отдельными
запусками `python main.py auto-update start|stop|status`.
"""

import json
import os
import sys
import threading
import time
import logging
import tempfile
from datetime import datetime

from .web_fetcher import fetch_and_save
from .stats_engine import _load_games

logger = logging.getLogger("dota_auto_update")

# Настроить вывод в консоль (если ещё не настроен)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [auto-update] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Не передавать сообщения выше (в root logger), чтобы не дублироваться
    logger.propagate = False

# ── Пути к файлам состояния ──────────────────────────────────────────────────

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_STATE_DIR = os.path.join(_PROJECT_ROOT, "games")
_STATE_FILE = os.path.join(_STATE_DIR, ".auto_update_state.json")
_PID_FILE = os.path.join(_STATE_DIR, ".auto_update.pid")

# Открыть блокировку в зависимости от платформы
if sys.platform == "win32":
    import msvcrt

    _LOCK_EX = msvcrt.LK_LOCK
    _LOCK_SH = msvcrt.LK_LOCK  # на Windows нет разделяемой блокировки, используем эксклюзивную
    _LOCK_UN = msvcrt.LK_UNLCK
else:
    import fcntl

    _LOCK_EX = fcntl.LOCK_EX
    _LOCK_SH = fcntl.LOCK_SH
    _LOCK_UN = fcntl.LOCK_UN


def _ensure_state_dir():
    os.makedirs(_STATE_DIR, exist_ok=True)


def _lock_file(f, exclusive: bool = True):
    """Закрыть файл (взаимоблокировка через msvcrt/fcntl)."""
    try:
        if exclusive:
            fcntl.flock(f.fileno(), _LOCK_EX) if sys.platform != "win32" else msvcrt.locking(f.fileno(), _LOCK_EX, 1)
        else:
            fcntl.flock(f.fileno(), _LOCK_SH) if sys.platform != "win32" else msvcrt.locking(f.fileno(), _LOCK_SH, 1)
    except (ValueError, OSError):
        pass  # файл может быть закрыт


def _unlock_file(f):
    try:
        if sys.platform == "win32":
            msvcrt.locking(f.fileno(), _LOCK_UN, 0)
        else:
            fcntl.flock(f.fileno(), _LOCK_UN)
    except (ValueError, OSError):
        pass


def _read_state() -> dict:
    """Прочитать состояние из файла (потокобезопасно)."""
    _ensure_state_dir()
    if not os.path.exists(_STATE_FILE):
        return {}
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            _lock_file(f, exclusive=False)
            data = json.load(f)
            _unlock_file(f)
            return data
    except (json.JSONDecodeError, IOError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    """Записать состояние в файл (потокобезопасно)."""
    _ensure_state_dir()
    tmp_path = _STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        _lock_file(f, exclusive=True)
        json.dump(state, f, ensure_ascii=False, indent=2)
        _unlock_file(f)
    os.replace(tmp_path, _STATE_FILE)


def _clear_state() -> None:
    """Очистить файлы состояния."""
    for path in (_STATE_FILE, _PID_FILE):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _has_new_games_since(since_hours: int = 24) -> bool:
    """Проверить, были ли новые игры за последние N часов."""
    games = _load_games()
    if not games:
        return False
    cutoff = time.time() - (since_hours * 3600)
    for g in games:
        date_str = g.get("date_full", g.get("date", ""))
        for fmt in ("%Y-%m-%d %H:%M:%S +07", "%Y-%m-%d %H:%M:%S UTC"):
            if date_str and date_str.endswith(fmt[-4:]):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    if dt.timestamp() > cutoff:
                        return True
                except ValueError:
                    pass
    return False


# ── Управление процессом (PID-файл) ──────────────────────────────────────────

def _write_pid(pid: int) -> None:
    _ensure_state_dir()
    with open(_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))


def _read_pid() -> int | None:
    try:
        with open(_PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid: int) -> bool:
    """Проверить, жив ли процесс с данным PID (Windows-compatible)."""
    if sys.platform == "win32":
        try:
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=5
            )
            return str(pid) in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


# ── Поток обновления ─────────────────────────────────────────────────────────

class AutoUpdateThread(threading.Thread):
    """
    Фоновый поток, который каждые `interval_seconds` секунд
    проверяет и обновляет статистику игр.
    """

    def __init__(
        self,
        account_id: str,
        interval_seconds: int = 300,
        max_matches: int = 30,
        new_game_hours: int = 24,
        daemon: bool = True,
    ):
        super().__init__(daemon=daemon)
        self.account_id = account_id
        self.interval_seconds = interval_seconds
        self.max_matches = max_matches
        self.new_game_hours = new_game_hours
        self._stop_event = threading.Event()
        self.last_update: datetime | None = None
        self.games_added: int = 0
        self._run_count: int = 0

    def run(self):
        logger.info(
            f"Запуск автообновления (account_id={self.account_id}, "
            f"интервал={self.interval_seconds}с, max={self.max_matches})"
        )
        # Записываем PID
        _write_pid(os.getpid())
        # Сохраняем начальное состояние
        self._save_state()

        while not self._stop_event.is_set():
            try:
                self._do_update()
            except Exception as e:
                logger.error(f"Ошибка обновления: {e}")
            self._stop_event.wait(self.interval_seconds)

        # Очистка при остановке
        _clear_state()
        logger.info("Автообновление остановлено.")

    def _do_update(self):
        """Выполнить одно обновление."""
        self._run_count += 1
        state = _read_state()
        # Резолвим account_id из состояния (на случай если изменили)
        self.account_id = state.get("account_id", self.account_id)

        count = fetch_and_save(self.account_id, max_matches=self.max_matches)
        self.last_update = datetime.now()
        if count:
            self.games_added += count
            logger.info(
                f"Добавлено {count} новых матчей "
                f"(всего за сессию: {self.games_added}, "
                f"запусков: {self._run_count})"
            )
        else:
            logger.info("Новых матчей не найдено")

        self._save_state()

    def _save_state(self):
        """Сохранить текущее состояние в файл."""
        prev = _read_state()
        _write_state({
            "owner": prev.get("owner", "server"),
            "account_id": self.account_id,
            "interval_seconds": self.interval_seconds,
            "max_matches": self.max_matches,
            "new_game_hours": self.new_game_hours,
            "last_update": (
                self.last_update.isoformat()
                if self.last_update
                else None
            ),
            "games_added": self.games_added,
            "run_count": self._run_count,
            "alive": True,
        })

    def stop(self):
        """Остановить поток."""
        logger.info("Остановка автообновления...")
        self._stop_event.set()


# ── Публичные функции управления ─────────────────────────────────────────────

# Живой поток в ЭТОМ процессе. PID-файл хранит pid сервера (поток живёт внутри
# него), поэтому признаком «уже запущено» может быть только живой объект
# потока, а не stale PID-файл от убитого ранее сервера.
_THREAD: AutoUpdateThread | None = None


def start_auto_update(
    account_id: str,
    interval_seconds: int = 300,
    max_matches: int = 30,
    new_game_hours: int = 24,
    owner: str = "server",
) -> AutoUpdateThread | None:
    """
    Запустить автообновление статистики игр.

    Если уже запущен — выводит предупреждение и возвращает None.

    Args:
        account_id: account_id игрока на Steam (OpenDota).
        interval_seconds: интервал обновления в секундах (по умолчанию 300 = 5 мин).
        max_matches: максимальное количество матчей за одну загрузку.
        new_game_hours: за какой период проверять наличие новых игр.
        owner: кто владеет потоком — "server" (поток внутри веб-сервера)
            или "daemon" (отдельный процесс auto_update_daemon.py).

    Returns:
        AutoUpdateThread — запущенный поток, или None если уже запущен.
    """
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        logger.warning("Автообновление уже запущено в этом процессе, пропуск")
        return None

    # Stale файлы от прошлого запуска (сервер убили без очистки) — сбросить,
    # иначе новый поток унаследует чужой run_count/games_added.
    _clear_state()
    # Привести типы: из HTTP-ручки могут прийти строки
    try:
        interval_seconds = int(interval_seconds)
    except (TypeError, ValueError):
        interval_seconds = 300
    try:
        max_matches = int(max_matches)
    except (TypeError, ValueError):
        max_matches = 100

    t = AutoUpdateThread(
        account_id=str(account_id),
        interval_seconds=interval_seconds,
        max_matches=max_matches,
        new_game_hours=new_game_hours,
    )
    t.start()
    _THREAD = t
    # Подождать, пока поток запишет PID и initial state
    deadline = time.time() + 5
    while time.time() < deadline:
        pid2 = _read_pid()
        if pid2 is not None and _is_running(pid2):
            break
        time.sleep(0.1)
    # Пометить владельца, чтобы stop/status из другого процесса понимали,
    # можно ли слать SIGTERM (демону — да, серверу — нет).
    try:
        st = _read_state()
        st["owner"] = owner
        _write_state(st)
    except OSError:
        pass
    return t


def stop_auto_update() -> bool:
    """Остановить автообновление. Возвращает True если было остановлено."""
    global _THREAD
    t = _THREAD
    _THREAD = None
    if t is not None and t.is_alive():
        t.stop()
        t.join(timeout=10)
        _clear_state()
        return True
    # Свой поток не найден — может, работает чужой демон. Ему можно слать
    # SIGTERM (он его обрабатывает и выходит сам). Но если в файле pid
    # сервера (owner=server) — kill запрещён, там нет обработчика.
    try:
        state = _read_state()
        pid = _read_pid()
    except OSError:
        state, pid = {}, None
    if (
        pid is not None
        and pid != os.getpid()
        and state.get("owner") == "daemon"
        and _is_running(pid)
    ):
        try:
            os.kill(pid, 15)  # SIGTERM — демон завершится сам
            deadline = time.time() + 10
            while time.time() < deadline and _is_running(pid):
                time.sleep(0.2)
            _clear_state()
            return True
        except OSError as e:
            logger.error(f"Не могу остановить демон {pid}: {e}")
            return False
    _clear_state()
    logger.warning("Поток автообновления в этом процессе не найден")
    return False


def get_auto_update_status() -> dict:
    """Вернуть текущий статус автообновления (из файла)."""
    t = _THREAD
    if t is not None and t.is_alive():
        state = _read_state()
        return {
            "running": True,
            "pid": os.getpid(),
            "owner": "server",
            "account_id": state.get("account_id", t.account_id),
            "interval_seconds": state.get("interval_seconds", t.interval_seconds),
            "max_matches": state.get("max_matches", t.max_matches),
            "new_game_hours": state.get("new_game_hours", t.new_game_hours),
            "last_update": state.get("last_update"),
            "games_added": state.get("games_added", 0),
            "run_count": state.get("run_count", 0),
        }
    # Свой поток не жив — может, работает внешний демон
    try:
        state = _read_state()
        pid = _read_pid()
    except OSError:
        state, pid = {}, None
    if pid is not None and _is_running(pid) and state.get("alive"):
        return {
            "running": True,
            "external": True,
            "pid": pid,
            "owner": state.get("owner", "daemon"),
            "account_id": state.get("account_id", "?"),
            "interval_seconds": state.get("interval_seconds", 300),
            "max_matches": state.get("max_matches", 100),
            "new_game_hours": state.get("new_game_hours", 24),
            "last_update": state.get("last_update"),
            "games_added": state.get("games_added", 0),
            "run_count": state.get("run_count", 0),
        }
    return {"running": False}
