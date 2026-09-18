r"""Базовые типы оцениваемых систем.

Класс гипотез $\mathcal{H} = \{f : \mathcal{Q} \to \mathcal{A} \times 2^{\mathcal{I}}\}$,
$f(q) = (\hat a, \hat S)$, где $\mathcal{Q}$ — вопросы на русском языке,
$\mathcal{A} = \mathcal{A}^+ \sqcup \{\varnothing\}$ ($\varnothing$ — отказ «Я не знаю.»),
$\mathcal{I}$ — множество стабильных идентификаторов документов корпуса (``webpage_id``).

Любая система, независимо от внутреннего устройства (с поиском или без), возвращает
``SystemOutput``: ответ $\hat a$ (``None`` при отказе), множество процитированных
идентификаторов $\hat S$, сырой ответ провайдера и фактически отработавшую модель
(поле ``model`` ответа) — последнее обязательно из-за тихой подмены моделей
провайдером llama-swap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

ABSTENTION_MARKER = "Я не знаю."
"""Каноническая форма отказа $\\varnothing$ в ответах промышленной системы."""


class UnknownModelError(RuntimeError):
    """Фактическая модель ответа не совпала с запрошенной (fail-fast по постановке)."""


@dataclass
class SystemOutput:
    r"""Выход системы $f(q) = (\hat a, \hat S)$ плюс служебные поля.

    Attributes:
        answer: текст ответа $\hat a \in \mathcal{A}^+$ или ``None`` при отказе $\hat a = \varnothing$.
        cited_ids: $\hat S \subset \mathcal{I}$ — идентификаторы ``webpage_id`` процитированных
            документов (инлайн-цитаты ``(N)`` переведены через ``source_map`` → URL → ``webpage_id``).
            Для систем без поиска $\hat S = \varnothing$.
        raw: сырой ответ провайдера или API прода (для воспроизводимости и разбора инцидентов).
        model_reported: значение поля ``model`` в ответе провайдера — фактически отработавшая модель.
        retrieved_ids: ранжированный список идентификаторов, выданных компонентом $\rho$
            (нужен для Hit@k, Recall@k, MRR, nDCG@k); пустой список для $f_0^{(m)}$.
        latency_s: время ответа в секундах.
    """

    answer: str | None
    cited_ids: set[int] = field(default_factory=set)
    raw: dict = field(default_factory=dict)
    model_reported: str = ""
    retrieved_ids: list[int] = field(default_factory=list)
    latency_s: float | None = None

    @property
    def is_abstention(self) -> bool:
        r"""Истина, если $\hat a = \varnothing$."""
        return self.answer is None

    def to_record(self) -> dict:
        """Сериализуемое представление для ``generations.jsonl`` (множества → отсортированные списки)."""
        return {
            "answer": self.answer,
            "cited_ids": sorted(self.cited_ids),
            "model_reported": self.model_reported,
            "retrieved_ids": list(self.retrieved_ids),
            "latency_s": self.latency_s,
            "raw": self.raw,
        }


class System(ABC):
    r"""Абстрактная оцениваемая система $f \in \mathcal{H}$.

    Конкретные реализации: ``ProdApiSystem`` ($f_{\mathrm{prod}}$) и ``OpenAICompatSystem``
    ($f_0^{(m)}$ при ``retriever: none``, $f_\rho^{(m)}$ при ``retriever: cached_prod``).
    """

    kind: str = "abstract"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config: dict = dict(config)
        self.system_id: str = str(config["system_id"])

    @abstractmethod
    def answer(self, question: str, question_id: str | None = None) -> SystemOutput:
        r"""Вычисляет $f(q) = (\hat a, \hat S)$ для вопроса $q$.

        Args:
            question: текст вопроса $q \in \mathcal{Q}$ (русский).
            question_id: идентификатор записи Golden Set — ключ кэша ретривера для $f_\rho^{(m)}$.

        Raises:
            UnknownModelError: если ``fail_fast_on_unknown_model`` и модель ответа не совпала с запрошенной.
        """

    def describe(self) -> dict:
        """Паспорт системы для ``meta.json``: параметры, влияющие на воспроизводимость."""
        keys = (
            "system_id", "kind", "retriever", "model_id", "quantization", "k", "m", "threshold",
            "deep_search", "num_docs", "temperature", "max_tokens", "seed", "prompt_version",
        )
        return {key: self.config.get(key) for key in keys if key in self.config or key == "kind"} | {
            "kind": self.kind,
        }

    def check_model(self, model_reported: str, expected: str | None) -> None:
        """Fail-fast: сравнивает фактическую модель ответа с ожидаемой.

        Raises:
            UnknownModelError: при несовпадении и включённом ``fail_fast_on_unknown_model``.
        """
        if not self.config.get("fail_fast_on_unknown_model", True) or expected is None:
            return
        if model_reported != expected:
            raise UnknownModelError(
                f"{self.system_id}: ожидалась модель {expected!r}, ответ пришёл от {model_reported!r}"
            )
