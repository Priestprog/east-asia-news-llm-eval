r"""Листы разметки и их обратный импорт.

Два вида листов:

1. **Разметка Golden Set** ($R = 3$ независимых разметчика, не менее одного читающего
   по-китайски). По каждому черновику разметчик $r$ проставляет: $z_r(q) \in \{0, 1\}$ —
   инвариантность во времени после проверки правил $E_1$–$E_5$; отвечаемость по корпусу;
   тип вопроса; исправленный канонический ответ и алиасы; подтверждение evidence-span.
   Листы обезличены и перемешаны (фиксированный seed), черновая метка модели скрыта.
2. **Человеческая валидация** $h^{(r)}_{i,f} \in \{0, \dots, 5\}$ (правильность, обоснованность)
   для ответов систем $\mathcal{H}_h \subset \mathcal{H}_{\mathrm{eval}}$ на $G_h \subset G^+$;
   разметчик не видит, какая система дала ответ.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

ANNOTATION_COLUMNS: tuple[str, ...] = (
    "draft_id", "question_ru", "anchor_date", "evidence_span_ru", "evidence_span_zh", "supporting_uris",
    "time_invariant",            # z_r(q): 1 — инвариантен, 0 — нет
    "exclusion_rule",            # E1..E5 или пусто
    "answerable",                # 1 — подтверждается корпусом, 0 — кандидат в G∅
    "question_type",
    "answer_canonical_fixed", "answer_aliases_fixed",
    "evidence_confirmed",        # 1/0
    "difficulty",                # 1..3
    "comment",
)
"""Столбцы листа разметки Golden Set."""

HUMAN_VALIDATION_COLUMNS: tuple[str, ...] = (
    "item_id", "question_ru", "answer_canonical", "system_answer_blind",
    "correctness_0_5",           # правильность относительно A*_i
    "groundedness_0_5",          # обоснованность процитированными источниками
    "comment",
)
"""Столбцы листа человеческой валидации (система скрыта, порядок перемешан)."""


def export_for_annotators(drafts_path: str, out_dir: str, R: int = 3, seed: int = 20260917) -> list[Path]:
    """Создаёт ``R`` обезличенных листов (CSV) с одинаковым набором черновиков в разном порядке."""
    raise NotImplementedError("реализация — часть работы")


def export_human_validation_sheets(
    generations: Sequence[dict], golden_subset: Sequence[dict], out_dir: str, R: int = 3, seed: int = 20260917
) -> list[Path]:
    r"""Листы для $h^{(r)}_{i,f}$: пары (вопрос, ответ системы) без указания системы, перемешанные."""
    raise NotImplementedError("реализация — часть работы")


def import_annotations(sheets_dir: str) -> list[dict]:
    """Читает заполненные листы, проверяет полноту столбцов и допустимость значений,
    возвращает записи вида ``{"draft_id", "annotator", <поля листа>}``."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--drafts", default="data/golden_set/v0.1-pilot/drafts.jsonl")
    parser.add_argument("--out-dir", default="data/golden_set/v0.1-pilot/sheets")
    parser.add_argument("--annotators", type=int, default=3, help="R — число разметчиков")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
