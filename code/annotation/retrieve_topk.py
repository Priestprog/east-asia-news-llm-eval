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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config, load_env
from code.annotation.corpus import connect_qdrant, connect_webmedia, fetch_pages, webpage_id_of
from code.annotation.generate_drafts import read_by_position, read_jsonl, round_positions
from code.annotation.translate_documents import DEFAULT_CONFIG as TRANSLATION_CONFIG
from code.annotation.translate_documents import Translator

DEFAULT_CONFIG = "code/configs/annotation.yaml"
DIRECTIONS = {"en": "ru_en", "zh": "ru_zh"}
RETRY_ATTEMPTS = 5
RETRY_BASE_SECONDS = 10


def formulations(question_ru: str, langs: Sequence[str], translator: Translator) -> list[dict]:
    """Формулировки запроса: вопрос черновика и его переводы."""
    out = []
    for lang in langs:
        text = question_ru if lang == "ru" else translator.translate(question_ru, DIRECTIONS[lang])[0]
        out.append({"lang": lang, "text": text})
    return out


def query_with_retry(client, collection: str, vec: list[float], k: int, attempts: int = RETRY_ATTEMPTS):
    """Запрос к Qdrant с повтором при таймауте и ошибках сервера или соединения (туннель к корпусу)."""
    from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

    for attempt in range(1, attempts + 1):
        try:
            return client.query_points(collection_name=collection, query=vec, limit=k, with_payload=True).points
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            status = getattr(exc, "status_code", None)
            if attempt == attempts or (status is not None and status != 408 and status < 500):
                raise
            wait = RETRY_BASE_SECONDS * 2 ** (attempt - 1)
            print(f"Qdrant: {status or type(exc).__name__}, повтор {attempt}/{attempts - 1} через {wait} с",
                  file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def search(queries: list[dict], embedder, client, collection: str, k: int) -> list[dict]:
    """Поиск по всем формулировкам; слияние по документу с максимумом сходства."""
    best: dict[int, dict] = {}
    for q in queries:
        vec = embedder.encode(q["text"]).tolist()
        points = query_with_retry(client, collection, vec, k)
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


def load_partial(path: Path, positions: Sequence[dict], drafts: dict[str, dict]) -> dict[str, dict]:
    """Строки прерванного запуска, ещё годные: та же позиция, тот же документ и вопрос черновика.
    Оборванная последняя строка (процесс остановлен во время записи) пропускается."""
    if not path.exists():
        return {}
    by_id = {p["position_id"]: p for p in positions}
    done = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        p = by_id.get(r["position_id"])
        if p and r["webpage_id"] == p["webpage_id"] and r.get("question_ru") == drafts[r["position_id"]]["question_ru"]:
            done[r["position_id"]] = r
    return done


def retrieve(positions: Sequence[dict], drafts: dict[str, dict], cfg: dict, tr_cfg: dict,
             partial_path: Path | None = None, workers: int | None = None) -> list[dict]:
    r"""Топ-$K$ по позициям в ``workers`` потоках. Каждая задача — поиск по позиции (если его нет в
    промежуточном файле) и сразу перевод её фрагментов, которых нет в кэше; поиск одних позиций идёт
    одновременно с переводом фрагментов других. Найденное и кэш переводов пишутся по ходу, поэтому
    прерванный запуск продолжается с места остановки."""
    from sentence_transformers import SentenceTransformer

    rc = cfg["retrieval"]
    workers = workers or rc["workers"]
    translator = Translator(tr_cfg)
    translator.check_model()
    embedder = SentenceTransformer(rc["embedder"])
    client, collection = connect_qdrant()
    embed_lock, cache_lock, out_lock = threading.Lock(), threading.Lock(), threading.Lock()

    class LockedEmbedder:
        def encode(self, text):
            with embed_lock:
                return embedder.encode(text)

    cache_path = REPO_ROOT / cfg["paths"]["snippet_translations"]
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    def save_cache() -> None:
        with cache_lock:
            payload = json.dumps(cache, ensure_ascii=False)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(cache_path)

    def snippet_of(h: dict) -> str:
        return h["snippet_zh"][: rc["snippet_chars"]]

    done = load_partial(partial_path, positions, drafts) if partial_path else {}
    if done:
        print(f"продолжение: {len(done)} позиций уже найдено ({partial_path.name})", file=sys.stderr)
    partial = partial_path.open("w", encoding="utf-8") if partial_path else None
    if partial:
        partial.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in done.values())
        partial.flush()

    def task(p: dict) -> tuple[dict, int, bool]:
        """Поиск по позиции (если нужен) и перевод её недостающих фрагментов."""
        row, fresh = done.get(p["position_id"]), False
        if row is None:
            question = drafts[p["position_id"]]["question_ru"]
            queries = formulations(question, rc["formulations"], translator)
            hits = search(queries, LockedEmbedder(), client, collection, rc["k"])
            row = {"position_id": p["position_id"], "webpage_id": p["webpage_id"], "question_ru": question,
                   "queries": queries, "retriever": f"prod_qdrant/{rc['embedder']}", "k": rc["k"],
                   "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": hits}
            fresh = True
            if partial:
                with out_lock:
                    partial.write(json.dumps(row, ensure_ascii=False) + "\n")
                    partial.flush()
        translated = 0
        if rc["translate_snippets"]:
            for h in row["results"]:
                pid, zh = str(h["point_id"]), snippet_of(h)
                with cache_lock:
                    if not zh or pid in cache:
                        continue
                ru, _ = translator.translate(zh)
                with cache_lock:
                    cache[pid] = ru
                translated += 1
        return row, translated, fresh

    by_id: dict[str, dict] = {}
    total_translated = 0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(task, p): p for p in positions}
            for n, future in enumerate(as_completed(futures), 1):
                p = futures[future]
                row, translated, fresh = future.result()
                by_id[p["position_id"]] = row
                total_translated += translated
                rank = next((i for i, h in enumerate(row["results"], 1) if h["webpage_id"] == p["webpage_id"]), None)
                print(f"[{n}/{len(positions)}] {p['position_id']}: {'поиск, ' if fresh else ''}{len(row['results'])} док., "
                      f"исходный документ — {rank or 'вне топа'}; переведено фрагментов: {translated}", file=sys.stderr)
                if n % 5 == 0:
                    save_cache()
    finally:
        save_cache()
        if partial:
            partial.close()
    print(f"переведено фрагментов за запуск: {total_translated}", file=sys.stderr)
    rows = [by_id[p["position_id"]] for p in positions]
    for r in rows:
        r.pop("question_ru", None)

    # метаданные документов
    conn = connect_webmedia()
    pages = fetch_pages(conn, {h["webpage_id"] for r in rows for h in r["results"]},
                        ["uri", "date_time", "netloc", "text_content_trafilatura"])
    conn.close()
    for r in rows:
        for rank, h in enumerate(r["results"], 1):
            page = pages.get(h["webpage_id"], {})
            tf = page.get("text_content_trafilatura") or {}
            h.update({"rank": rank,
                      "snippet_zh": snippet_of(h),
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
    parser.add_argument("--workers", type=int, default=None,
                        help="потоков: поиск и перевод фрагментов (по умолчанию retrieval.workers)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(REPO_ROOT / args.config)
    tr_cfg = load_config(REPO_ROOT / TRANSLATION_CONFIG)
    positions = round_positions(cfg)[: args.limit]
    drafts = read_by_position(cfg["paths"]["drafts"])
    target = args.out or cfg["paths"]["retrieval"]
    if not isinstance(target, str):
        raise SystemExit("paths.retrieval — список файлов (единый пул разметки): укажите файл результата через --out")
    out = Path(REPO_ROOT / target)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial_path = out.with_name(out.stem + ".partial.jsonl")
    rows = retrieve(positions, drafts, cfg, tr_cfg, partial_path, args.workers)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    partial_path.unlink(missing_ok=True)
    found = sum(any(h["is_source_doc"] for h in r["results"]) for r in rows)
    print(f"{out.relative_to(REPO_ROOT)}: {len(rows)} позиций; исходный документ в топ-{cfg['retrieval']['k']} — "
          f"у {found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
