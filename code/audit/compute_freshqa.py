r"""Устаревание эталонных ответов FreshQA между версиями набора.

FreshQA (Vu et al., 2023) — 600 вопросов с разметкой типа факта ``fact_type``
(never-, slow-, fast-changing) и эталонными ответами ``answer_0`` … ``answer_9``; авторы
регулярно обновляют ответы и публикуют каждую версию отдельной таблицей Google Sheets.

Для базовой версии $v_0$ (15 октября 2023 года) и каждой из 74 более поздних доступных версий $v$
вопросы сопоставляются по нормализованному тексту (идентификаторы между версиями нестабильны).
Для каждого вопроса $q$:

* $s_{\mathrm{any}}(q; v) = \mathbb{I}[A^*_v(q) \ne A^*_{v_0}(q)]$ — изменилось множество эталонных
  ответов (канонический ответ и алиасы после нормализации);
* $s_{\mathrm{main}}(q; v) = \mathbb{I}[a^*_{0,v}(q) \ne a^*_{0,v_0}(q)]$ — изменился канонический ответ
  ``answer_0``; это более строгая оценка, не учитывающая добавление алиасов.

Доля устаревших эталонов типа $c$ — среднее индикатора по вопросам этого типа в $v_0$
с 95%-м перцентильным бутстреп-интервалом по вопросам.

Выход (только таблицы, без рисунков):

* ``results/audit/freshqa_staleness.csv`` — доли по версиям, типам и определениям; столбец
  ``quarterly`` отмечает последнюю версию каждого квартала (первый прогон, эскиз графика);
* ``results/audit/freshqa_never_changed.csv`` — неизменные по разметке вопросы, эталон которых
  изменился к последней версии, для ручного разбора причин.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Sequence

from code.audit import B, RESULTS_DIR, SEED
from code.audit.common import normalize_text, record_sources, rel, sha256, share, write_csv
from code.audit.download import FRESHQA_EXPORT, freshqa_path, load_freshqa_versions

FACT_TYPES = ("never-changing", "slow-changing", "fast-changing")


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """Заголовок и строки CSV версии; над заголовком в выгрузке стоят строки-предупреждения."""
    rows = list(csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8"))))
    header_idx = next(i for i, row in enumerate(rows) if "question" in row and "fact_type" in row)
    header = rows[header_idx]
    q = header.index("question")
    body = [row for row in rows[header_idx + 1:] if len(row) > q and row[q].strip()]
    return header, body


def read_version(path: Path) -> dict[str, dict]:
    """Читает CSV версии: ``{нормализованный вопрос: {fact_type, false_premise, main, answers}}``.

    Вопросы, встречающиеся в версии дважды, отбрасываются.
    """
    header, body = read_rows(path)
    col = {name: header.index(name) for name in header if name}
    answer_cols = [col[f"answer_{k}"] for k in range(10) if f"answer_{k}" in col]
    out: dict[str, dict] = {}
    duplicates: set[str] = set()
    for row in body:
        key = normalize_text(row[col["question"]])
        answers = [normalize_text(row[c]) for c in answer_cols if c < len(row) and row[c].strip()]
        record = {
            "question": row[col["question"]].strip(),
            "fact_type": row[col["fact_type"]].strip().lower(),
            "false_premise": row[col["false_premise"]].strip().upper() == "TRUE" if "false_premise" in col else False,
            "main": answers[0] if answers else "",
            "answers": frozenset(answers),
        }
        if key in out:
            duplicates.add(key)
        out[key] = record
    for key in duplicates:
        out.pop(key, None)
    return out


def staleness_rows(
    base: dict[str, dict], later: dict[str, dict], base_date: str, later_date: str,
    B: int = B, seed: int = SEED,
) -> list[dict]:
    """Строки таблицы устаревания для пары версий $(v_0, v)$ по каждому типу факта и определению."""
    import pandas as pd

    months = (pd.Timestamp(later_date) - pd.Timestamp(base_date)).days / 30.4375
    common = [q for q in base if q in later]
    rows = []
    for fact_type in FACT_TYPES:
        qs = [q for q in common if base[q]["fact_type"] == fact_type]
        for definition in ("any", "main"):
            key = "answers" if definition == "any" else "main"
            values = [base[q][key] != later[q][key] for q in qs]
            rows.append({
                "base_version": base_date,
                "version": later_date,
                "months": round(months, 2),
                "fact_type": fact_type,
                "definition": definition,
                **share(values, B=B, seed=seed),
            })
    return rows


def pick_quarterly(dates: Sequence[str]) -> list[str]:
    """Последняя доступная версия каждого календарного квартала."""
    by_quarter: dict[str, str] = {}
    for d in sorted(dates):
        year, month = int(d[:4]), int(d[5:7])
        by_quarter[f"{year}Q{(month - 1) // 3 + 1}"] = d
    return sorted(by_quarter.values())


def run(B: int = B, seed: int = SEED) -> list[dict]:
    versions = [v for v in load_freshqa_versions() if v.get("exportable")]
    base_v, later_vs = versions[0], versions[1:]
    quarterly = set(pick_quarterly([v["date"] for v in later_vs]))

    base_path = freshqa_path(base_v)
    base = read_version(base_path)
    sources = [{"version": base_v["date"], "file": rel(base_path), "url": FRESHQA_EXPORT.format(sheet_id=base_v["sheet_id"]),
                "sha256": sha256(base_path), "records": len(base)}]
    rows, last = [], None
    for v in later_vs:
        path = freshqa_path(v)
        if not path.exists():
            raise FileNotFoundError(f"{rel(path)}: нет в кэше, запустите python -m code.audit --stage download")
        later = read_version(path)
        sources.append({"version": v["date"], "file": rel(path), "url": FRESHQA_EXPORT.format(sheet_id=v["sheet_id"]),
                        "sha256": sha256(path), "records": len(later)})
        for row in staleness_rows(base, later, base_v["date"], v["date"], B=B, seed=seed):
            rows.append(row | {"quarterly": v["date"] in quarterly})
        last = (v["date"], later)

    out = write_csv(rows, RESULTS_DIR / "freshqa_staleness.csv")
    last_date, last_version = last
    changed = [
        {
            "question": base[q]["question"],
            "answer_base": base[q]["main"],
            "answer_last": last_version[q]["main"],
            "aliases_base": " | ".join(sorted(base[q]["answers"])),
            "aliases_last": " | ".join(sorted(last_version[q]["answers"])),
            "last_version": last_date,
        }
        for q in base
        if q in last_version and base[q]["fact_type"] == "never-changing"
        and base[q]["answers"] != last_version[q]["answers"]
    ]
    write_csv(sorted(changed, key=lambda r: r["question"]), RESULTS_DIR / "freshqa_never_changed.csv")
    record_sources("FreshQA", sources)
    print(f"FreshQA: базовая версия {base_v['date']}, сравнено версий: {len(later_vs)}; таблица: {rel(out)}")
    return rows


if __name__ == "__main__":
    run()
