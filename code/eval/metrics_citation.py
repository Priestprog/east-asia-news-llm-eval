r"""Метрики цитирования (ALCE, Gao et al., 2023; адаптация к идентификаторам корпуса).

Для ответа $(\hat a, \hat S)$ и эталона $S^*_i \subset \mathcal{I}$:

* $\mathrm{CP}_{\mathrm{id}} = |\hat S \cap S^*_i| / |\hat S|$ — точность цитирования по идентификаторам;
  $\mathrm{NA}$ при $\hat S = \varnothing$;
* $\mathrm{CR}_{\mathrm{id}} = |\hat S \cap S^*_i| / |S^*_i|$ — полнота; для закрытой книги
  ($\hat S = \varnothing$) равна 0; $\mathrm{NA}$ при $S^*_i = \varnothing$ ($G^{\varnothing}$);
* $\mathrm{CP}_{\mathrm{ent}} = \frac{1}{|\hat S|} \sum_{\iota \in \hat S} \mathbb{1}[x_\iota \models \hat a]$ —
  точность по следованию (NLI или судья): процитированный документ действительно влечёт ответ.
  Нужна, потому что $S^*_i$ может быть неполным в корпусе из 23,9 млн чанков: верная цитата
  на документ вне $S^*_i$ не должна штрафоваться. $\mathrm{NA}$ при $\hat S = \varnothing$
  или $\hat a = \varnothing$.

Цитаты с номером вне ``source_map`` (например, ``(22)`` при трёх источниках) в $\hat S$
не разрешаются и учитываются как ложные через ``n_unresolved``.
"""

from __future__ import annotations

from typing import Callable


def citation_precision_id(cited_ids: set[int], supporting_ids: set[int], n_unresolved: int = 0) -> float | None:
    r"""$\mathrm{CP}_{\mathrm{id}} = |\hat S \cap S^*_i| / (|\hat S| + n_{\text{unresolved}})$.

    Неразрешённые номера цитат входят в знаменатель как ложные ссылки.
    ``None``, если $|\hat S| + n_{\text{unresolved}} = 0$ (цитат нет).
    """
    raise NotImplementedError("реализация — часть работы")


def citation_recall_id(cited_ids: set[int], supporting_ids: set[int]) -> float | None:
    r"""$\mathrm{CR}_{\mathrm{id}} = |\hat S \cap S^*_i| / |S^*_i|$.

    0 при $\hat S = \varnothing$ (закрытая книга или ответ без цитат); ``None`` при
    $S^*_i = \varnothing$ (запись из $G^{\varnothing}$).
    """
    raise NotImplementedError("реализация — часть работы")


def citation_precision_entailment(
    answer: str | None,
    cited_ids: set[int],
    get_text: Callable[[int], str],
    entails: Callable[[str, str], bool],
) -> float | None:
    r"""$\mathrm{CP}_{\mathrm{ent}} = \frac{1}{|\hat S|} \sum_{\iota \in \hat S} \mathbb{1}[x_\iota \models \hat a]$.

    Args:
        answer: $\hat a$; при ``None`` (отказ) метрика не определена → ``None``.
        cited_ids: $\hat S$; при пустом множестве → ``None``.
        get_text: $\iota \mapsto x_\iota$ — текст документа (перевод) по ``webpage_id``.
        entails: предикат $x \models \hat a$ — NLI-модель или судья-LLM с бинарным выходом;
            выбор реализации фиксируется в ``meta.json``.
    """
    raise NotImplementedError("реализация — часть работы")
