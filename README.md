# DOTA_MASTER — анализ статистики игр в DOTA 2

## Структура проекта

```
DOTA_MASTER/
├── main.py              # CLI: add / import / report / hero / list / errors / fetch / auto-update
├── app.py               # Flask веб-интерфейс (порт 9999)
├── requirements.txt     # Зависимости (Flask; PyYAML опционально; pytest для тестов)
├── start_web.bat        # Launcher сервера (UTF-8, порт 9999)
├── games/               # Хранилище игр: games.json + кэши fresh_matches.json / match_list.json
├── data/                # heroes_cache.json, sample.csv
├── analysis/
│   ├── config.py            # Единый конфиг через env (DOTA_ACCOUNT_ID, PORT, ...)
│   ├── http.py              # Единый HTTP-клиент (urllib + retry)
│   ├── fresh_cache.py       # TTL-кэш свежих матчей (stale-while-revalidate)
│   ├── stats_engine.py      # Хранилище, агрегация, detect_errors, merge_games
│   ├── fetcher.py           # OpenDota API: загрузка и нормализация матчей
│   ├── web_fetcher.py       # Свежие матчи (recentMatches + догоняющий запрос)
│   ├── macro_analyzer.py    # Макро-анализ vs бенчмарки ранга
│   ├── report_generator.py  # Текстовые отчёты по матчам
│   ├── hero_strategies.py   # Стратегии победы по героям (win vs loss)
│   ├── auto_update.py       # Фоновое обновление (поток + файлы состояния)
│   ├── auto_update_daemon.py# Отдельный процесс-демон обновления
│   ├── console_utf8.py      # UTF-8 вывод в консоль (кириллица) на Windows
│   └── icons.py             # URL иконок предметов/способностей
├── scripts/             # fetch.py и import_matches.py — единые загрузка/импорт;
│                       # старые fetch_*/import_* оставлены для совместимости
│                       # (писали в scripts/games/ — теневую копию базы)
├── tests/               # pytest: stats_engine, fetcher, hero_strategies, http,
├── static/css/dota.css  # Единая тема оформления (стиль Dota 2)
├── templates/
│   ├── base.html        # Общий каркас страниц: шапка, меню, подвал
│   └── *.html           # Страницы (расширяют base.html, своего CSS не содержат)
├── reports/             # Сгенерированные отчёты (Markdown / HTML)
└── README.md
```

## Как добавлять данные об играх

Проект поддерживает два входных формата:

1. **Ручной ввод** через терминал — `main.py add` (запрос: герой, роль, результат, KDA, RoTL, last hits, GPM, XPM, draft-Composition, описание ошибок).
2. **CSV-импорт** — `main.py import <file.csv>` (ожидаемые колонки: `date, hero, role, result, kills, deaths, assists, RoTL, last_hits, GPM, XPM, game_mode, draft_allies, draft_enemies, notes`).

Пример CSV:
```csv
date,hero,role,result,kills,deaths,assists,RoTL,last_hits,GPM,XPM,game_mode,draft_allies,draft_enemies,notes
2026-09-12,Invoker,carry,loss,14,12,31,23,156,340,510,cm,dragon,neere,positioning mistakes on fights
```

## Загрузка из OpenDota

```bash
# Быстрая загрузка (recentMatches, без деталей)
python scripts/fetch.py --steam-id64 76561198001364885 --max 30

# Полная загрузка (детали каждого матча: KDA/GPM/XPM/драфт)
python scripts/fetch.py --steam-id64 76561198001364885 --max 30 --source api

# Импорт свежих матчей из games/fresh_matches.json (с дедупликацией)
python scripts/import_matches.py --fresh
```

Старые `scripts/fetch_*.py` писали в `scripts/games/games.json` (теневая копия) —
не используйте их, только `scripts/fetch.py` / `scripts/import_matches.py`.

API: `GET /api/games?page=1&per_page=50` (пагинация, `per_page` ≤ 200),
ошибки API — единый формат `{"status": "error", "message": ...}`.

## Бэкенд-анализ

- `stats_engine.py` — агрегирует: общий KDA, RoTL%, GPM/XPM среднее, выигрыш-проигрыш по герою/роли/рангу, тренды по дате.
- `stats_engine.detect_errors()` — маркеры критических ошибок одной игры: KDA < 0.5 в проигрыше, известный RoTL < 10 (`rotl == 0` означает «нет данных» от OpenDota и не помечается), ≥ 8 смертей, GPM < 60% от XPM.
- `hero_strategies.py` — для каждого героя, на котором вы играли > N игр, строит карту "что работает / что нет" по факторам: кастом-комп vs вражеский драфт, дельта GPM на ~10 мин, смерти-до-10-минут, контриб в командах-с-победой против проигрышных.
- `macro_analyzer.py` + `report_generator.py` — макро-анализ свежих матчей vs бенчмарки ранга (GPM/XPM/LH, смерти, урон) и текстовые отчёты с трендами.
- `web_fetcher.py` + `fetcher.py` — загрузка матчей из OpenDota API (recentMatches + детали `/matches/{id}`, дедупликация по `match_id`).
- `http.py` — единый HTTP-клиент обоих fetcher'ов (`urllib` + retry на 429/сеть).
- `fresh_cache.py` — TTL-кэш (60 c) свежих матчей: страница `/` и `/fresh` не ждут API, протухшее отдаётся сразу с фоновым обновлением.
- `auto_update.py` — фоновое обновление `games.json` каждые N минут, состояние в `games/.auto_update_state.json`.

## Запуск

```bash
# Добавить одну игру ручным вводом
python main.py add

# Импорт CSV
python main.py import games_export.csv

# Вывод сводного отчёта
python main.py report

# Анализ конкретного героя
python main.py hero Invoker
```

## Оформление: единый стиль Dota 2

Все страницы используют один каркас и один стилевой файл:

```
templates/base.html      # <head>, шапка с меню, <main class="container">, подвал
static/css/dota.css      # вся тема: палитра, панели, таблицы, кнопки, адаптивность
templates/<page>.html    # {% extends "base.html" %} + {% block content %}
```

* Палитра в стиле Dota 2: тёмный фон `#0d0d12`, золото `#c9a84c`, зелёный/красный
  для побед и поражений; переменные `--dota-*` объявлены в `:root`.
* Гранёные углы панелей — `clip-path` со срезом (top-left + bottom-right);
  тени сделаны через `filter: drop-shadow()`, чтобы повторять силуэт среза.
* Меню одно для всех страниц; активный пункт подсвечивается по `request.path`,
  ссылка «герой» ведёт на текущего героя (`/hero/<hero>`).
* Заголовки страниц единообразны: `.page-title` + `.page-subtitle` + `.back-btn`.
* Есть адаптивность (960px / 620px), кастомный скроллбар, `:focus-visible`
  и `prefers-reduced-motion`.

Как добавить новую страницу:

```html
{% extends "base.html" %}
{% block title %}DOTA_MASTER — Новая страница{% endblock %}
{% block content %}
<h1 class="page-title">🆕 Новая страница</h1>
<p class="page-subtitle">Описание</p>
<div class="dota-section">
    <div class="dota-section-title">Заголовок блока</div>
    ...
</div>
{% endblock %}
```

Готовые классы: `.stats-row` / `.stats-grid` + `.stat-card`, `.dota-section`,
`.dota-table`, `.error-pill`, `.tip-box`, `.btn` / `.btn-primary`,
`.empty-state`, `.code-block`, `.pagination`, `.hero-grid` / `.hero-card`,
`.match-preview`, `.hero-large` / `.hero-portrait-large`.

Утилитарные классы (вместо inline-стилей): `.muted`, `.gold`, `.cyan`,
`.fs-sm` (0.8rem), `.fs-xs` (0.7rem), `.mono`, `.tc` / `.tl`, `.mt-sm` / `.mt-md`,
`.hidden`, `.note-box`, `.inline-code`, `.hero-thumb-sm`, `.stat-value-sm`,
`.stat-value-xs`, `.empty-state-sm`.

При изменении CSS увеличьте параметр версии в ссылке (`dota.css?v=2` в
`base.html`) — иначе браузер может показать старый файл из кеша.

> Важно: после правки шаблонов перезапустите сервер (`start_web.bat`) —
> Flask в не-debug режиме кеширует шаблоны в памяти.

## Кодировки: почему русский текст «ломался» и что сделано

Все файлы проекта — **UTF-8 без BOM** (шаблоны, JSON, Python). Данные не были
испорчены: некорректно отображался только вывод из-за рассогласования кодировок
между программой и консолью.

Причины, которые устранены:

1. **`chcp 1251` в `start_web.bat`.** Python печатал UTF-8 байты, а консоль
   декодировала их как cp1251 → «РџСЂРёРІРµС‚» вместо «Привет».
   Теперь в лаунчере `chcp 65001` + `PYTHONUTF8=1`.
2. **Python берёт кодировку из locale (cp1251) при перенаправлении вывода**, и
   символы вне cp1251 («—», «◄») вызывали `UnicodeEncodeError`. Теперь
   `analysis/console_utf8.py` ставит code page консоли 65001 и переводит
   `stdout`/`stderr` в UTF-8 — во всех точках входа (`app.py`, `main.py`,
   `analysis/auto_update_daemon.py`, `scripts/*.py`, `test_fetcher.py`).
3. **PowerShell 5.1 читает файлы как ANSI и пишет `>` в UTF-16LE.** Поэтому
   файлы вроде `games/fresh_matches.json` выглядят «кракозябрами», хотя внутри
   корректный UTF-8.

Правила работы (чтобы проблема не вернулась):

* запускайте сервер через `start_web.bat` (не меняйте в нём `chcp`);
* `start_web.bat` держите ASCII-only: cmd читает байты .bat в *текущей* code page;
* в PowerShell смотрите файлы с явной кодировкой и не используйте `>`:

```powershell
Get-Content .\games\fresh_matches.json -Encoding UTF8
# или
[IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)
# для записи лога: cmd /c "python app.py > server.log 2>&1"
```

## Зависимости

Требуется Python 3.10+. Сеть и веб — только Flask; движок статистики и fetcher — stdlib (`urllib`, `csv`, `json`, `datetime`, `statistics`, `collections`).

```
pip install -r requirements.txt   # Flask (+ PyYAML опционально)
pip install pytest                # только для запуска тестов
```

Настройки — через переменные окружения (дефолты в `analysis/config.py`):
`DOTA_ACCOUNT_ID` (по умолчанию 41099157), `DOTA_STEAM_ID64`, `PORT` (9999),
`DOTA_UPDATE_INTERVAL` (300 c), `DOTA_MAX_MATCHES` (100), `DOTA_MASTER_SECRET`,
`STEAM_API_KEY` (нужен только для резолва vanity URL в `main.py fetch`).

Тесты (не трогают `games/games.json` — хранилище подменяется на tmp):
```
python -m pytest tests/ -q
```
