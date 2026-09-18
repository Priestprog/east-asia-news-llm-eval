r"""Открытые модели провайдера ИВ РАН через OpenAI-совместимый API (``kind: openai_compat``).

Два режима по полю ``retriever``:

* ``none`` — $f_0^{(m)} = (g_m(q), \varnothing)$: «закрытая книга», модель отвечает
  из собственных знаний; $\hat S = \varnothing$, ``retrieved_ids = []``;
* ``cached_prod`` — $f_\rho^{(m)} = g_m \circ \rho_{\mathrm{prod}}$: в промпт подаётся
  та же выдача ретривера прода из ``RetrieverCache`` (контексты с номерами ``(N)``),
  что изолирует вклад модели от вклада ретривера.

Провайдер (llama-swap) тихо подменяет неизвестную модель, поэтому перед прогоном
снимается ``/v1/models`` и проверяется наличие ``model_id``; поле ``model`` каждого
ответа сверяется с запрошенным (fail-fast).
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import System, SystemOutput
from .retriever_cache import RetrievedContext, RetrieverCache


class OpenAICompatSystem(System):
    r"""$f_0^{(m)}$ или $f_\rho^{(m)}$ в зависимости от ``retriever``."""

    kind = "openai_compat"

    def __init__(self, config: Mapping[str, Any], retriever_cache: RetrieverCache | None = None) -> None:
        super().__init__(config)
        self.model_id: str = str(config["model_id"])
        self.retriever_cache = retriever_cache
        if config.get("retriever") == "cached_prod" and retriever_cache is None:
            raise ValueError(f"{self.system_id}: retriever=cached_prod требует RetrieverCache")

    def client(self):
        """Ленивое создание клиента ``openai.OpenAI(base_url, api_key)``."""
        raise NotImplementedError("реализация — часть работы")

    def list_models(self) -> list[str]:
        """Снимок ``/v1/models`` провайдера (сохраняется в ``meta.json`` прогона)."""
        raise NotImplementedError("реализация — часть работы")

    def assert_model_available(self) -> None:
        """Fail-fast до прогона: ``model_id`` должен присутствовать в снимке ``/v1/models``."""
        raise NotImplementedError("реализация — часть работы")

    def build_messages(self, question: str, contexts: list[RetrievedContext] | None) -> list[dict]:
        r"""Собирает сообщения чата по ``prompt_version``.

        Для $f_0^{(m)}$ — системный промпт без контекста; для $f_\rho^{(m)}$ — контексты
        с нумерацией ``(N)`` и инструкция цитировать номера. В обоих режимах при
        ``abstention_instruction`` разрешён ответ «Я не знаю.».
        """
        raise NotImplementedError("реализация — часть работы")

    def answer(self, question: str, question_id: str | None = None) -> SystemOutput:
        r"""Вычисляет $g_m(q)$ (или $g_m(q, \rho_{\mathrm{prod}}(q))$) при ``temperature = 0`` и фиксированном ``seed``.

        Цитаты ``(N)`` переводятся в ``webpage_id`` по номерам контекстов кэша; для
        ``retriever: none`` возвращается $\hat S = \varnothing$.
        """
        raise NotImplementedError("реализация — часть работы")
