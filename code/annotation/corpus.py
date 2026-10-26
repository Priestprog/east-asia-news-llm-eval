r"""Доступ к корпусу $D$: PostgreSQL ``webmedia`` и коллекция Qdrant промышленной системы.

Подключение только на чтение. Адреса и учётные данные — переменные ``WEBMEDIA_*`` и ``QDRANT_*``
(см. ``code/README.md``); они загружаются функцией :func:`code.load_env`, в том числе из файла
``CORPUS_ENV_FILE``. Значения переменных не печатаются и не записываются в результаты.

Идентификатор точки Qdrant кодирует документ и номер фрагмента:
$\text{point\_id} = \text{webpage\_id} \ll 16 \mid \text{chunk}$, поэтому
$\text{webpage\_id} = \text{point\_id} \gg 16$ (``docs/systems.md``).
"""

from __future__ import annotations

import os
from typing import Iterable, Iterator, Sequence

from code import load_env

DEFAULT_COLLECTION = "webmedia_sentence_transformers_distiluse_base_multilingual_cased_v2"
CHUNK_BITS = 16


def webpage_id_of(point_id: int) -> int:
    return point_id >> CHUNK_BITS


def point_id_of(webpage_id: int, chunk: int) -> int:
    return (webpage_id << CHUNK_BITS) | chunk


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"не задана переменная окружения {name} (см. code/README.md)")
    return value


def connect_webmedia():
    """Соединение с базой ``webmedia`` в режиме только чтения."""
    import psycopg

    load_env()
    conn = psycopg.connect(
        host=_require("WEBMEDIA_POSTGRES_HOST"),
        port=int(_require("WEBMEDIA_POSTGRES_PORT")),
        dbname=_require("WEBMEDIA_CC_NEWS_DB_NAME"),
        user=_require("WEBMEDIA_CC_NEWS_USER"),
        password=_require("WEBMEDIA_CC_NEWS_USER_PASSWORD"),
        connect_timeout=20,
    )
    conn.read_only = True
    return conn


def connect_qdrant(timeout: int = 120):
    """Клиент Qdrant и имя коллекции корпуса."""
    from qdrant_client import QdrantClient

    load_env()
    client = QdrantClient(
        host=_require("QDRANT_HOST"),
        port=int(_require("QDRANT_PORT")),
        timeout=timeout,
        prefer_grpc=False,
        https=False,
    )
    collection = os.environ.get("QDRANT_COLLECTION") or DEFAULT_COLLECTION
    return client, collection


def batched(items: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def indexed_webpages(client, collection: str, webpage_ids: Iterable[int], chunks: int = 4) -> set[int]:
    """Документы, у которых в коллекции есть хотя бы один из первых ``chunks`` фрагментов."""
    ids = sorted(set(webpage_ids))
    found: set[int] = set()
    for batch in batched(ids, max(1, 2048 // chunks)):
        points = client.retrieve(
            collection_name=collection,
            ids=[point_id_of(w, k) for w in batch for k in range(chunks)],
            with_payload=False,
            with_vectors=False,
        )
        found.update(webpage_id_of(int(p.id)) for p in points)
    return found


def fetch_pages(conn, webpage_ids: Iterable[int], columns: Sequence[str]) -> dict[int, dict]:
    """Строки ``webmedia.webpages`` по идентификаторам: ``{id: {column: value}}``."""
    cols = ", ".join(["id", *[c for c in columns if c != "id"]])
    ids = sorted(set(webpage_ids))
    rows: dict[int, dict] = {}
    with conn.cursor() as cur:
        for batch in batched(ids, 20000):
            cur.execute(f"SELECT {cols} FROM webmedia.webpages WHERE id = ANY(%s)", (list(batch),))
            names = [d.name for d in cur.description]
            for rec in cur.fetchall():
                row = dict(zip(names, rec))
                rows[int(row["id"])] = row
    return rows
