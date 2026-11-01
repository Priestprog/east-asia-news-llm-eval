r"""Меры согласия аннотаторов.

Пороги постановки: $\alpha$ Криппендорфа $\ge 0.67$ — допустимо, $\ge 0.8$ — надёжно ($\alpha_G$ при разметке $G$,
$\alpha_h$ по шкалам 0–5 на $G_h$)
(по инвариантности, отвечаемости, типу вопроса и метке инвариантности — протокол разметки, §7); попарный
токенный F1 ответов $\ge 0.8$. Согласие людей также задаёт потолок для валидации метрик
(среднее попарное согласие — верхняя граница $r_S(m_k, \bar h)$).

Соглашение о данных: ``labels`` — матрица $R \times n$ (аннотаторы × единицы),
``None`` — пропущенная метка; единицы с менее чем двумя метками не участвуют.

Вход CLI — ``annotations.jsonl`` из ``argilla_tasks pull`` (строки ``{"draft_id", "annotator",
<поля>}``), выход — ``agreement.json`` со сводкой и списком единиц для ``adjudicate``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from itertools import combinations
from typing import Sequence

from code import REPO_ROOT, load_config

Label = int | float | str | None

DEFAULT_FIELDS = ("time_invariant", "answerable", "question_type", "label")

# Krippendorff (2011), «Computing Krippendorff's Alpha-Reliability», пример с пропусками:
# 4 наблюдателя × 12 единиц, номинальная шкала, alpha = 0.743
_K2011 = [
    [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
    [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
    [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
    [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None],
]
_K2011_NOMINAL = 0.743


def _codes(labels: Sequence[Sequence[Label]]) -> tuple[list[list[float]], int]:
    """Категории → числовые коды (NaN — пропуск); число различных категорий."""
    values = sorted({v for row in labels for v in row if v is not None}, key=str)
    index = {v: float(i) for i, v in enumerate(values)}
    return [[index[v] if v is not None else math.nan for v in row] for row in labels], len(values)


def krippendorff_alpha(labels: Sequence[Sequence[Label]], level: str = "nominal") -> float:
    r"""Коэффициент Криппендорфа $\alpha = 1 - D_o / D_e$.

    $D_o$ — наблюдаемое несогласие внутри единиц, $D_e$ — ожидаемое несогласие при случайном
    распределении всех меток; метрика различия $\mathrm{dist}^2(c, c')$ между категориями зависит от ``level``:
    ``nominal`` ($\mathrm{dist}^2 = \mathbb{I}[c \ne c']$), ``ordinal``, ``interval``
    ($\mathrm{dist}^2 = (c - c')^2$), ``ratio``. Подходит для любого числа аннотаторов и пропусков.
    Возвращает ``nan``, если $D_e = 0$ (все метки одинаковы).
    Реализация — через пакет ``krippendorff`` с проверкой на игрушечном примере из
    Krippendorff (2011).
    """
    import krippendorff

    if level == "nominal":
        data, n_values = _codes(labels)
    else:
        data = [[float(v) if v is not None else math.nan for v in row] for row in labels]
        n_values = len({v for row in labels for v in row if v is not None})
    n_units = len(data[0]) if data else 0
    pairable = sum(sum(not math.isnan(row[j]) for row in data) >= 2 for j in range(n_units))
    if n_values < 2 or pairable == 0:
        return math.nan
    return float(krippendorff.alpha(reliability_data=data, level_of_measurement=level))


def fleiss_kappa(labels: Sequence[Sequence[Label]]) -> float:
    r"""Fleiss $\kappa = (\bar P - \bar P_e) / (1 - \bar P_e)$ для номинальных меток.

    $\bar P$ — средняя по единицам доля согласных пар аннотаторов, $\bar P_e = \sum_c p_c^2$,
    где $p_c$ — доля меток категории $c$. Требует одинакового числа меток на единицу;
    единицы с пропусками исключаются (отличие от $\alpha$). Даётся как вторая, более
    известная комиссии мера.
    """
    units = [[row[j] for row in labels] for j in range(len(labels[0]) if labels else 0)]
    units = [u for u in units if all(v is not None for v in u)]
    if not units or len(units[0]) < 2:
        return math.nan
    m = len(units[0])
    p_units = [(sum(c * c for c in Counter(u).values()) - m) / (m * (m - 1)) for u in units]
    totals = Counter(v for u in units for v in u)
    p_e = sum((c / (len(units) * m)) ** 2 for c in totals.values())
    if p_e == 1:
        return math.nan
    return (sum(p_units) / len(units) - p_e) / (1 - p_e)


def _f1(a: list[str], b: list[str]) -> float:
    common = sum((Counter(a) & Counter(b)).values())
    if not a or not b or common == 0:
        return 0.0
    p, r = common / len(a), common / len(b)
    return 2 * p * r / (p + r)


def answer_f1(a: str | Sequence[str] | None, b: str | Sequence[str] | None) -> float | None:
    """F1 по леммам между ответами двух аннотаторов; ответ — строка или список «ответ + алиасы»
    (берётся максимум по парам вариантов). ``None``, если ответа нет хотя бы у одного."""
    from code.eval.metrics_reference import lemmatize_tokens

    va = [a] if isinstance(a, str) else [x for x in (a or []) if x]
    vb = [b] if isinstance(b, str) else [x for x in (b or []) if x]
    if not va or not vb:
        return None
    return max(_f1(lemmatize_tokens(x), lemmatize_tokens(y)) for x in va for y in vb)


def unit_answer_f1(answers: Sequence[str | Sequence[str] | None]) -> list[float]:
    """Попарные F1 ответов одной единицы (пары с пропуском не учитываются)."""
    return [f for x, y in combinations(answers, 2) if (f := answer_f1(x, y)) is not None]


def pairwise_answer_f1(answers: Sequence[Sequence[str | Sequence[str] | None]]) -> float:
    r"""Среднее по единицам и по парам аннотаторов $(r, r')$ токенного F1 их черновых ответов.

    $\mathrm{F1}(a, a') = \frac{2 P R}{P + R}$ по мультимножествам лемм после нормализации
    (та же ``normalize``/лемматизация, что в ``code.eval.metrics_reference``). Порог включения
    единицы — $\ge 0.8$; ниже — адъюдикация. Пары с пропуском не учитываются.
    ``answers[j]`` — ответы единицы $j$ по аннотаторам: строка или «ответ + алиасы».
    """
    per_unit = [sum(fs) / len(fs) for unit in answers if (fs := unit_answer_f1(unit))]
    return sum(per_unit) / len(per_unit) if per_unit else math.nan


def _verdict(alpha: float, low: float, high: float) -> str:
    if math.isnan(alpha):
        return "не определено"
    return "надёжно" if alpha >= high else "допустимо" if alpha >= low else "ниже порога"


def agreement_report(
    annotations: Sequence[dict],
    fields: Sequence[str] = DEFAULT_FIELDS,
    krippendorff_alpha_min: float = 0.67,
    krippendorff_alpha_reliable: float = 0.8,
    f1_min: float = 0.8,
) -> dict:
    r"""Сводка: $\alpha$ и $\kappa$ по каждому полю с вердиктом (ниже порога / допустимо / надёжно),
    попарный F1 ответов, список единиц ниже порога — вход для ``adjudicate``."""
    annotators = sorted({a["annotator"] for a in annotations})
    units = sorted({a["draft_id"] for a in annotations})
    cell = {(a["annotator"], a["draft_id"]): a for a in annotations}

    def matrix(field: str) -> list[list[Label]]:
        return [[(cell.get((r, u)) or {}).get(field) for u in units] for r in annotators]

    report: dict = {"annotators": annotators, "units": len(units),
                    "complete_units": sum(all((r, u) in cell for r in annotators) for u in units), "fields": {}}
    for field in fields:
        labels = matrix(field)
        alpha, kappa = krippendorff_alpha(labels), fleiss_kappa(labels)
        report["fields"][field] = {
            "alpha": None if math.isnan(alpha) else round(alpha, 4),
            "kappa": None if math.isnan(kappa) else round(kappa, 4),
            "n_pairable_units": sum(sum(v is not None for v in col) >= 2 for col in zip(*labels)),
            "verdict": _verdict(alpha, krippendorff_alpha_min, krippendorff_alpha_reliable),
        }

    answers, flagged = [], []
    for u in units:
        rows = [cell.get((r, u)) for r in annotators]
        votes = [row.get("time_invariant") for row in rows if row]
        unit_answers = [([row["answer_canonical_fixed"], *row.get("answer_aliases_fixed", [])]
                         if row and row.get("answer_canonical_fixed") else None) for row in rows]
        fs = unit_answer_f1(unit_answers)
        if fs:
            answers.append(unit_answers)
        reasons = [f for f in fields if len({row.get(f) for row in rows if row}) > 1]
        if fs and min(fs) < f1_min:
            reasons.append(f"answer_f1={min(fs):.2f}")
        excluded = sum(v == 0 for v in votes) >= 2
        if reasons or excluded:
            flagged.append({"draft_id": u, "excluded_by_votes": excluded, "disagreement": reasons, "votes": votes})
    f1 = pairwise_answer_f1(answers)
    report["pairwise_answer_f1"] = None if math.isnan(f1) else round(f1, 4)
    report["f1_verdict"] = "не определено" if math.isnan(f1) else ("допустимо" if f1 >= f1_min else "ниже порога")
    report["flagged_units"] = flagged
    inv = report["fields"].get("time_invariant", {})
    ans = report["fields"].get("answerable", {})
    report["gate_g1"] = inv.get("alpha") is not None and inv["alpha"] >= krippendorff_alpha_min
    report["pilot_success"] = (report["gate_g1"] and ans.get("alpha") is not None
                               and ans["alpha"] >= krippendorff_alpha_min
                               and report["pairwise_answer_f1"] is not None
                               and report["pairwise_answer_f1"] >= f1_min)
    return report


def self_check() -> float:
    """Проверка реализации на примере Krippendorff (2011): номинальная alpha = 0.743."""
    alpha = krippendorff_alpha(_K2011)
    if abs(alpha - _K2011_NOMINAL) > 5e-4:
        raise AssertionError(f"krippendorff_alpha: {alpha:.4f} вместо {_K2011_NOMINAL}")
    return alpha


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--annotations", default="data/golden_set/v0.1-pilot/annotations.jsonl")
    parser.add_argument("--out", default="data/golden_set/v0.1-pilot/agreement.json")
    parser.add_argument("--self-check", action="store_true", help="только проверка на примере Krippendorff (2011)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    alpha = self_check()
    if args.self_check:
        print(f"Krippendorff (2011): alpha = {alpha:.3f}")
        return 0
    cfg = load_config(REPO_ROOT / args.config)
    with open(REPO_ROOT / args.annotations, encoding="utf-8") as fh:
        annotations = [json.loads(line) for line in fh if line.strip()]
    report = agreement_report(annotations,
                              krippendorff_alpha_min=cfg.get("krippendorff_alpha_min", 0.67),
                              krippendorff_alpha_reliable=cfg.get("krippendorff_alpha_reliable", 0.8),
                              f1_min=cfg.get("pairwise_answer_f1_min", 0.8))
    out = REPO_ROOT / args.out
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.relative_to(REPO_ROOT)}: единиц {report['units']} (полных {report['complete_units']}), "
          f"аннотаторы {', '.join(report['annotators'])}")
    for field, r in report["fields"].items():
        print(f"  {field}: alpha = {r['alpha']}, kappa = {r['kappa']} ({r['verdict']}, единиц {r['n_pairable_units']})")
    print(f"  попарный F1 ответов = {report['pairwise_answer_f1']} ({report['f1_verdict']})")
    print(f"  G1 (alpha инвариантности ≥ порога): {'да' if report['gate_g1'] else 'нет'}; "
          f"критерий пилота: {'выполнен' if report['pilot_success'] else 'не выполнен'}; "
          f"к адъюдикации или исключению: {len(report['flagged_units'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
