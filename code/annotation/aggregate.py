r"""Сведение разметки трёх аннотаторов в итоговую запись (ADR-027).

Правило включения: элемент входит в $G$, только если все $R = 3$ аннотатора согласны по ключевым меткам:

* инвариантность — $\widehat{\mathrm{Inv}}(q) = \mathbb{I}[\sum_{r=1}^{R} z_r(q) = R]$;
* отвечаемость — все 1 (кандидат в $G^+$) или все 0 (кандидат в $G^{\bot}$).

Остальные метки берутся по большинству:

* ``question_type``, ``label``, ``category``, ``difficulty`` — мода; при трёх разных значениях элемент
  исключается.

Ответ (только $G^+$):

* нужны хотя бы два аннотатора, чьи канонические ответы совпадают — попарный токенный F1 $\ge 0.8$
  после нормализации (``agreement.normalize``, ``lemmatize_tokens``; максимум по алиасам);
* канонический ответ — версия из совпавшей пары с наиболее полным списком алиасов;
* алиасы — объединение по всем трём аннотаторам;
* $S^*$ и evidence span — объединение версий совпавших аннотаторов.

Иначе элемент исключается с указанием причины. Решений вне правила и ручных правок итоговых меток нет.
"""

from __future__ import annotations

import argparse
from typing import Sequence


def include_item(votes: Sequence[dict]) -> tuple[bool, str]:
    """Решение по одному элементу: ``(включить, причина исключения или "")`` по правилу модуля."""
    raise NotImplementedError("реализация — часть работы")


def merge_answers(votes: Sequence[dict], f1_min: float = 0.8) -> dict | None:
    """Канонический ответ и алиасы по совпавшей паре аннотаторов; ``None`` — совпавших ответов нет."""
    raise NotImplementedError("реализация — часть работы")


def merge_supporting(votes: Sequence[dict], agreeing: Sequence[str]) -> dict:
    """$S^*$ и evidence span включённого элемента — объединение версий совпавших аннотаторов."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/annotation_main.yaml")
    parser.add_argument("--annotations", default="data/golden_set/drafts/annotations.jsonl")
    parser.add_argument("--out", default="data/golden_set/drafts/annotations_final.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
