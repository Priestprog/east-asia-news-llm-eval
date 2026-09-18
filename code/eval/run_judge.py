r"""Оценка генераций судьёй-LLM.

Вход — ``results/runs/<run_id>/generations.jsonl`` и Golden Set; выход —
``results/runs/<run_id>/judge.jsonl``: по строке на вопрос с полями ``question_id, system_id,
scores{<dimension>: 0..5 | null}, rationales, extra, judge_model_reported, judge_prompt_version, raw``.
В ``meta.json`` прогона добавляется блок ``judge`` (модель, версия промпта, снимок моделей,
отчёт о воспроизводимости).

Измерения, требующие эталона, пропускаются на $G^{\varnothing}$; измерения, требующие
контекстов, — для систем без цитат (``None`` = NA). Перед прогоном проверяется ограничение
судья $\notin \mathcal{L} \cup \{g_{\theta_{\mathrm{prod}}}\}$.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

JUDGE_FIELDS: tuple[str, ...] = (
    "question_id", "system_id", "scores", "rationales", "extra",
    "judge_model_reported", "judge_prompt_version", "raw",
)


def load_generations(run_dir: str | Path) -> list[dict]:
    """Читает ``generations.jsonl`` прогона."""
    raise NotImplementedError("реализация — часть работы")


def contexts_for(record: dict, cache) -> list[dict]:
    r"""Процитированные документы $\hat S$ с текстами (из кэша ретривера или снимка корпуса) для промпта судьи."""
    raise NotImplementedError("реализация — часть работы")


def run(run_id: str, judge_config_path: str, eval_config_path: str, resume: bool = False) -> Path:
    """Цикл по генерациям → ``Judge.score`` → ``judge.jsonl``; обновление ``meta.json``."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--judge-config", default="code/configs/judge.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
