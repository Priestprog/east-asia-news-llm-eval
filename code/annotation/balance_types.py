r"""Выбор черновика из меню кандидатов так, чтобы типы вопроса были представлены поровну (ADR-026).

По каждой позиции основного раунда модель черновиков предлагает меню (промпт ``draft-v2``,
``data/golden_set/drafts/candidates.jsonl``): не больше одного кандидата на каждый из восьми типов
вопроса с оценкой ``fit`` (1 — главный факт статьи, 2 — существенная деталь, 3 — второстепенная).
Здесь на каждую позицию выбирается ровно один кандидат. Позиции с ответом в документе и кандидаты
в $G^{\bot}$ выравниваются отдельно, каждая группа — по всем восьми типам.

Задача о назначениях (``scipy.optimize.linear_sum_assignment``): строки — позиции группы, столбцы —
пары (тип, место $k = 1, \dots, n$). Стоимость места $k$ — $M (2k - 1)$, поэтому сумма по
назначению равна $M \sum_t c_t^2$, где $c_t$ — число вопросов типа $t$, и минимум достигается
на самом равномерном распределении, которое допускают меню. $M$ больше суммы всех штрафов
кандидатов, поэтому штрафы выбирают кандидатов только среди одинаково равномерных распределений:
за ``fit``, за непройденные проверки черновика и, у позиций seed pool, за вопрос не на основе
исходного вопроса. Кандидата, цитату которого не удаётся найти в тексте документа даже по частям,
выбирают только при отсутствии другого выхода. Результат детерминирован.

Выход: черновики ``data/golden_set/drafts/drafts.jsonl`` (``draft_prompt_id = draft-v2``; в
``checks`` — ``menu_types`` и ``fit``) и отчёт ``data/golden_set/drafts/type_balance.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config
from code.annotation.argilla_tasks import evidence_parts
from code.annotation.generate_drafts import (DEFAULT_CONFIG, QUESTION_TYPES, candidate_draft, load_document,
                                             load_positions, load_seed_pool, read_jsonl)

M = 10_000                       # вес равномерности; больше суммы штрафов всех позиций группы
FIT_PENALTY = {1: 0, 2: 1, 3: 3}
CHECK_PENALTY = 2                # за каждую непройденную проверку: дата-якорь, дата в вопросе, дословная цитата
SEED_PENALTY = 1                 # позиция seed pool, вопрос не на основе исходного вопроса
MARKER_PENALTY = 1               # маркеры E1/E2/E4 в вопросе (эвристика)
NO_EVIDENCE = 10_000_000         # цитата не найдена в документе даже по частям
MISSING = 1_000_000_000          # у позиции нет кандидата этого типа
GROUPS = ("answerable", "unanswerable_candidate")


def evidence_found(evidence_zh: str, doc: dict) -> bool:
    """Цитата или хотя бы одна её часть (строки, куски между многоточиями) есть в тексте документа."""
    text = re.sub(r"\s+", "", (doc.get("text_zh") or "") + (doc.get("title_zh") or ""))
    return any(re.sub(r"\s+", "", part) in text for part in evidence_parts(evidence_zh))


def candidate_penalty(cand: dict, position: dict, doc: dict) -> int:
    checks = cand["checks"]
    penalty = FIT_PENALTY[cand["fit"]]
    penalty += CHECK_PENALTY * sum(not checks.get(k) for k in ("anchor_format_ok", "date_in_question",
                                                                "evidence_in_document"))
    penalty += MARKER_PENALTY * bool(checks.get("markers"))
    if position["origin"] == "seed" and cand["seed_question_used"] not in position.get("seed_refs", []):
        penalty += SEED_PENALTY
    if not evidence_found(cand["evidence_span_zh"], doc):
        penalty += NO_EVIDENCE
    return penalty


def assign(menus: Sequence[dict], positions: dict[str, dict], docs: dict[int, dict]) -> dict[str, dict]:
    """Один кандидат на позицию: самое равномерное распределение типов, затем наименьший штраф."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    n, n_types = len(menus), len(QUESTION_TYPES)
    slot_cost = M * (2 * np.arange(1, n + 1) - 1)                     # места k = 1..n каждого типа
    cost = np.full((n, n_types * n), MISSING, dtype=np.int64)
    by_type: list[dict[str, dict]] = []
    for i, menu in enumerate(menus):
        pos = positions[menu["position_id"]]
        cands = {c["question_type"]: c for c in menu["candidates"]}
        by_type.append(cands)
        for t_i, t in enumerate(QUESTION_TYPES):
            if t in cands:
                cost[i, t_i * n:(t_i + 1) * n] = slot_cost + candidate_penalty(cands[t], pos, docs[pos["webpage_id"]])
    rows, cols = linear_sum_assignment(cost)
    chosen = {}
    for i, col in zip(rows, cols):
        t = QUESTION_TYPES[col // n]
        if t not in by_type[i]:
            raise RuntimeError(f"{menus[i]['position_id']}: нет кандидата типа {t}")
        chosen[menus[i]["position_id"]] = by_type[i][t]
    return chosen


def build_drafts(menus: Sequence[dict], chosen: dict[str, dict], positions: dict[str, dict], cfg: dict,
                 seed_pool: dict[int, dict], docs: dict[int, dict]) -> list[dict]:
    out = []
    for menu in menus:
        pos = positions[menu["position_id"]]
        cand = chosen[menu["position_id"]]
        draft = candidate_draft(pos, cfg, menu, {k: v for k, v in cand.items() if k != "checks"},
                                docs[pos["webpage_id"]], seed_pool)
        draft.channel, draft.draft_model, draft.created_at = menu["channel"], menu["draft_model"], menu["created_at"]
        draft.draft_prompt_id = menu["draft_prompt_id"]
        draft.checks["menu_types"] = [c["question_type"] for c in menu["candidates"]]
        draft.checks["fit"] = cand["fit"]
        out.append(asdict(draft))
    return out


def _table(header: Sequence[str], rows: Sequence[Sequence]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]


def report(menus: Sequence[dict], drafts: Sequence[dict], positions: dict[str, dict], prompt_id: str) -> str:
    lines = ["# Выбор черновиков по типам вопроса (ADR-026)", "",
             f"Промпт `{prompt_id}`: по документу — меню кандидатов, не больше одного на тип вопроса; один кандидат "
             "на позицию выбран `code/annotation/balance_types.py` — самое равномерное распределение типов, которое "
             "допускают меню, затем наименьший штраф (`fit`, проверки черновика, связь с исходным вопросом seed pool).",
             "", f"Позиций: {len(drafts)}; кандидатов в меню: {sum(len(m['candidates']) for m in menus)}.", ""]
    for group in GROUPS:
        g_menus = [m for m in menus if m["role"] == group]
        g_drafts = [d for d in drafts if d["role"] == group]
        if not g_menus:
            continue
        supply = Counter(c["question_type"] for m in g_menus for c in m["candidates"])
        got = Counter(d["question_type"] for d in g_drafts)
        target = len(g_drafts) / len(QUESTION_TYPES)
        lines += [f"## {group}: {len(g_drafts)} позиций, цель — {target:.1f} на тип", ""]
        lines += _table(["Тип", "Позиций с кандидатом", "Выбрано", "fit 1 / 2 / 3"],
                        [(t, supply[t], got[t], " / ".join(str(sum(1 for d in g_drafts if d["question_type"] == t
                                                                   and d["checks"]["fit"] == f)) for f in (1, 2, 3)))
                         for t in QUESTION_TYPES])
        lines.append("")
    lines += ["## По регионам и происхождению", ""]
    keys = sorted({(positions[d["position_id"]]["region"], d["origin"]) for d in drafts})
    lines += _table(["Регион", "Происхождение", *QUESTION_TYPES, "Всего"],
                    [(r, o, *(sum(1 for d in drafts if positions[d["position_id"]]["region"] == r and d["origin"] == o
                                  and d["question_type"] == t) for t in QUESTION_TYPES),
                      sum(1 for d in drafts if positions[d["position_id"]]["region"] == r and d["origin"] == o))
                     for r, o in keys])
    best = sum(1 for d, m in zip(drafts, menus) if any(c["fit"] == 1 for c in m["candidates"]) and d["checks"]["fit"] != 1)
    seed = [d for d in drafts if d["origin"] == "seed"]
    lines += ["", f"Выбран кандидат с fit > 1, хотя в меню был кандидат с fit = 1: {best} позиций.",
              f"Позиции seed pool: {len(seed)}; вопрос на основе исходного вопроса — "
              f"{sum(1 for d in seed if d['seed_pool_ref'])}.",
              f"Непройденные проверки у выбранных: дата в вопросе — {sum(not d['checks']['date_in_question'] for d in drafts)}, "
              f"дословная цитата — {sum(not d['checks']['evidence_in_document'] for d in drafts)}, "
              f"формат даты-якоря — {sum(not d['checks']['anchor_format_ok'] for d in drafts)}.", ""]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--candidates", default=None, help="меню кандидатов (по умолчанию paths.candidates_main)")
    parser.add_argument("--out", default=None, help="черновики (по умолчанию paths.out_main)")
    parser.add_argument("--report", default=None, help="отчёт (по умолчанию paths.balance_report_main)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(REPO_ROOT / args.config)
    paths = cfg["paths"]
    menus = read_jsonl(REPO_ROOT / (args.candidates or paths["candidates_main"]))
    positions = {p["position_id"]: p for p in load_positions(REPO_ROOT / paths["positions"], main=True)}
    errors = [m["position_id"] for m in menus if m["error"]]
    if errors or {m["position_id"] for m in menus} != set(positions):
        missing = sorted(set(positions) - {m["position_id"] for m in menus})
        raise SystemExit(f"меню неполны: с ошибкой {errors}, нет {missing}")
    menus = [m for m in menus if m["position_id"] in positions]
    docs = {p["webpage_id"]: load_document(REPO_ROOT / paths["documents"], p["webpage_id"]) for p in positions.values()}
    seed_pool = load_seed_pool(REPO_ROOT / paths["seed_pool"])
    cfg["prompt_id"] = menus[0]["draft_prompt_id"]
    chosen = {}
    for group in GROUPS:
        chosen.update(assign([m for m in menus if m["role"] == group], positions, docs))
    drafts = build_drafts(menus, chosen, positions, cfg, seed_pool, docs)
    out = REPO_ROOT / (args.out or paths["out_main"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in drafts), encoding="utf-8")
    rep = REPO_ROOT / (args.report or paths["balance_report_main"])
    rep.write_text(report(menus, drafts, positions, cfg["prompt_id"]), encoding="utf-8")
    counts = Counter(d["question_type"] for d in drafts)
    print(f"{out.relative_to(REPO_ROOT)}: {len(drafts)} черновиков; " + ", ".join(f"{t} — {counts[t]}" for t in QUESTION_TYPES))
    print(f"отчёт: {rep.relative_to(REPO_ROOT)}")
    unsuitable = [d["position_id"] for d in drafts if not d["suitable"]]
    if unsuitable:
        print(f"непригодные документы (заменить резервом): {', '.join(unsuitable)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
