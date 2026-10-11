r"""Эвристическая проверка 388 вопросов промышленной системы (seed pool) правилами исключения.

Вопросы сгенерированы языковой моделью по переводам статей без проверки человеком
(``data/seed_pool/provenance.md``). Для каждого русского вопроса проверяются маркеры правил
$E_1$ (прогноз и гипотетика), $E_2$ (момент запроса), $E_4$ (оценочная позиция), а также
фрагменты латиницей или иероглифами, составные формулировки и отсутствие явной даты (``markers.py``).
Доля вопросов, отмеченных хотя бы одним из правил $E_1$, $E_2$, $E_4$, — эвристическая оценка
доли вопросов, которые не удовлетворяют $\mathrm{Inv}(q)$ и не могут войти в эталон без переписывания.

Выход:

* ``results/audit/seed_pool_markers.csv`` — доли по правилам с 95%-м бутстреп-интервалом;
* ``results/audit/seed_pool_flagged.csv`` — отмеченные вопросы с перечнем сработавших правил.
"""

from __future__ import annotations

import json
import re

from code.audit import B, RESULTS_DIR, SEED, SEED_POOL_DIR
from code.audit.common import record_sources, rel, sha256, share, write_csv
from code.audit.markers import DATE_ANCHOR, SEED_POOL_RULES, STATIC_RULES, has

SOURCE_REPO = "ivran-lab/chinese-media"
SOURCE_COMMIT = "5676f9323863cc7c565fa23e63346f0425329ead"
SOURCE_PATH = "production/backend/rag/{lang}_rag_questions.json"

_WARC_RE = re.compile(r"^trans_txt_(?P<netloc>.+)-(?P<month>\d{4}-\d{2})\.warc_record_(?P<n>\d+)\.txt$")


def load(lang: str = "RU") -> dict[str, str]:
    """``{вопрос: warc_id}`` из копии файла промышленной системы."""
    with open(SEED_POOL_DIR / f"{lang}_rag_questions.json", encoding="utf-8") as fh:
        return json.load(fh)


def run(B: int = B, seed: int = SEED) -> list[dict]:
    questions = load("RU")
    items = list(questions.items())
    hits = {rule: [has(pattern, q) for q, _ in items] for rule, (_, pattern) in SEED_POOL_RULES.items()}
    hits["any_static"] = [any(hits[r][i] for r in STATIC_RULES) for i in range(len(items))]
    hits["no_date_anchor"] = [not has(DATE_ANCHOR["ru"], q) for q, _ in items]

    labels = {rule: label for rule, (label, _) in SEED_POOL_RULES.items()}
    labels["any_static"] = "хотя бы одно из правил E1, E2, E4"
    labels["no_date_anchor"] = "в формулировке нет явной даты"
    rows = [{"rule": rule, "label": labels[rule], **share(values, B=B, seed=seed)} for rule, values in hits.items()]
    out = write_csv(rows, RESULTS_DIR / "seed_pool_markers.csv")

    flagged = []
    for i, (q, warc_id) in enumerate(items):
        rules = [r for r in SEED_POOL_RULES if hits[r][i]]
        if rules:
            m = _WARC_RE.match(warc_id)
            flagged.append({"question": q, "rules": " ".join(rules), "netloc": m["netloc"] if m else "", "warc_id": warc_id})
    write_csv(flagged, RESULTS_DIR / "seed_pool_flagged.csv")

    record_sources("seed pool", [
        {"version": SOURCE_COMMIT[:7], "file": rel(SEED_POOL_DIR / f"{lang}_rag_questions.json"),
         "url": f"{SOURCE_REPO}@{SOURCE_COMMIT[:7]}:{SOURCE_PATH.format(lang=lang)}",
         "sha256": sha256(SEED_POOL_DIR / f"{lang}_rag_questions.json"), "records": len(load(lang))}
        for lang in ("EN", "RU")
    ])
    any_row = next(r for r in rows if r["rule"] == "any_static")
    print(f"seed pool: {any_row['n']} вопросов, отмечено правилами E1/E2/E4: {any_row['count']}; таблица: {rel(out)}")
    return rows


if __name__ == "__main__":
    run()
