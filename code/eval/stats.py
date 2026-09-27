r"""Агрегация, композит и статистика парных сравнений.

Для $f \in \mathcal{H}_{\mathrm{eval}}$, $m_k \in M'$:
$\bar m_k(f) = \frac{1}{|I_k(f)|} \sum_{i \in I_k(f)} m_k(f(q_i); G_i)$, $I_k(f) = \{i : m_k \ne \mathrm{NA}\}$;
композит $Q(f) = \sum_{m_k \in M'_Q} w_k \bar m_k(f)$, $w_k \ge 0$, $\sum_k w_k = 1$ (по умолчанию равные);
$f^\star = \arg\max_{f} Q(f) = \arg\min_{f} \sum_{m_k \in M'_Q} w_k (1 - \bar m_k(f))$ с проверкой значимости
парных различий.

Для пары $(f, f')$ по первичной метрике: $\delta_i = m_k(f(q_i)) - m_k(f'(q_i))$ на общих $i$
(оба значения не NA); парный бутстреп по вопросам ($B = 10^4$, перцентильный 95%-й интервал для
$\bar\delta$); двусторонний критерий Уилкоксона знаковых рангов (``zero_method='zsplit'``), для бинарных
метрик — точный критерий Мак-Немара; поправка Холма на уровне значимости ``significance_level`` = 0.05
в четырёх семьях: {первичная метрика, $Q(f)$} × {12 сравнений $f' \ne f_{\mathrm{prod}}$ ($H_1$, $H_2$);
6 пар $(f_\rho^{(\ell)}, f_0^{(\ell)})$ ($H_3$)}; размер эффекта — $\Delta_{\mathrm{C}}$ Клиффа.
$H_1$–$H_3$ принимаются при $p_{\mathrm{Holm}} < 0.05$ и $\bar\delta > 0$ (ADR-018). Буква $\alpha$
зарезервирована за коэффициентом Криппендорфа (ADR-013).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class BootstrapResult:
    mean_delta: float
    ci_low: float
    ci_high: float
    n: int
    B: int


@dataclass(frozen=True)
class WilcoxonResult:
    statistic: float
    p_value: float
    n: int            # число ненулевых разностей


def aggregate_metric(values: Sequence[float | None]) -> tuple[float | None, int]:
    r"""$\bar m_k(f)$ и $|I_k(f)|$: среднее по значениям, не равным NA; ``(None, 0)`` при пустом $I_k(f)$."""
    raise NotImplementedError("реализация — часть работы")


def composite_score(means: Mapping[str, float | None], weights: Mapping[str, float] | None = None) -> float:
    r"""$Q(f) = \sum_k w_k \bar m_k(f)$; ``weights=None`` — равные веса по метрикам с известным $\bar m_k$.

    Веса перенормируются на множество метрик, для которых $\bar m_k(f) \ne \mathrm{NA}$
    (например, retrieval-метрики у $f_0^{(\ell)}$), и факт перенормировки отмечается в таблице.
    """
    raise NotImplementedError("реализация — часть работы")


def paired_bootstrap_ci(
    x: Sequence[float], y: Sequence[float], B: int = 10000, significance_level: float = 0.05, seed: int = 20260917
) -> BootstrapResult:
    r"""Парный бутстреп по вопросам для $\bar\delta$, $\delta_i = x_i - y_i$.

    $B$ раз выбираются индексы $i$ с возвращением, считается $\bar\delta^{(b)}$;
    интервал — перцентили ``significance_level / 2`` и ``1 - significance_level / 2``. ``x`` и ``y`` уже выровнены по общим $i$.
    """
    raise NotImplementedError("реализация — часть работы")


def wilcoxon_signed_rank(x: Sequence[float], y: Sequence[float], alternative: str = "two-sided") -> WilcoxonResult:
    r"""Двусторонний критерий Уилкоксона знаковых рангов для $\delta_i = x_i - y_i$ (``scipy.stats.wilcoxon``,
    нулевые разности делятся между знаками — ``zero_method='zsplit'``). Направление эффекта для $H_1$–$H_3$
    проверяется знаком $\bar\delta$, а не односторонней альтернативой (ADR-018)."""
    raise NotImplementedError("реализация — часть работы")


def holm_correction(p_values: Sequence[float], significance_level: float = 0.05) -> list[float]:
    r"""Поправка Холма (step-down): для упорядоченных $p_{(1)} \le \dots \le p_{(m)}$
    $\tilde p_{(j)} = \max_{l \le j} \min\{1, (m - l + 1)\, p_{(l)}\}$; возвращает скорректированные
    $p$ в исходном порядке. Отклонение при $\tilde p \le$ ``significance_level``. Семьи поправки — четыре
    (см. докстринг модуля); функция применяется к каждой семье отдельно."""
    raise NotImplementedError("реализация — часть работы")


def cliffs_delta(x: Sequence[float], y: Sequence[float]) -> float:
    r"""$\Delta_{\mathrm{C}} = \frac{\#\{(i, j): x_i > y_j\} - \#\{(i, j): x_i < y_j\}}{|x| \cdot |y|} \in [-1, 1]$ — размер эффекта Клиффа;
    интерпретация $|\Delta_{\mathrm{C}}|$: $< 0.147$ пренебрежимый, $< 0.33$ малый, $< 0.474$ средний, иначе большой
    (Romano et al., 2006)."""
    raise NotImplementedError("реализация — часть работы")


def compare_to_prod(
    per_question: Mapping[str, Mapping[str, float | None]],
    metric: str,
    prod_id: str = "f_prod",
    B: int = 10000,
    significance_level: float = 0.05,
    holm: bool = True,
    seed: int = 20260917,
) -> list[dict]:
    r"""Семья $H_1$, $H_2$: для каждой $f' \ne f_{\mathrm{prod}}$ — $\bar\delta$ с интервалом, $p$ Уилкоксона
    (или Мак-Немара для бинарной метрики), $\tilde p$ Холма по 12 сравнениям, $\Delta_{\mathrm{C}}$ Клиффа,
    число общих вопросов — строки для ``main_table_long.csv``.

    ``per_question[system_id][question_id]`` — значение метрики (``None`` = NA).
    """
    raise NotImplementedError("реализация — часть работы")


def mcnemar_exact(x: Sequence[float], y: Sequence[float]) -> float:
    r"""Точный критерий Мак-Немара для бинарных метрик ($\mathrm{EM}$, $\mathrm{AR}$, $1 - \mathrm{FAR}$):
    $p$-значение по биномиальному распределению числа дискордантных пар $(1, 0)$ и $(0, 1)$;
    заменяет критерий Уилкоксона, который на разностях из $\{-1, 0, 1\}$ вырождается (ADR-018)."""
    raise NotImplementedError("реализация — часть работы")


def compare_retrieval_gain(
    per_question: Mapping[str, Mapping[str, float | None]],
    metric: str,
    pairs: Sequence[tuple[str, str]],
    B: int = 10000,
    significance_level: float = 0.05,
    holm: bool = True,
    seed: int = 20260917,
) -> list[dict]:
    r"""Семья $H_3$: для каждой пары $(f_\rho^{(\ell)}, f_0^{(\ell)})$, $\ell \in \mathcal{L}$ (6 сравнений), —
    те же величины, что в ``compare_to_prod``; поправка Холма применяется внутри этой семьи отдельно."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--runs", nargs="*", help="run_id прогонов; по умолчанию — все в results/runs/")
    parser.add_argument("--out", default="results/tables/stats.csv")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
