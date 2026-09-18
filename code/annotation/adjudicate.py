r"""Адъюдикация расхождений разметчиков.

Правило включения: единица входит в $G$ при единогласии $R$ разметчиков по инвариантности
($\widehat{\mathrm{Inv}}(q) = \mathbb{1}[\sum_{r=1}^{R} z_r(q) = R]$), отвечаемости и типу
и при попарном F1 ответов $\ge 0.8$. Иначе единица передаётся четвёртому эксперту,
решение которого фиксируется вместе с обоснованием; поле ``provenance.adjudicated = true``.
Эксперт может исключить единицу (с указанием правила $E_1$–$E_5$ или причины).
"""

from __future__ import annotations

import argparse
from typing import Sequence


def find_disagreements(
    annotations: Sequence[dict],
    fields: Sequence[str] = ("time_invariant", "answerable", "question_type"),
    f1_min: float = 0.8,
) -> list[dict]:
    """Единицы без единогласия по ``fields`` или с попарным F1 ответов ниже порога."""
    raise NotImplementedError("реализация — часть работы")


def export_adjudication_sheet(items: Sequence[dict], path: str) -> None:
    """Лист для четвёртого эксперта: все метки разметчиков рядом, поля решения и обоснования."""
    raise NotImplementedError("реализация — часть работы")


def apply_adjudication(annotations: Sequence[dict], adjudications: Sequence[dict]) -> list[dict]:
    """Сливает решения эксперта с разметкой: итоговые метки, ``adjudicated``, исключения."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--sheets-dir", default="data/golden_set/v0.1-pilot/sheets")
    parser.add_argument("--adjudications", default="data/golden_set/v0.1-pilot/adjudication.csv")
    parser.add_argument("--out", default="data/golden_set/v0.1-pilot/annotations_final.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
