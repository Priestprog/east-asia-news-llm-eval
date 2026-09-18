r"""Метрики отказа.

$G^{\varnothing}$ — вопросы, инвариантные по форме, но не подтверждаемые корпусом; правильный
ответ на них — отказ $\varnothing$ («Я не знаю.»). $G^+$ — отвечаемые вопросы, отказ на них — ошибка.

* $\mathrm{AR} = \frac{1}{n_\varnothing} \sum_{G^{\varnothing}} \mathbb{1}[\hat a = \varnothing]$ —
  доля корректных отказов; «больше — лучше»;
* $\mathrm{FAR} = \frac{1}{n_+} \sum_{G^+} \mathbb{1}[\hat a = \varnothing]$ — доля ложных отказов;
  в таблицу результатов входит $1 - \mathrm{FAR}$, чтобы все метрики были «больше — лучше».

Обе метрики — агрегаты по системе, а не по отдельному вопросу, поэтому для них
$I_k(f)$ — вся соответствующая часть выборки; $\mathrm{NA}$, если она пуста.
Признак отказа определяется ``code.systems.prod_api.detect_abstention`` единообразно для всех систем.
"""

from __future__ import annotations

from typing import Sequence


def abstention_indicator(answers: Sequence[str | None]) -> list[int]:
    r"""Вектор $\mathbb{1}[\hat a_i = \varnothing]$ по ответам (``None`` или маркер «Я не знаю.»)."""
    raise NotImplementedError("реализация — часть работы")


def abstention_rate(answers_on_unanswerable: Sequence[str | None]) -> float | None:
    r"""$\mathrm{AR} = \frac{1}{n_\varnothing} \sum_{i \in G^{\varnothing}} \mathbb{1}[\hat a_i = \varnothing]$;
    ``None`` при $n_\varnothing = 0$."""
    raise NotImplementedError("реализация — часть работы")


def false_abstention_rate(answers_on_answerable: Sequence[str | None]) -> float | None:
    r"""$\mathrm{FAR} = \frac{1}{n_+} \sum_{i \in G^+} \mathbb{1}[\hat a_i = \varnothing]$; ``None`` при $n_+ = 0$.

    В таблицу и композит $Q(f)$ входит $1 - \mathrm{FAR}$ (идентификатор метрики ``one_minus_far``).
    """
    raise NotImplementedError("реализация — часть работы")
