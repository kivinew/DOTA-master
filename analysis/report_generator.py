# -*- coding: utf-8 -*-
"""DOTA_MASTER — генератор развёрнутых отчётов по матчам.

Создаёт детальный текстовый анализ с указанием критических ошибок,
рекомендациями по макро-игре и вкладу в команду.
"""

import json
import os
import statistics
from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import Optional

from .macro_analyzer import analyze_match, get_recent_match_ids, BENCHMARKS, _hero_name, get_recent_matches_batch, analyze_from_recent

LOCAL_TZ = timezone(timedelta(hours=7))


def generate_match_summary(match: dict) -> str:
    """Развёрнутое текстовое резюме одного матча."""
    lines = []
    lines.append(f"## Матч {match['match_id']} — {match['hero_name']}")
    lines.append(f"**Результат:** {'Победа' if match['result'] == 'win' else 'Поражение'}  |  ")
    lines.append(f"**Длительность:** {match['duration'] // 60}:{match['duration'] % 60:02d}  |  ")
    lines.append(f"**Уровень:** {match['level']}  |  **Net Worth:** {match['net_worth']}")
    lines.append("")
    lines.append(f"### KDA")
    lines.append(f"**{match['kills']} / {match['deaths']} / {match['assists']}** (KDA: {match['kda']})")
    if match['scores']['deaths'] == 'bad':
        lines.append("⚠️ **КРИТИЧЕСКАЯ ОШИБКА:** Слишком много смертей. Это разрушает игру команды.")
    elif match['scores']['deaths'] == 'warn':
        lines.append("⚠️ Смертей больше нормы. Смотри миникарту после каждого каста.")
    lines.append("")

    lines.append(f"### Экономика")
    lines.append(f"**GPM:** {match['gpm']} (цель: 600+)  |  **XPM:** {match['xpm']} (цель: 700+)")
    lines.append(f"**Lasthits:** {match['last_hits']} ({match['lhpm']}/мин)  |  **Denies:** {match['denies']}")
    if match['scores']['lhpm'] == 'low':
        lines.append("⚠️ **КРИТИЧЕСКАЯ ОШИБКА:** Мало ластхитов. Ты теряешь золото и опыт.")
    lines.append("")

    lines.append(f"### Боевой вклад")
    lines.append(f"**Урон по героям:** {match['hero_damage']} ({match['dpm']}/мин)")
    lines.append(f"**Урон по башням:** {match['tower_damage']}")
    lines.append(f"**Хил по героям:** {match['hero_healing']}")
    if match['scores']['dpm'] == 'low':
        lines.append("⚠️ Мало урона по героям. Участвуй в драках.")
    lines.append("")

    lines.append(f"### Вклад в команду")
    lines.append(f"**Убийства:** {match['kill_part']}%  |  **Урон:** {match['damage_part']}%  |  **Башни:** {match['tower_part']}%")
    lines.append(f"**Ранг по GPM в матче:** {match['gpm_rank']}/10")
    if match['kill_part'] < 15:
        lines.append("⚠️ Низкий вклад в убийства. Ротируй и участвуй в драках.")
    lines.append("")

    lines.append(f"### Сравнение с командой")
    ta = match.get('team_avg', {})
    lines.append(f"| Показатель | Ты | Команда avg | Разница |")
    lines.append(f"|---|---|---|---|")
    diff_gpm = match['gpm'] - (ta.get('gpm', 0) or 0)
    diff_xpm = match['xpm'] - (ta.get('xpm', 0) or 0)
    diff_deaths = match['deaths'] - (ta.get('deaths', 0) or 0)
    lines.append(f"| GPM | {match['gpm']} | {ta.get('gpm', '?')} | {diff_gpm:+d} |")
    lines.append(f"| XPM | {match['xpm']} | {ta.get('xpm', '?')} | {diff_xpm:+d} |")
    lines.append(f"| Смерти | {match['deaths']} | {ta.get('deaths', '?')} | {diff_deaths:+.1f} |")
    lines.append("")

    if match.get('tips'):
        lines.append(f"### Рекомендации")
        for tip in match['tips']:
            lines.append(f"- {tip}")
        lines.append("")

    return "\n".join(lines)


def generate_full_report(match_ids: list[int] = None, max_matches: int = 15) -> dict:
    """Полный отчёт через быстрый recentMatches (один запрос)."""
    raw_matches = get_recent_matches_batch(limit=max_matches)
    matches = []
    for raw in raw_matches[:max_matches]:
        m = analyze_from_recent(raw)
        matches.append(m)

    if not matches:
        return {"error": "Нет данных", "report": "Не удалось загрузить матчи."}

    # Агрегация
    wins = sum(1 for m in matches if m['result'] == 'win')
    win_rate = round(wins / len(matches) * 100, 1)

    avg_gpm = round(statistics.mean([m['gpm'] for m in matches]), 1)
    avg_xpm = round(statistics.mean([m['xpm'] for m in matches]), 1)
    avg_deaths = round(statistics.mean([m['deaths'] for m in matches]), 1)
    avg_kda = round(statistics.mean([m['kda'] for m in matches]), 2)
    avg_lhpm = round(statistics.mean([m['lhpm'] for m in matches]), 2)
    avg_dpm = round(statistics.mean([m['dpm'] for m in matches]), 1)
    avg_td = round(statistics.mean([m['tower_damage'] for m in matches]), 0)
    avg_kill_part = round(statistics.mean([m['kill_part'] for m in matches]), 1)

    # Критические ошибки
    critical_errors = []
    if avg_deaths > BENCHMARKS['deaths']['warn']:
        critical_errors.append({
            "issue": "Высокая смертность",
            "value": f"{avg_deaths} смертей за игру",
            "target": f"≤{BENCHMARKS['deaths']['good']}",
            "fix": "Смотри миникарту после каждого каста. Не лезь в бой без видения — держи дистанцию."
        })
    if avg_lhpm < BENCHMARKS['lhpm']['mid']:
        critical_errors.append({
            "issue": "Мало ластхитов",
            "value": f"{avg_lhpm}/мин",
            "target": f"≥{BENCHMARKS['lhpm']['mid']}/мин",
            "fix": "Практикуй тайминги в тренировке. Используй Decrepify для быстрого зачищения волн."
        })
    if avg_kill_part < 20:
        critical_errors.append({
            "issue": "Низкий вклад в убийства",
            "value": f"{avg_kill_part}%",
            "target": "≥20%",
            "fix": "Ротируй на другие линии после того как забрал башню. Decrepify на вражеского керри = огромный вклад."
        })

    # Проблемы по матчам
    error_counter = Counter()
    for m in matches:
        for key, val in m['scores'].items():
            if val in ('low', 'bad', 'warn'):
                error_counter[key] += 1

    # Тренд (первые 5 vs последние 5)
    first_half = matches[:max(1, len(matches) // 2)]
    second_half = matches[max(1, len(matches) // 2):]
    if len(first_half) > 0 and len(second_half) > 0:
        gpm_trend = round(statistics.mean([m['gpm'] for m in second_half]) - statistics.mean([m['gpm'] for m in first_half]), 1)
        deaths_trend = round(statistics.mean([m['deaths'] for m in second_half]) - statistics.mean([m['deaths'] for m in first_half]), 1)
    else:
        gpm_trend = 0
        deaths_trend = 0

    # Лучший и худший матч
    best_kda = max(matches, key=lambda m: m['kda'])
    worst_kda = min(matches, key=lambda m: m['kda'])

    # Генерация текстового отчёта
    report_lines = []
    report_lines.append(f"# 📊 Полный отчёт по DOTA 2")
    report_lines.append(f"**Профиль:** ARISTOCRAT (account 41099157)")
    report_lines.append(f"**Период:** последние {len(matches)} матчей")
    report_lines.append(f"**Дата отчёта:** {datetime.now(LOCAL_TZ).strftime('%d.%m.%Y %H:%M')}")
    report_lines.append("")
    report_lines.append(f"## Общие показатели")
    report_lines.append(f"- **Винрейт:** {win_rate}%")
    report_lines.append(f"- **Средний KDA:** {avg_kda} (цель: 3.5+)")
    report_lines.append(f"- **Средний GPM:** {avg_gpm} (цель: 600+)")
    report_lines.append(f"- **Средний XPM:** {avg_xpm} (цель: 700+)")
    report_lines.append(f"- **Lasthits/мин:** {avg_lhpm} (цель: 6.0)")
    report_lines.append(f"- **Смертей за игру:** {avg_deaths} (цель: ≤4)")
    report_lines.append(f"- **Урон по героям (DPM):** {avg_dpm}")
    report_lines.append(f"- **Урон по башням:** {avg_td:.0f}")
    report_lines.append(f"- **Вклад в убийства:** {avg_kill_part}%")
    report_lines.append("")

    # Тренд
    report_lines.append(f"## Тренд")
    if gpm_trend > 0:
        report_lines.append(f"- 📈 GPM растёт (+{gpm_trend}) — фармишь эффективнее.")
    elif gpm_trend < 0:
        report_lines.append(f"- 📉 GPM падает ({gpm_trend}) — нужно больше фарма.")
    if deaths_trend > 0:
        report_lines.append(f"- 📉 Смертей стало больше (+{deaths_trend}) — будь осторожнее.")
    elif deaths_trend < 0:
        report_lines.append(f"- 📈 Смертей стало меньше ({deaths_trend}) — молодец!")
    report_lines.append("")

    # Критические ошибки
    if critical_errors:
        report_lines.append("## 🔴 Критические ошибки")
        for err in critical_errors:
            report_lines.append(f"### {err['issue']}")
            report_lines.append(f"- **Текущее:** {err['value']}")
            report_lines.append(f"- **Цель:** {err['target']}")
            report_lines.append(f"- **Как исправить:** {err['fix']}")
            report_lines.append("")

    # Частые проблемы
    if error_counter:
        report_lines.append("## ⚠️ Частые проблемы")
        names = {'gpm': 'Низкий GPM', 'xpm': 'Низкий XPM', 'lhpm': 'Мало ластхитов',
                 'deaths': 'Много смертей', 'td': 'Мало урона по башням',
                 'dpm': 'Мало урона по героям', 'kda': 'Низкий KDA', 'kill_part': 'Низкий вклад в убийства'}
        for err, count in error_counter.most_common():
            report_lines.append(f"- **{names.get(err, err)}:** {count} из {len(matches)} матчей ({round(count/len(matches)*100)}%)")
        report_lines.append("")

    # Лучший/худший матч
    report_lines.append("## Лучший и худший матч")
    report_lines.append(f"- **Лучший KDA:** {best_kda['kda']} ({best_kda['hero_name']}, матч {best_kda['match_id']})")
    report_lines.append(f"- **Худший KDA:** {worst_kda['kda']} ({worst_kda['hero_name']}, матч {worst_kda['match_id']})")
    report_lines.append("")

    # Рекомендации
    report_lines.append("## 💡 Что делать дальше")
    if avg_deaths > 6:
        report_lines.append("1. **Смертей слишком много.** Включи миникарту на полный экран и смотри на неё после каждого каста.")
        report_lines.append("2. Не лезь в бой, если не видишь всех врагов на карте.")
        report_lines.append("3. Держи дистанцию — герой уязвим, не стой в первых рядах.")
    if avg_lhpm < 5:
        report_lines.append("4. **Улучшай фарм.** Практикуй ластхиты в тренировке 5 минут перед игрой.")
        report_lines.append("5. Используй Nether Blast для быстрого зачищения волн и джангла.")
    report_lines.append("6. После каждой драки — сразу пуш, не возвращайся в базу без причины.")
    report_lines.append("7. Играй от объектов: башни, Рошан, high ground — а не от убийств.")
    report_lines.append("")

    report_text = "\n".join(report_lines)

    return {
        "matches_analyzed": len(matches),
        "win_rate": win_rate,
        "avg_gpm": avg_gpm,
        "avg_xpm": avg_xpm,
        "avg_kda": avg_kda,
        "avg_deaths": avg_deaths,
        "avg_lhpm": avg_lhpm,
        "avg_dpm": avg_dpm,
        "avg_tower_damage": avg_td,
        "avg_kill_part": avg_kill_part,
        "gpm_trend": gpm_trend,
        "deaths_trend": deaths_trend,
        "critical_errors": critical_errors,
        "error_counter": dict(error_counter.most_common()),
        "best_kda": {"match_id": best_kda['match_id'], "kda": best_kda['kda'], "hero": best_kda['hero_name']},
        "worst_kda": {"match_id": worst_kda['match_id'], "kda": worst_kda['kda'], "hero": worst_kda['hero_name']},
        "report": report_text,
        "matches": matches,
    }


if __name__ == "__main__":
    ids = get_recent_match_ids(limit=10)
    r = generate_full_report(ids, max_matches=10)
    print(r['report'])
