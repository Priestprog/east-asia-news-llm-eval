r"""Обёртки оцениваемых систем $\mathcal{H}_{\mathrm{eval}}$.

$\mathcal{H}_{\mathrm{eval}} = \{f_{\mathrm{prod}}\} \cup \{f_0^{(m)}\}_{m \in \mathcal{L}}
\cup \{f_\rho^{(m)}\}_{m \in \mathcal{L}}$:

* ``prod_api.ProdApiSystem`` — $f_{\mathrm{prod}} = g_{\theta_{\mathrm{prod}}} \circ \rho_{\mathrm{prod}}$
  (Qdrant + SearchAPI + генератор), вызывается через HTTP API промышленной системы;
* ``openai_compat.OpenAICompatSystem`` с ``retriever: none`` — $f_0^{(m)} = (g_m(q), \varnothing)$,
  открытая модель провайдера ИВ РАН без поиска;
* ``openai_compat.OpenAICompatSystem`` с ``retriever: cached_prod`` — $f_\rho^{(m)} = g_m \circ \rho_{\mathrm{prod}}$,
  та же выдача ретривера прода из ``retriever_cache.RetrieverCache`` с другой моделью
  (абляция «модель против ретривера»).
"""

from __future__ import annotations

from pathlib import Path

from .base import ABSTENTION_MARKER, System, SystemOutput

__all__ = ["ABSTENTION_MARKER", "System", "SystemOutput", "load_system"]


def load_system(config_path: str | Path) -> System:
    """Создаёт систему по YAML-конфигурации из ``code/configs/systems``.

    Диспетчеризация по полю ``kind``: ``prod_api`` → ``ProdApiSystem``,
    ``openai_compat`` → ``OpenAICompatSystem``. Для ``retriever: cached_prod``
    подключается ``RetrieverCache`` по пути ``retriever_cache``.
    """
    from .. import load_config
    from .openai_compat import OpenAICompatSystem
    from .prod_api import ProdApiSystem
    from .retriever_cache import RetrieverCache

    config = load_config(config_path)
    kind = config.get("kind")
    if kind == "prod_api":
        return ProdApiSystem(config)
    if kind == "openai_compat":
        cache = None
        if config.get("retriever") == "cached_prod":
            cache = RetrieverCache(config["retriever_cache"])
        return OpenAICompatSystem(config, retriever_cache=cache)
    raise ValueError(f"Неизвестный kind системы: {kind!r} ({config_path})")
