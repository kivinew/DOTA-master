# -*- coding: utf-8 -*-
"""DOTA_MASTER — единый HTTP-клиент для OpenDota/Steam API.

Заменяет три копии `_fetch_json`/`_fetch_url` в `fetcher.py`, `web_fetcher.py`
и `macro_analyzer.py`: один `urllib`-код (без внешних зависимостей),
retry на 429/сетевых ошибках, `None` при неуспехе.
"""

import json
import time
import urllib.request
import urllib.error
from typing import Optional

USER_AGENT = "DOTA_MASTER/1.0 (OpenDota integration)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_json(url: str, timeout: int = 30, retries: int = 3,
               user_agent: str = USER_AGENT) -> Optional[dict | list]:
    """GET-запрос, распарсить JSON. При ошибке — None (после retry).

    429 (rate limit) и сетевые ошибки повторяются с экспоненциальной паузой,
    прочие HTTP-ошибки возвращают None сразу.
    """
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  Rate limited (429), жду {wait}с...")
                time.sleep(wait)
                continue
            print(f"  HTTP {e.code}: {e.reason} ({url})")
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            print(f"  Сеть (попытка {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return None
    print(f"  Не удалось после {retries} попыток: {last_err} ({url})")
    return None
