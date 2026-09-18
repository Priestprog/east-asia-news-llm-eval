r"""Черновики записей Golden Set моделью $g_{\mathrm{draft}} \notin \mathcal{L}$.

По каждому отобранному документу (и по паре документов для ``requires_multi_doc``)
модель-черновик формирует кортеж $(q, a, S, \text{evidence}, \text{тип}, \text{дата-якорь})$:
вопрос на русском с явной датой-якорем, канонический ответ и алиасы, идентификаторы
подтверждающих документов $S \subset \mathcal{I}$, короткие evidence-span (ru и zh),
тип вопроса и предварительную метку инвариантности. Черновик — только заготовка для
разметчиков; в $G$ он попадает после независимой разметки и согласия.

Отдельно генерируются кандидаты в $G^{\varnothing}$ — вопросы, инвариантные по форме,
но не подтверждаемые корпусом ($n_\varnothing \approx 0.1\,n$; правильный ответ — отказ).

Старые 388 вопросов (``EN_rag_questions.json`` / ``RU_rag_questions.json`` прод-репозитория)
используются как seed pool после перекладки ``warc_id`` → ``webpage_id``; эталонных
ответов у них нет, поэтому они проходят тот же путь, что и новые черновики.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Sequence

from .sample_documents import DocumentRef


@dataclass
class Draft:
    """Черновик записи; поля соответствуют схеме ``data/golden_set/schema.json``."""

    draft_id: str
    question_ru: str
    answer_canonical: str | None          # None — кандидат в G∅
    answer_aliases: list[str] = field(default_factory=list)
    answer_type: str = "entity"           # entity | date | number | short_text | ...
    supporting_ids: list[int] = field(default_factory=list)   # S ⊂ I
    evidence_span_ru: str = ""
    evidence_span_zh: str = ""
    question_type: str = "factoid"
    category: str | None = None
    anchor_date: str | None = None        # дата-якорь в вопросе
    requires_multi_doc: bool = False
    answerable: bool = True               # False — кандидат в G∅
    draft_model: str = ""
    draft_prompt_id: str = "draft-v1"
    seed_pool_ref: str | None = None      # ссылка на запись seed pool, если черновик из неё


def load_seed_pool(questions_path: str, mapping_path: str) -> list[dict]:
    """Читает старые вопросы и mapping ``warc_id → webpage_id``; записи без соответствия отбрасываются
    с записью в отчёт (ключ ``warc_id`` lossy, покрытие корпуса ~67 %)."""
    raise NotImplementedError("реализация — часть работы")


def build_draft_prompt(doc_ru: str, doc_zh: str, meta: DocumentRef, prompt_id: str = "draft-v1") -> list[dict]:
    r"""Промпт модели-черновика: требования к статичности (правила $E_1$–$E_5$ в инструкции),
    обязательная дата-якорь, канонический ответ + алиасы, evidence-span."""
    raise NotImplementedError("реализация — часть работы")


def generate_drafts(
    docs: Sequence[DocumentRef],
    client,
    model: str,
    prompt_id: str = "draft-v1",
    per_doc: int = 2,
) -> list[Draft]:
    r"""Черновики по документам моделью $g_{\mathrm{draft}}$ (``temperature = 0``).

    Модель-черновик не должна принадлежать $\mathcal{L}$ и не должна совпадать с генератором
    прода, иначе вопросы будут смещены в сторону её собственных знаний.
    """
    raise NotImplementedError("реализация — часть работы")


def generate_unanswerable_drafts(docs: Sequence[DocumentRef], client, model: str, n: int) -> list[Draft]:
    r"""Кандидаты в $G^{\varnothing}$: вопросы с датой-якорем о событиях, отсутствующих в корпусе
    (проверяется поиском по Qdrant: ни один документ не подтверждает ответ)."""
    raise NotImplementedError("реализация — часть работы")


def write_drafts(drafts: Sequence[Draft], path: str) -> None:
    """Записывает черновики в JSONL."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml")
    parser.add_argument("--documents", default="data/seed_pool/sampled_documents.jsonl")
    parser.add_argument("--draft-model", required=False, help="модель g_draft ∉ L")
    parser.add_argument("--out", default="data/golden_set/v0.1-pilot/drafts.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
