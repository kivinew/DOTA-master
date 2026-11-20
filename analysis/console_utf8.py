# -*- coding: utf-8 -*-
"""DOTA_MASTER — принудительный UTF-8 для потоков вывода (БЕЗ chcp).

Почему НЕ используем chcp 65001 / SetConsoleOutputCP(65001):
* На Windows смена кодовой страницы консоли сбрасывает шрифт на Raster
  вместо Consolas — баг/фича conhost.exe.
* Нам не нужно менять кодовую страницу консоли — достаточно, чтобы
  Python писал UTF-8 в stdout/stderr. Это делают переменные окружения:
  PYTHONUTF8=1 и PYTHONIOENCODING=utf-8 (заданы в start_web.bat).

Что делает этот модуль:
* переводит sys.stdout / sys.stderr в UTF-8 (errors="replace"),
  что работает и при перенаправлении вывода в файл или канал.

Использование — в точке входа, до первого print/log::

    from analysis.console_utf8 import enable_utf8_console
    enable_utf8_console()
"""

import sys

__all__ = ["enable_utf8_console"]

UTF8_CODE_PAGE = 65001  # kept for reference, NOT used


def _reconfigure_streams(encoding: str = "utf-8") -> None:
    """Перевести stdout/stderr в нужную кодировку, если поток это позволяет."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding=encoding, errors="replace")
        except (OSError, ValueError, AttributeError):
            # Поток уже обёрнут или закрыт — оставляем как есть.
            continue


def enable_utf8_console(encoding: str = "utf-8") -> None:
    """Сделать вывод корректным для кириллицы (stdout/stderr в UTF-8).

    НЕ меняет кодовую страницу консоли (chcp), чтобы не сбрасывать шрифт Consolas.
    Ожидается, что PYTHONUTF8=1 и PYTHONIOENCODING=utf-8 заданы в окружении.
    """
    _reconfigure_streams(encoding)