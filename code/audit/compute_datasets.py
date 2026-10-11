r"""Дефекты существующих наборов вопросов, мешающие долговечной оценке над зафиксированным корпусом.

Для каждого набора измеряются доли вопросов с одним из свойств (95%-й перцентильный
бутстреп-интервал по вопросам):

* ``time_dependent_label`` — вопрос времязависим по разметке самих авторов (FreshQA, CDQA);
* ``gold_revised`` — эталонный ответ исправлен в следующей редакции набора (RGB: исходные файлы
  против ``*_refine``);
* ``draft_modified``, ``answer_rewritten`` — машинный черновик правили аннотаторы (CDQA);
* ``implicit_expression``, ``relative_type`` — время в вопросе задано неявно или относительно (ChronoQA);
* ``question_overlap``, ``id_reused`` — доля вопросов последней версии, встречавшихся в первой, и доля
  идентификаторов, за которыми в разных версиях стоят разные вопросы (DRAGOn);
* ``relative_time`` — формулировка содержит маркер момента запроса (правило $E_2$, ``markers.py``);
* ``no_date_anchor`` — в формулировке нет явной даты.

Выход: ``results/audit/datasets_measures.csv``.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from code.audit import B, RESULTS_DIR, SEED
from code.audit.common import normalize_text, record_sources, rel, sha256, share, write_csv
from code.audit.compute_freshqa import read_rows
from code.audit.download import freshqa_path, load_freshqa_versions, static_files
from code.audit.markers import DATE_ANCHOR, RELATIVE_TIME, has

LABELS = {
    "time_dependent_label": "вопрос времязависим по разметке авторов",
    "fast_label": "ответ меняется быстро по разметке авторов",
    "false_premise": "вопрос с ложной предпосылкой",
    "gold_revised": "эталонный ответ исправлен в следующей редакции",
    "draft_modified": "машинный черновик исправлен аннотаторами",
    "answer_rewritten": "эталонный ответ черновика переписан аннотаторами",
    "implicit_expression": "время в вопросе задано неявно",
    "relative_type": "вопрос об относительном времени",
    "question_overlap": "вопрос последней версии есть в первой",
    "id_reused": "идентификатор в двух версиях указывает на разные вопросы",
    "relative_time": "в формулировке есть маркер момента запроса",
    "no_date_anchor": "в формулировке нет явной даты",
}


def measure(dataset: str, subset: str, name: str, values, B: int = B, seed: int = SEED) -> dict:
    return {"dataset": dataset, "subset": subset, "measure": name, "label": LABELS[name], **share(values, B=B, seed=seed)}


def wording(dataset: str, subset: str, lang: str, questions: list[str], **kw) -> list[dict]:
    return [
        measure(dataset, subset, "relative_time", [has(RELATIVE_TIME[lang], q) for q in questions], **kw),
        measure(dataset, subset, "no_date_anchor", [not has(DATE_ANCHOR[lang], q) for q in questions], **kw),
    ]


def _files(dataset: str) -> list[dict]:
    files = [f for f in static_files() if f["dataset"] == dataset]
    for f in files:
        if not Path(f["path"]).exists():
            raise FileNotFoundError(f"{rel(f['path'])}: нет в кэше, запустите python -m code.audit --stage download")
    return files


def _sources(files: list[dict], records: dict[str, int]) -> list[dict]:
    return [{"version": f["version"], "file": rel(f["path"]), "url": f["url"], "sha256": sha256(f["path"]),
             "records": records.get(Path(f["path"]).name, "")} for f in files]


# --- Наборы ----------------------------------------------------------------------------------


def freshqa(**kw) -> list[dict]:
    base_v = next(v for v in load_freshqa_versions() if v.get("exportable"))
    header, body = read_rows(freshqa_path(base_v))
    ft, fp = header.index("fact_type"), header.index("false_premise")
    types = [r[ft].strip().lower() for r in body]
    subset = f"версия {base_v['date']}"
    return [
        measure("FreshQA", subset, "time_dependent_label", [t in ("slow-changing", "fast-changing") for t in types], **kw),
        measure("FreshQA", subset, "fast_label", [t == "fast-changing" for t in types], **kw),
        measure("FreshQA", subset, "false_premise", [r[fp].strip().upper() == "TRUE" for r in body], **kw),
        *wording("FreshQA", subset, "en", [r[header.index("question")] for r in body], **kw),
    ]


def _rgb_answer(raw: str) -> frozenset[str]:
    """Множество нормализованных эталонных ответов из строкового представления списка RGB."""
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        value = [raw]
    flat: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(item)
        else:
            flat.append(normalize_text(item))
    return frozenset(flat)


def rgb(**kw) -> tuple[list[dict], list[dict]]:
    files = _files("RGB")
    by_name = {Path(f["path"]).stem: f["path"] for f in files}
    rows, records = [], {}
    for lang in ("en", "zh"):
        data = {}
        for name in (lang, f"{lang}_refine"):
            lines = [json.loads(line) for line in Path(by_name[name]).read_text(encoding="utf-8").splitlines() if line.strip()]
            records[f"{name}.json"] = len(lines)
            data[name] = {str(x["id"]): x for x in lines}
        orig, refine = data[lang], data[f"{lang}_refine"]
        common = [i for i in orig if i in refine]
        rows.append(measure("RGB", lang, "gold_revised",
                            [_rgb_answer(orig[i]["answer"]) != _rgb_answer(refine[i]["answer"]) for i in common], **kw))
        rows.extend(wording("RGB", lang, lang, [refine[i]["query"] for i in common], **kw))
    return rows, _sources(files, records)


def cdqa(**kw) -> tuple[list[dict], list[dict]]:
    files = _files("CDQA")
    items = json.loads(Path(files[0]["path"]).read_text(encoding="utf-8"))
    questions = [it["qa"].replace("﻿", "").split("\n")[0].split(":", 1)[-1].strip() for it in items]
    ann = [it["annotation"] for it in items]
    rows = [
        measure("CDQA", "v1", "time_dependent_label", [a.get("知识动态性分类") in ("快速变化", "中速变化") for a in ann], **kw),
        measure("CDQA", "v1", "fast_label", [a.get("知识动态性分类") == "快速变化" for a in ann], **kw),
        measure("CDQA", "v1", "draft_modified", [str(a.get("分类1", "")).startswith("p") for a in ann], **kw),
        measure("CDQA", "v1", "answer_rewritten", [a.get("p-改写答案") not in (None, "", "None") for a in ann], **kw),
        *wording("CDQA", "v1", "zh", questions, **kw),
    ]
    return rows, _sources(files, {"CDQA_v1.json": len(items)})


def chronoqa(**kw) -> tuple[list[dict], list[dict]]:
    files = _files("ChronoQA")
    items = json.loads(Path(files[0]["path"]).read_text(encoding="utf-8"))
    rows = [
        measure("ChronoQA", "all", "implicit_expression", [x["temporal_expression_type"] == "implicit" for x in items], **kw),
        measure("ChronoQA", "all", "relative_type", [x["temporal_type"] == "relative" for x in items], **kw),
        *wording("ChronoQA", "all", "zh", [x["question"] for x in items], **kw),
    ]
    return rows, _sources(files, {"chronoqa.json": len(items)})


def dragon(**kw) -> tuple[list[dict], list[dict]]:
    import pandas as pd

    files = _files("DRAGOn")
    first, last = (pd.read_parquet(f["path"]) for f in files)
    v0, v1 = (f["version"] for f in files)
    seen = {normalize_text(q) for q in first["question"]}
    q_first = dict(zip(first["public_id"], first["question"].map(normalize_text)))
    q_last = dict(zip(last["public_id"], last["question"].map(normalize_text)))
    shared_ids = [i for i in q_last if i in q_first]
    rows = [
        measure("DRAGOn", f"{v1} против {v0}", "question_overlap", [normalize_text(q) in seen for q in last["question"]], **kw),
        measure("DRAGOn", f"{v1} против {v0}", "id_reused", [q_first[i] != q_last[i] for i in shared_ids], **kw),
        *wording("DRAGOn", v1, "ru", list(last["question"]), **kw),
    ]
    records = {Path(f["path"]).name: n for f, n in zip(files, (len(first), len(last)))}
    return rows, _sources(files, records)


def run(B: int = B, seed: int = SEED) -> list[dict]:
    kw = {"B": B, "seed": seed}
    rows = freshqa(**kw)
    for name, fn in (("RGB", rgb), ("CDQA", cdqa), ("ChronoQA", chronoqa), ("DRAGOn", dragon)):
        part, sources = fn(**kw)
        rows.extend(part)
        record_sources(name, sources)
    out = write_csv(rows, RESULTS_DIR / "datasets_measures.csv")
    print(f"наборы: {len({r['dataset'] for r in rows})}, величин: {len(rows)}; таблица: {rel(out)}")
    return rows


if __name__ == "__main__":
    run()
