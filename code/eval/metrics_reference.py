r"""Метрики по эталону (определены на $G^+$).

Для записи $G_i = (q_i, A^*_i, S^*_i, \mu_i)$ с каноническим ответом и алиасами $A^*_i$
и ответа $\hat a$:

* $\mathrm{EM} = \max_{a \in A^*_i} \mathbb{1}[\mathrm{norm}(\hat a) = \mathrm{norm}(a)]$;
* токенный F1 после лемматизации, максимум по алиасам;
* BERTScore-F1 с мультиязычным энкодером, максимум по алиасам;
* косинусная близость эмбеддингов (``sentence-transformers``), максимум по алиасам.

Правило NA: на $G^{\varnothing}$ метрики по эталону не определены (``None``).
Отказ $\hat a = \varnothing$ на $G^+$ — неверный ответ, метрика равна 0 (отказы на $G^+$
учитываются отдельно через $\mathrm{FAR}$). Транслитерация имён ломает EM и F1, поэтому
алиасы обязательны, а BERTScore и косинус даются как мягкие метрики.
"""

from __future__ import annotations

from typing import Sequence


def normalize(text: str) -> str:
    r"""$\mathrm{norm}(\cdot)$: нижний регистр, ``ё → е``, удаление пунктуации и кавычек,
    схлопывание пробелов, снятие внешних артиклей и служебных слов («год», «г.»)."""
    raise NotImplementedError("реализация — часть работы")


def lemmatize_tokens(text: str) -> list[str]:
    """Токены ``normalize(text)``, приведённые к леммам ``pymorphy3`` (для русского);
    латиница, цифры и китайские иероглифы остаются как есть."""
    raise NotImplementedError("реализация — часть работы")


def exact_match(answer: str | None, aliases: Sequence[str]) -> float | None:
    r"""$\mathrm{EM} = \max_{a \in A^*_i} \mathbb{1}[\mathrm{norm}(\hat a) = \mathrm{norm}(a)]$.

    Возвращает 0 при отказе, ``None`` при пустом ``aliases`` (запись из $G^{\varnothing}$).
    """
    raise NotImplementedError("реализация — часть работы")


def token_f1(answer: str | None, aliases: Sequence[str]) -> float | None:
    r"""Токенный F1 по леммам, максимум по алиасам.

    $P = |T(\hat a) \cap T(a)| / |T(\hat a)|$, $R = |T(\hat a) \cap T(a)| / |T(a)|$,
    $\mathrm{F1} = 2PR / (P + R)$ по мультимножествам лемм ($\cap$ — пересечение мультимножеств);
    $\mathrm{F1} = \max_{a \in A^*_i}$. 0 при отказе или пустом пересечении; ``None`` на $G^{\varnothing}$.
    """
    raise NotImplementedError("реализация — часть работы")


def bertscore_f1(
    answers: Sequence[str | None],
    aliases: Sequence[Sequence[str]],
    model_type: str = "bert-base-multilingual-cased",
    batch_size: int = 32,
) -> list[float | None]:
    r"""BERTScore-F1 (Zhang et al., 2020) по паре (ответ, алиас), максимум по алиасам; батчевая версия.

    Используется мультиязычный энкодер (русский ответ может содержать китайские имена в оригинале).
    Без бейзлайн-масштабирования, чтобы значение оставалось в $[0, 1]$. 0 при отказе;
    ``None`` на $G^{\varnothing}$. Версия модели фиксируется в ``meta.json``.
    """
    raise NotImplementedError("реализация — часть работы")


def cosine_similarity(answer: str | None, aliases: Sequence[str], encoder) -> float | None:
    r"""$\max_{a \in A^*_i} \cos(e(\hat a), e(a))$, $e$ — энкодер ``sentence-transformers``
    (в проде — ``distiluse-base-multilingual-cased-v2``, 512).

    Значение обрезается к $[0, 1]$. 0 при отказе; ``None`` на $G^{\varnothing}$.
    Совпадает по смыслу с ``semantic_similarity`` прод-репозитория и включена как
    кандидатная метрика, подлежащая валидации.
    """
    raise NotImplementedError("реализация — часть работы")
