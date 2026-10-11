r"""Сводная таблица «почему существующие наборы не подходят» по результатам аудита.

Описательные столбцы (язык, эталон, опорные документы, отказы, согласие, время, версии) заданы
вручную по данным и статьям наборов; столбец «измеренный дефект» собирается из таблиц
``freshqa_staleness.csv``, ``datasets_measures.csv`` и ``seed_pool_markers.csv``. Для CRAG,
RecencyQA и AbstentionBench данные не скачивались, сведения взяты из статей и документации.

Выход: ``results/audit/datasets_summary.csv`` и ``results/audit/datasets_summary.md``.
"""

from __future__ import annotations

from code.audit import RESULTS_DIR
from code.audit.common import read_csv, rel, write_csv

COLUMNS = {
    "dataset": "Набор",
    "language": "Язык",
    "questions": "Вопросов",
    "reference": "Эталонные ответы",
    "evidence": "Опорные документы",
    "abstention": "Вопросы с ответом-отказом",
    "agreement": "Согласие аннотаторов",
    "time": "Время вопроса",
    "versions": "Версии",
    "defect": "Измеренный дефект",
    "basis": "Сведения",
}

FACTS = [
    {"dataset": "FreshQA", "language": "en", "questions": "600", "reference": "да, до 10 вариантов",
     "evidence": "ссылка-источник, корпуса нет", "abstention": "нет; 150 вопросов с ложной предпосылкой",
     "agreement": "не сообщается", "time": "год актуальности ответа", "versions": "87, доступны 75",
     "basis": "измерено"},
    {"dataset": "RGB", "language": "zh, en", "questions": "300 + 300", "reference": "да",
     "evidence": "фрагменты веб-поиска, корпуса нет", "abstention": "проверка отказа на шумовых фрагментах",
     "agreement": "не сообщается", "time": "нет даты вопроса", "versions": "исходная и уточнённая",
     "basis": "измерено"},
    {"dataset": "CRAG", "language": "en", "questions": "4409", "reference": "да, с вариантами",
     "evidence": "5 веб-страниц, релевантность не гарантирована", "abstention": "отказ оценивается выше ошибки",
     "agreement": "н/д", "time": "дата и время запроса", "versions": "v4",
     "basis": "по статье и документации"},
    {"dataset": "CDQA", "language": "zh", "questions": "1339", "reference": "да",
     "evidence": "ссылка проверки, корпуса нет", "abstention": "нет",
     "agreement": "не сообщается", "time": "нет даты вопроса", "versions": "одна",
     "basis": "измерено"},
    {"dataset": "ChronoQA", "language": "zh", "questions": "5176", "reference": "да",
     "evidence": "фрагменты новостей с URL", "abstention": "нет",
     "agreement": "не сообщается", "time": "дата вопроса", "versions": "одна",
     "basis": "измерено"},
    {"dataset": "DRAGOn", "language": "ru", "questions": "600 в версии", "reference": "да",
     "evidence": "текст новости", "abstention": "нет",
     "agreement": "не сообщается", "time": "нет даты вопроса", "versions": "15, набор пересобирается",
     "basis": "измерено"},
    {"dataset": "RecencyQA", "language": "en", "questions": "4031", "reference": "н/д",
     "evidence": "корпуса нет", "abstention": "н/д",
     "agreement": "н/д", "time": "метки частоты смены ответа", "versions": "выдаётся по запросу",
     "basis": "по статье"},
    {"dataset": "AbstentionBench", "language": "en", "questions": "20 наборов", "reference": "из исходных наборов",
     "evidence": "корпуса нет", "abstention": "да, основное назначение",
     "agreement": "н/д", "time": "часть вопросов устарела", "versions": "загрузчик исходных наборов",
     "basis": "по статье"},
    {"dataset": "Вопросы промышленной системы", "language": "ru, en", "questions": "388", "reference": "нет",
     "evidence": "статья WARC без стабильного ключа", "abstention": "нет",
     "agreement": "нет, без проверки человеком", "time": "нет даты вопроса", "versions": "одна",
     "basis": "измерено, эвристика"},
]

PAPER_DEFECTS = {
    "CRAG": "вопросы real-time и fast-changing теряют эталон после даты запроса",
    "RecencyQA": "оценивает знание свежих фактов, а не ответ над заданным корпусом",
    "AbstentionBench": "неотвечаемость задана вопросом, а не отсутствием ответа в корпусе",
}


def pct(rate: float | str) -> str:
    """Доля в процентах: целое число от 10 %, иначе один знак после запятой."""
    value = 100 * float(rate)
    text = f"{value:.0f}" if value >= 10 or value == 0 else f"{value:.1f}".replace(".", ",")
    return f"{text} %"


def defects() -> dict[str, str]:
    staleness = read_csv(RESULTS_DIR / "freshqa_staleness.csv")
    last = max(r["version"] for r in staleness)
    at_last = {r["fact_type"]: r for r in staleness if r["version"] == last and r["definition"] == "any"}
    months = round(float(next(iter(at_last.values()))["months"]))
    m = {(r["dataset"], r["subset"], r["measure"]): r for r in read_csv(RESULTS_DIR / "datasets_measures.csv")}
    get = lambda ds, measure: next(r for (d, _, k), r in m.items() if d == ds and k == measure)  # noqa: E731
    rgb = {lang: m[("RGB", lang, "gold_revised")] for lang in ("en", "zh")}
    seed = {r["rule"]: r for r in read_csv(RESULTS_DIR / "seed_pool_markers.csv")}
    return {
        "FreshQA": (f"за {months} месяцев изменились эталоны {pct(at_last['fast-changing']['rate'])} быстро меняющихся, "
                    f"{pct(at_last['slow-changing']['rate'])} медленно меняющихся и {pct(at_last['never-changing']['rate'])} "
                    f"неизменных вопросов"),
        "RGB": (f"в уточнённой редакции исправлены эталоны {pct(rgb['en']['rate'])} (en) и {pct(rgb['zh']['rate'])} (zh) "
                f"вопросов; без явной даты {pct(m[('RGB', 'en', 'no_date_anchor')]['rate'])} (en) "
                f"и {pct(m[('RGB', 'zh', 'no_date_anchor')]['rate'])} (zh)"),
        "CDQA": (f"{pct(get('CDQA', 'time_dependent_label')['rate'])} вопросов времязависимы по разметке авторов; "
                 f"{pct(get('CDQA', 'draft_modified')['rate'])} машинных черновиков исправлены аннотаторами; "
                 f"без явной даты {pct(get('CDQA', 'no_date_anchor')['rate'])}"),
        "ChronoQA": (f"все вопросы времязависимы по замыслу; у {pct(get('ChronoQA', 'implicit_expression')['rate'])} "
                     f"время задано неявно, {pct(get('ChronoQA', 'relative_type')['rate'])} об относительном времени"),
        "DRAGOn": (f"вопросов последней версии в первой: {pct(get('DRAGOn', 'question_overlap')['rate'])}; "
                   f"{pct(get('DRAGOn', 'id_reused')['rate'])} идентификаторов указывают в двух версиях на разные вопросы; "
                   f"без явной даты {pct(get('DRAGOn', 'no_date_anchor')['rate'])}"),
        "Вопросы промышленной системы": (
            f"{pct(seed['any_static']['rate'])} отмечены правилами E1, E2, E4 (прогноз, момент запроса, оценка); "
            f"{pct(seed['compound']['rate'])} составные; без явной даты {pct(seed['no_date_anchor']['rate'])}"),
        **PAPER_DEFECTS,
    }


def run() -> list[dict]:
    measured = defects()
    rows = [{k: fact.get(k, "") for k in COLUMNS} | {"defect": measured[fact["dataset"]]} for fact in FACTS]
    write_csv(rows, RESULTS_DIR / "datasets_summary.csv")
    lines = [
        "# Почему существующие наборы не подходят для долговечной оценки",
        "",
        "Таблица собрана `python -m code.audit` по результатам аудита (`results/audit/*.csv`). "
        "«Измерено» — доли посчитаны по скачанным данным с 95%-м бутстреп-интервалом в исходных таблицах; "
        "«по статье» — данные не скачивались; «н/д» — сведений нет.",
        "",
        "| " + " | ".join(COLUMNS.values()) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    lines += ["| " + " | ".join(r[k] for k in COLUMNS) + " |" for r in rows]
    out = RESULTS_DIR / "datasets_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"сводная таблица: {len(rows)} наборов; {rel(out)}")
    return rows


if __name__ == "__main__":
    run()
