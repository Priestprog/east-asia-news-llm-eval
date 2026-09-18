r"""Отчётные таблицы результатов.

* ``results/tables/main_table_long.csv`` — длинный формат, по строке на (система, метрика):
  ``system_id, model_id_reported, quantization, retriever, k, prompt_version, temperature, n_samples,
  metric, n, mean, ci_low, ci_high, delta_vs_prod, p_wilcoxon, p_holm, run_id, git_sha, date``;
* ``results/tables/main_table.md`` — широкий формат: строки — системы $f \in \mathcal{H}_{\mathrm{eval}}$,
  столбцы — метрики $m_k \in M'$ в виде ``mean [lo; hi]``, звёздочка при $p_{\mathrm{Holm}} < 0.05$
  (относительно $f_{\mathrm{prod}}$), последние столбцы — $Q(f)$ и ранг;
* ``results/tables/validation.csv`` — результат ``validate_metrics`` (пишется там).

Интервалы для $\bar m_k(f)$ — бутстреп по вопросам ($B$ и seed из ``eval.yaml``).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping, Sequence

LONG_COLUMNS: tuple[str, ...] = (
    "system_id", "model_id_reported", "quantization", "retriever", "k", "prompt_version", "temperature",
    "n_samples", "metric", "n", "mean", "ci_low", "ci_high", "delta_vs_prod", "p_wilcoxon", "p_holm",
    "run_id", "git_sha", "date",
)
"""Схема ``main_table_long.csv`` (совпадает с постановкой задачи)."""


def collect_runs(runs_dir: str | Path, run_ids: Sequence[str] | None = None) -> list[dict]:
    """Читает ``meta.json``, ``generations.jsonl`` и ``judge.jsonl`` выбранных прогонов."""
    raise NotImplementedError("реализация — часть работы")


def per_question_metrics(runs: Sequence[dict], golden_set: Sequence[dict], eval_config: Mapping) -> dict:
    r"""Вычисляет $m_k(f(q_i); G_i)$ для всех $f$, $m_k \in M$ по модулям из ``eval.yaml`` →
    ``{system_id: {metric: {question_id: value | None}}}``."""
    raise NotImplementedError("реализация — часть работы")


def build_long_table(per_question: Mapping, runs: Sequence[dict], validated: Sequence[str], eval_config: Mapping):
    """Длинная таблица (``pandas.DataFrame`` со столбцами ``LONG_COLUMNS``) с интервалами и статистикой
    относительно $f_{\\mathrm{prod}}$ (``code.eval.stats.compare_to_prod``)."""
    raise NotImplementedError("реализация — часть работы")


def build_wide_table(long_table, weights: Mapping[str, float] | None = None):
    r"""Широкая таблица: ``mean [lo; hi]`` со звёздочкой при $p_{\mathrm{Holm}} < 0.05$, $Q(f)$, ранг."""
    raise NotImplementedError("реализация — часть работы")


def render_markdown(wide_table, path: str | Path) -> None:
    """Запись ``main_table.md`` (GitHub-Markdown) с подписью: split, $n$, $B$, дата, git sha."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--runs", nargs="*")
    parser.add_argument("--out-dir", default="results/tables")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
