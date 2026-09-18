r"""Валидация метрик по согласию с разметчиками и отбор $M'$.

Человеческие оценки $h^{(r)}_{i,f} \in \{0, \dots, 5\}$ (правильность, обоснованность) даны на
$G_h \subset G^+$, $|G_h| = n_h$, для систем $\mathcal{H}_h \subset \mathcal{H}_{\mathrm{eval}}$;
$\bar h_{i,f}$ — среднее по разметчикам $r$.

$M' = \{m_k \in M : \rho_S(m_k, \bar h) \ge \rho_{\min} \text{ на } G_h \times \mathcal{H}_h\}$,
$\rho_{\min} = 0.5$; $\rho_S$ — коэффициент Спирмена с 95%-м бутстреп-интервалом по парам
$(i, f)$. Потолок — среднее попарное согласие людей $\rho_S(h^{(r)}, h^{(r')})$.
Детерминированные метрики без человеческого аналога (Recall@k, MRR, nDCG@k, AR, $1-\mathrm{FAR}$,
$\mathrm{CP}_{\mathrm{id}}$, $\mathrm{CR}_{\mathrm{id}}$) включаются в $M'$ напрямую.

Гипотезы: $H_4$: $\rho_S(m_J^{\mathrm{corr}}, \bar h) \ge 0.5$ и $\alpha_{\mathrm{human}} \ge 0.67$;
$H_5$: самопредпочтение судьи незначимо.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class SpearmanResult:
    r"""$\rho_S$ с бутстреп-интервалом; ``n`` — число пар $(i, f)$ после удаления NA."""

    metric: str
    rho: float
    ci_low: float
    ci_high: float
    n: int
    passed: bool     # rho >= rho_min


def spearman_with_ci(
    metric_values: Sequence[float | None],
    human_means: Sequence[float],
    B: int = 10000,
    alpha: float = 0.05,
    seed: int = 20260917,
    rho_min: float = 0.5,
    metric: str = "",
) -> SpearmanResult:
    r"""$\rho_S(m_k, \bar h)$ по парам $(i, f)$ с перцентильным $(1 - \alpha)$-интервалом
    из $B$ бутстреп-повторов по парам; пары с $m_k = \mathrm{NA}$ исключаются.

    ``passed`` — $\rho_S \ge \rho_{\min}$ по точечной оценке; нижняя граница интервала
    приводится в таблице ``validation.csv`` как консервативная проверка.
    """
    raise NotImplementedError("реализация — часть работы")


def human_agreement_ceiling(human_scores: Mapping[str, Sequence[float | None]]) -> float:
    r"""Среднее попарное $\rho_S(h^{(r)}, h^{(r')})$ по разметчикам — верхняя граница для $\rho_S(m_k, \bar h)$."""
    raise NotImplementedError("реализация — часть работы")


def select_validated_metrics(
    results: Mapping[str, SpearmanResult],
    rho_min: float = 0.5,
    direct_include: Sequence[str] = (),
) -> list[str]:
    r"""$M' = \{m_k : \rho_S(m_k, \bar h) \ge \rho_{\min}\} \cup \{\text{метрики без человеческого аналога}\}$.

    ``direct_include`` — идентификаторы метрик с ``human_analog: false`` из ``eval.yaml``.
    Порядок — как в ``eval.yaml``. Если первичная метрика ``judge_correctness`` не прошла,
    первичной становится ``fallback_metric`` (решение записывается в ``validation.csv``).
    """
    raise NotImplementedError("реализация — часть работы")


def self_preference_test(
    judge_scores_own: Sequence[float],
    judge_scores_other: Sequence[float],
    human_means_own: Sequence[float],
    human_means_other: Sequence[float],
) -> dict:
    r"""$H_5$: разность «судья − человек» на ответах, порождённых моделью-судьёй (или её семейством),
    против остальных систем; критерий Манна — Уитни и размер эффекта Cliff's $\delta$.
    Возвращает ``{"delta_own", "delta_other", "p_value", "cliffs_delta", "significant"}``."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--out", default="results/tables/validation.csv")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
