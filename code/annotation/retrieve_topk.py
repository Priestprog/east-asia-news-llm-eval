r"""Топ-K ретривера промышленной системы для позиций пилота (протокол разметки, §3; инструкция аннотатора, §4).

Для каждой позиции ищутся $K = 20$ документов корпуса по формулировкам вопроса черновика:
русской и её переводам на английский и китайский (модель перевода из
``code/configs/translation.yaml``). Ретривер — как у $f_{\mathrm{prod}}$: эмбеддинги
``distiluse-base-multilingual-cased-v2`` и коллекция Qdrant корпуса, без порога сходства.
Фрагменты по всем формулировкам сливаются по документу (максимум сходства), остаются $K$ лучших.

Список показывается аннотаторам у всех позиций пилота, чтобы роли позиций (кандидаты в
$G^{\bot}$) не раскрывались; для кандидатов он становится основой
``provenance.unanswerable_check`` (``method = retrieval_topk``). Собственных запросов аннотатора
в пилоте нет (решение 30.10, CHANGELOG). Фрагменты переводятся на русский той же моделью перевода;
переводы фрагментов кэшируются в ``data/_cache/translations/snippets.json``.

Результат: ``data/_cache/retrieval/pilot_top20.jsonl`` — в репозиторий не входит: фрагменты переведены
моделью перевода, а переводы не публикуются (ADR-025, п. 6).
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config, load_env
from code.annotation.corpus import connect_qdrant, connect_webmedia, fetch_pages, webpage_id_of
from code.annotation.generate_drafts import load_positions, read_jsonl
from code.annotation.translate_documents import DEFAULT_CONFIG as TRANSLATION_CONFIG
from code.annotation.translate_documents import Translator

DEFAULT_CONFIG = "code/configs/annotation.yaml"
DIRECTIONS = {"en": "ru_en", "zh": "ru_zh"}


def formulations(question_ru: str, langs: Sequence[str], translator: Translator) -> list[dict]:
    """Формулировки запроса: вопрос черновика и его переводы."""
    out = []
    for lang in langs:
        text = question_ru if lang == "ru" else translator.translate(question_ru, DIRECTIONS[lang])[0]
        out.append({"lang": lang, "text": text})
    return out


def search(queries: list[dict], embedder, client, collection: str, k: int) -> list[dict]:
    """Поиск по всем формулировкам; слияние по документу с максимумом сходства."""
    best: dict[int, dict] = {}
    for q in queries:
        vec = embedder.encode(q["text"]).tolist()
        points = client.query_points(collection_name=collection, query=vec, limit=k, with_payload=True).points
        for pt in points:
            wid = webpage_id_of(int(pt.id))
            hit = best.get(wid)
            if hit is None or pt.score > hit["score"]:
                best[wid] = {"webpage_id": wid, "score": round(float(pt.score), 4), "point_id": int(pt.id),
                             "snippet_zh": (pt.payload or {}).get("chunk") or "",
                             "langs": sorted({q["lang"], *(hit["langs"] if hit else [])})}
            else:
                hit["langs"] = sorted({q["lang"], *hit["langs"]})
    return sorted(best.values(), key=lambda h: -h["score"])[:k]


def retrieve(positions: Sequence[dict], drafts: dict[str, dict], cfg: dict, tr_cfg: dict) -> list[dict]:
    from sentence_transformers import SentenceTransformer

    rc = cfg["retrieval"]
    translator = Translator(tr_cfg)
    translator.check_model()
    embedder = SentenceTransformer(rc["embedder"])
    client, collection = connect_qdrant()
    rows = []
    for n, p in enumerate(positions, 1):
        queries = formulations(drafts[p["position_id"]]["question_ru"], rc["formulations"], translator)
        hits = search(queries, embedder, client, collection, rc["k"])
        rows.append({"position_id": p["position_id"], "webpage_id": p["webpage_id"], "queries": queries,
                     "retriever": f"prod_qdrant/{rc['embedder']}", "k": rc["k"],
                     "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": hits})
        rank = next((i for i, h in enumerate(hits, 1) if h["webpage_id"] == p["webpage_id"]), None)
        print(f"[{n}/{len(positions)}] {p['position_id']}: {len(hits)} док., исходный документ — "
              f"{rank or 'вне топа'}", file=sys.stderr)

    # метаданные документов и переводы фрагментов
    conn = connect_webmedia()
    pages = fetch_pages(conn, {h["webpage_id"] for r in rows for h in r["results"]},
                        ["uri", "date_time", "netloc", "text_content_trafilatura"])
    conn.close()
    cache_path = REPO_ROOT / cfg["paths"]["snippet_translations"]
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    snippets = {str(h["point_id"]): h["snippet_zh"][: rc["snippet_chars"]] for r in rows for h in r["results"]}
    todo = [pid for pid, zh in snippets.items() if zh and pid not in cache] if rc["translate_snippets"] else []
    print(f"фрагментов: {len(snippets)}, к переводу: {len(todo)}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=rc["workers"]) as pool:
        for pid, (ru, _) in zip(todo, pool.map(lambda pid: translator.translate(snippets[pid]), todo)):
            cache[pid] = ru
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    for r in rows:
        for rank, h in enumerate(r["results"], 1):
            page = pages.get(h["webpage_id"], {})
            tf = page.get("text_content_trafilatura") or {}
            h.update({"rank": rank,
                      "snippet_zh": snippets[str(h["point_id"])],
                      "snippet_ru": cache.get(str(h["point_id"])),
                      "title_zh": tf.get("title"),
                      "uri": page.get("uri"),
                      "published_at": page["date_time"].date().isoformat() if page.get("date_time") else None,
                      "source": page.get("netloc"),
                      "is_source_doc": h["webpage_id"] == r["webpage_id"]})
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--limit", type=int, default=None, help="не больше N позиций (отладка)")
    parser.add_argument("--out", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(REPO_ROOT / args.config)
    tr_cfg = load_config(REPO_ROOT / TRANSLATION_CONFIG)
    positions = load_positions(REPO_ROOT / cfg["paths"]["positions"], pilot=True)[: args.limit]
    drafts = {d["position_id"]: d for d in read_jsonl(REPO_ROOT / cfg["paths"]["drafts"])}
    rows = retrieve(positions, drafts, cfg, tr_cfg)
    out = Path(REPO_ROOT / (args.out or cfg["paths"]["retrieval"]))
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    found = sum(any(h["is_source_doc"] for h in r["results"]) for r in rows)
    print(f"{out.relative_to(REPO_ROOT)}: {len(rows)} позиций; исходный документ в топ-{cfg['retrieval']['k']} — "
          f"у {found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
