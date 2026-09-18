r"""Стратифицированный отбор документов корпуса для черновиков вопросов.

Источник: пересечение таблицы ``webmedia.webpages`` (PostgreSQL) и коллекции Qdrant —
так покрытие $S^*_i \subset \mathcal{I}$ ретривером равно 1 по построению.
Страты: домен × месяц публикации × категория. Объём — с переизбытком ×2 относительно
целевого $n$ (цель 200–300, минимум 150), чтобы после исключений $E_1$–$E_5$
и адъюдикации осталось достаточно вопросов.

Снимок $D_{t_0}$ фиксируется: дата $t_0$, $N$, хеш отсортированного списка $\mathcal{I}$.
Ограничения: ≥3 доменов, 2 регионов, охват ≥12 месяцев по $\tau_j \le t_0$.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DocumentRef:
    r"""Метаданные документа $d_j$ без текстов: $(\iota_j, u_j, \tau_j, s_j)$ плюс страты."""

    webpage_id: int
    urn_uuid: str | None
    uri: str
    published_at: str   # ISO-8601, $\tau_j \le t_0$
    source: str         # домен
    region: str         # КНР | Тайвань | Гонконг | Сингапур
    category: str | None


def connect_webmedia():
    """Подключение к PostgreSQL ``webmedia`` по переменным ``WEBMEDIA_*`` (см. code/README.md)."""
    raise NotImplementedError("реализация — часть работы")


def intersect_with_qdrant(conn, qdrant_client, collection: str) -> list[DocumentRef]:
    r"""Возвращает документы, у которых хотя бы один чанк присутствует в коллекции Qdrant.

    Даёт множество $\mathcal{I}$ снимка: только эти документы могут входить в $S^*_i$.
    """
    raise NotImplementedError("реализация — часть работы")


def snapshot_corpus(docs: Sequence[DocumentRef], t0: str) -> dict:
    r"""Паспорт снимка $D_{t_0}$: ``{"t0": ..., "N": ..., "ids_sha256": ..., "domains": ..., "months": ...}``.

    Хеш — sha256 от строки отсортированных ``webpage_id`` через перевод строки.
    """
    raise NotImplementedError("реализация — часть работы")


def stratified_sample(
    docs: Sequence[DocumentRef],
    n_target: int,
    oversample: float = 2.0,
    strata: Sequence[str] = ("source", "month", "category"),
    seed: int = 20260917,
) -> list[DocumentRef]:
    r"""Стратифицированный отбор $\lceil \text{oversample} \cdot n_{\text{target}} \rceil$ документов.

    Квота страты пропорциональна её объёму с нижней границей 1; внутри страты — равновероятный
    выбор с фиксированным ``seed``. Проверяются ограничения снимка (≥3 доменов, 2 регионов,
    ≥12 месяцев); при нарушении выбрасывается ``ValueError``.
    """
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml", help="путь к eval.yaml")
    parser.add_argument("--n-target", type=int, default=250, help="целевой объём n")
    parser.add_argument("--oversample", type=float, default=2.0)
    parser.add_argument("--out", default="data/seed_pool/sampled_documents.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
