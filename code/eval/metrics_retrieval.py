r"""Метрики компонента $\rho_{\mathrm{prod}}$ (поиск) относительно $S^*_i$.

Вход — ранжированный список идентификаторов ``ranked_ids`` $= (\iota_1, \iota_2, \dots)$,
выданный ретривером (для $f_{\mathrm{prod}}$ — из ответа API, для $f_\rho^{(\ell)}$ — из кэша,
совпадает с $f_{\mathrm{prod}}$), и эталон $S^*_i \subset \mathcal{I}$, $|S^*_i| \ge 1$.
Релевантность бинарная: $\mathrm{rel}_j = \mathbb{I}[\iota_j \in S^*_i]$.

Правило NA: для систем без поиска ($f_0^{(\ell)}$, ``ranked_ids`` пуст по конструкции)
и для записей $G^{\bot}$ ($S^*_i = \varnothing$) метрики равны ``None``.
Пустая выдача ретривера при $S^*_i \ne \varnothing$ — 0, а не NA.
Идентификаторы в списке — на уровне документа (``webpage_id``); фрагменты одного документа
схлопываются с сохранением лучшей позиции.
"""

from __future__ import annotations

from typing import Sequence


def hit_at_k(ranked_ids: Sequence[int] | None, relevant_ids: set[int], k: int) -> float | None:
    r"""$\mathrm{Hit@}k = \mathbb{I}\left[\exists\, j \le k : \iota_j \in S^*_i\right]$."""
    raise NotImplementedError("реализация — часть работы")


def recall_at_k(ranked_ids: Sequence[int] | None, relevant_ids: set[int], k: int) -> float | None:
    r"""$\mathrm{Recall@}k = |\{\iota_1, \dots, \iota_k\} \cap S^*_i| / |S^*_i|$."""
    raise NotImplementedError("реализация — часть работы")


def mrr(ranked_ids: Sequence[int] | None, relevant_ids: set[int]) -> float | None:
    r"""$\mathrm{MRR} = 1 / \min\{j : \iota_j \in S^*_i\}$; 0, если релевантных документов в выдаче нет."""
    raise NotImplementedError("реализация — часть работы")


def ndcg_at_k(ranked_ids: Sequence[int] | None, relevant_ids: set[int], k: int) -> float | None:
    r"""$\mathrm{nDCG@}k = \mathrm{DCG@}k / \mathrm{IDCG@}k$,
    $\mathrm{DCG@}k = \sum_{j=1}^{k} \frac{\mathrm{rel}_j}{\log_2(j + 1)}$,
    $\mathrm{IDCG@}k = \sum_{j=1}^{\min(k, |S^*_i|)} \frac{1}{\log_2(j + 1)}$."""
    raise NotImplementedError("реализация — часть работы")
