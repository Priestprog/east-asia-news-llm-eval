r"""Снимок корпуса $D_{t_0}$ и отбор позиций для черновиков вопросов (ADR-023).

Источник: пересечение таблицы ``webmedia.webpages`` (PostgreSQL) и коллекции Qdrant —
так покрытие $S^*_i \subset \mathcal{I}$ ретривером равно 1 по построению.

Подкоманды:

* ``probe`` — проверка подключения: коллекция, поля payload, колонки таблицы, домены;
* ``snapshot`` — множество $\mathcal{I}$ (все ``webpage_id`` коллекции Qdrant), паспорт снимка
  ``data/corpus_snapshot/meta.json`` и распределение документов по доменам и месяцам;
* ``sample`` — позиции: статьи seed pool и новые документы, отобранные по стратам
  «регион × домен × месяц» (категории в корпусе нет, она размечается позже), роли
  (кандидаты в $G^{\bot}$, контроль правил исключения), пилот и резерв →
  ``data/seed_pool/sampled_documents.jsonl`` и ``data/seed_pool/sampling_report.md``;
* ``fetch`` — тексты документов позиций (оригинал и, если есть, перевод фрагментов из
  payload Qdrant) в локальный кэш ``data/_cache/documents/`` для черновиков; в репозиторий
  тексты не входят;
* ``replace`` — замена непригодной позиции резервной из той же страты (тот же домен, ближайший
  месяц): резервная занимает её место в основном наборе и пилоте, заменённая остаётся в файле
  с отметкой ``replaced_by`` и причиной.

Ограничения снимка: ≥3 доменов, ≥2 регионов, охват ≥12 месяцев по $\tau_j \le t_0$.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config
from code.annotation.corpus import (
    batched,
    connect_qdrant,
    connect_webmedia,
    fetch_pages,
    point_id_of,
    webpage_id_of,
)

SNAPSHOT_DIR = REPO_ROOT / "data" / "corpus_snapshot"
CACHE_DIR = REPO_ROOT / "data" / "_cache"
SNAPSHOT_CACHE = CACHE_DIR / "snapshot"
DOCS_CACHE = CACHE_DIR / "documents"
SEED_POOL_DIR = REPO_ROOT / "data" / "seed_pool"

PAGE_FIELDS = ["webpage_id", "urn_uuid", "uri", "published_at", "month", "netloc", "lang_code", "text_len"]


@dataclass
class DocumentRef:
    r"""Метаданные документа $d_j$ без текстов: $(\iota_j, u_j, \tau_j, o_j)$ плюс страты."""

    webpage_id: int
    urn_uuid: str | None
    uri: str
    published_at: str   # ISO-8601, $\tau_j \le t_0$
    source: str         # домен
    region: str         # КНР | Тайвань | Гонконг | Сингапур | Франция (RFI)
    category: str | None


@dataclass
class Position:
    """Позиция для черновика: документ корпуса и, для seed pool, исходные вопросы."""

    position_id: str
    webpage_id: int
    urn_uuid: str | None
    uri: str
    published_at: str
    netloc: str
    region: str
    origin: str                      # seed | new
    role: str                        # answerable | unanswerable_candidate | dynamic_control
    pilot: bool
    reserve: bool
    seed_refs: list[int] = field(default_factory=list)
    control_seed_idx: int | None = None
    category_hint: str | None = None
    text_len: int | None = None
    replaces: str | None = None          # резервная позиция, занявшая место заменённой
    replaced_by: str | None = None       # заменённая позиция: выведена из основного набора и пилота
    replace_reason: str | None = None


def is_main(p: Position) -> bool:
    """Позиция основного набора: не резерв и не заменённая."""
    return not p.reserve and not p.replaced_by


# ---------------------------------------------------------------- probe

def probe() -> None:
    client, collection = connect_qdrant()
    names = sorted(c.name for c in client.get_collections().collections)
    info = client.get_collection(collection)
    print(f"Qdrant: коллекций {len(names)}; активная {collection}: points_count={info.points_count}")
    points, _ = client.scroll(collection, limit=5, with_payload=True, with_vectors=False)
    for p in points:
        payload = p.payload or {}
        print(f"  point {p.id} → webpage_id {webpage_id_of(int(p.id))}, chunk {int(p.id) & 0xFFFF}; "
              f"payload: {sorted(payload)}; chunk_ru: {'есть' if payload.get('chunk_ru') else 'нет'}")
    if points:
        wid = webpage_id_of(int(points[0].id))
        got = client.retrieve(collection, ids=[point_id_of(wid, k) for k in range(64)], with_payload=False)
        print(f"  номера фрагментов документа {wid}: {sorted(int(p.id) & 0xFFFF for p in got)}")

    conn = connect_webmedia()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'webmedia' AND table_name = 'webpages' ORDER BY ordinal_position"
        )
        print("webmedia.webpages:", ", ".join(f"{c} {t}" for c, t in cur.fetchall()))
        cur.execute("SELECT reltuples::bigint FROM pg_class WHERE oid = 'webmedia.webpages'::regclass")
        print("  строк (оценка pg_class):", cur.fetchone()[0])
        cur.execute(
            "SELECT lang_code, count(*) FROM webmedia.webpages TABLESAMPLE SYSTEM (0.5) "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
        )
        print("  lang_code (выборка 0,5 %):", cur.fetchall())
        cur.execute(
            "SELECT netloc, count(*), min(date_time)::date, max(date_time)::date "
            "FROM webmedia.webpages TABLESAMPLE SYSTEM (0.5) GROUP BY 1 ORDER BY 2 DESC LIMIT 40"
        )
        for row in cur.fetchall():
            print("  ", row)
    conn.close()


# ---------------------------------------------------------------- snapshot

def scroll_webpage_ids(client, collection: str, batch: int = 20000) -> list[int]:
    """Все ``webpage_id`` коллекции: прокрутка идентификаторов точек без payload и векторов.

    Прогресс сохраняется в ``data/_cache/snapshot``; прерванная прокрутка продолжается с места остановки.
    """
    SNAPSHOT_CACHE.mkdir(parents=True, exist_ok=True)
    state_path, ids_path = SNAPSHOT_CACHE / "scroll_state.json", SNAPSHOT_CACHE / "ids_part.txt"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"offset": None, "points": 0, "done": False}
    if state_path.exists() and ids_path.exists():
        # возобновление: дописанные после последнего сохранения состояния строки отбрасываются
        lines = ids_path.read_text().splitlines()[: state.get("lines", 0)]
        ids_path.write_text("".join(f"{x}\n" for x in lines))
    elif ids_path.exists():
        ids_path.unlink()
    with open(ids_path, "a") as out:
        while not state["done"]:
            points, nxt = client.scroll(
                collection, limit=batch, offset=state["offset"], with_payload=False, with_vectors=False
            )
            wids = sorted({webpage_id_of(int(p.id)) for p in points})
            out.write("".join(f"{w}\n" for w in wids))
            out.flush()
            state["points"] += len(points)
            state["lines"] = state.get("lines", 0) + len(wids)
            state["offset"], state["done"] = nxt, nxt is None
            state_path.write_text(json.dumps(state))
            if state["points"] % 1_000_000 < batch:
                print(f"  прокручено точек: {state['points']:,}", flush=True)
    ids = sorted({int(x) for x in ids_path.read_text().split()})
    return ids


def ids_sha256(ids: Sequence[int]) -> str:
    return hashlib.sha256("\n".join(str(i) for i in sorted(ids)).encode()).hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def snapshot() -> dict:
    client, collection = connect_qdrant()
    info = client.get_collection(collection)
    t0 = datetime.now(timezone.utc).date().isoformat()
    ids = scroll_webpage_ids(client, collection)
    with gzip.open(SNAPSHOT_CACHE / "webpage_ids.txt.gz", "wt") as fh:
        fh.write("\n".join(map(str, ids)) + "\n")

    conn = connect_webmedia()
    pages_path = SNAPSHOT_CACHE / "pages.csv.gz"
    netloc_month: Counter = Counter()
    langs: Counter = Counter()
    missing = 0
    with conn.cursor() as cur, gzip.open(pages_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PAGE_FIELDS)
        for chunk in batched(ids, 20000):
            cur.execute(
                # длина очищенного текста trafilatura; без него документ не годится для разметки (0)
                "SELECT id, urn_uuid::text, uri, date_time, netloc, lang_code, "
                "coalesce(length(text_content_trafilatura->>'text'), 0) "
                "FROM webmedia.webpages WHERE id = ANY(%s)",
                (list(chunk),),
            )
            rows = cur.fetchall()
            missing += len(chunk) - len(rows)
            for wid, urn, uri, dt, netloc, lang, tlen in rows:
                day = dt.date().isoformat() if dt else ""
                month = day[:7]
                writer.writerow([wid, urn or "", uri, day, month, netloc, lang or "", tlen or 0])
                netloc_month[(netloc, month)] += 1
                langs[lang or ""] += 1
    conn.close()

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_DIR / "netloc_month_counts.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["netloc", "month", "documents"])
        for (netloc, month), n in sorted(netloc_month.items()):
            writer.writerow([netloc, month, n])
    months = sorted({m for _, m in netloc_month if m})
    meta = {
        "t0": t0,
        "collection": collection,
        "points_count": info.points_count,
        "N": len(ids),
        "ids_sha256": ids_sha256(ids),
        "ids_hash_definition": "sha256 строки отсортированных webpage_id через \\n",
        "webpages_missing_in_postgres": missing,
        "domains": len({n for n, _ in netloc_month}),
        "months": {"first": months[0] if months else None, "last": months[-1] if months else None,
                   "distinct": len(months)},
        "lang_code": dict(langs.most_common()),
        "code_git_sha": git_sha(),
    }
    (SNAPSHOT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


# ---------------------------------------------------------------- sample

_CATEGORY_HINTS = [
    ("economy", r"financ|econom|business|money|stock|market|property|財經|财经|imoney|invest"),
    ("international", r"world|international|global|china-world|國際|国际"),
    ("politics", r"politic|政治"),
    ("technology", r"tech|science|digital|科技"),
    ("security", r"military|defen[cs]e|軍事|军事"),
    ("health", r"health|medical|健康"),
    ("culture", r"culture|entertainment|lifestyle|life|arts|travel|food|娛樂|娱乐|文化"),
    ("society", r"society|social|local|社會|社会|地方"),
    ("environment", r"environment|climate|環境|环境"),
]


def category_hint(uri: str) -> str | None:
    """Подсказка категории по поддомену и пути URL; только для отчёта, не для стратификации."""
    from urllib.parse import unquote, urlsplit

    parts = urlsplit(uri)
    text = (parts.netloc + " " + unquote(parts.path)).lower()
    for cat, pattern in _CATEGORY_HINTS:
        if re.search(pattern, text):
            return cat
    return None


def load_pages() -> list[dict]:
    with gzip.open(SNAPSHOT_CACHE / "pages.csv.gz", "rt", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["webpage_id"], r["text_len"] = int(r["webpage_id"]), int(r["text_len"] or 0)
    return rows


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def split_evenly(total: int, keys: Sequence) -> dict:
    keys = list(keys)
    base, extra = divmod(total, len(keys))
    return {k: base + (1 if i < extra else 0) for i, k in enumerate(keys)}


def stratified_sample(candidates: list[dict], regions: dict[str, list[str]], n_main: int, n_reserve: int,
                      rng: random.Random, min_cell: int = 1) -> tuple[list[dict], list[dict]]:
    r"""Отбор по стратам «регион × домен × месяц».

    Квоты делятся поровну между регионами, внутри региона — поровну между доменами; внутри домена
    документы берутся по кругу по месяцам (один случайный документ месяца за проход), поэтому
    позиции распределены по времени равномерно. Первые ``main``-квоты прохода — основные позиции,
    следующие — резерв той же страты. Ячейки «домен × месяц» меньше ``min_cell`` документов
    (края месячных выгрузок корпуса) не используются.
    """
    by_cell: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in sorted(candidates, key=lambda r: r["webpage_id"]):
        by_cell[c["netloc"]][c["month"]].append(c)
    for netloc in list(by_cell):
        by_cell[netloc] = defaultdict(list, {m: d for m, d in by_cell[netloc].items() if len(d) >= min_cell})
    main_q, res_q = split_evenly(n_main, sorted(regions)), split_evenly(n_reserve, sorted(regions))
    main, reserve = [], []
    for region in sorted(regions):
        domains = [d for d in regions[region] if by_cell.get(d)]
        if not domains:
            raise ValueError(f"в регионе {region} нет кандидатов")
        dm, dr = split_evenly(main_q[region], domains), split_evenly(res_q[region], domains)
        for domain in domains:
            pools = {m: rng.sample(docs, len(docs)) for m, docs in sorted(by_cell[domain].items())}
            need, picked = dm[domain] + dr[domain], []
            while len(picked) < need and any(pools.values()):
                for month in sorted(pools):
                    if pools[month] and len(picked) < need:
                        picked.append(dict(pools[month].pop(), region=region))
            if len(picked) < need:
                raise ValueError(f"в домене {domain} только {len(picked)} кандидатов из {need}")
            main += picked[: dm[domain]]
            reserve += picked[dm[domain]:]
    return main, reserve


def select_seed_positions(cfg: dict, seed_pool: list[dict], mapping: list[dict], rng: random.Random) -> list[dict]:
    """Статьи seed pool: в каждом домене — статьи с наибольшим числом вопросов без маркеров E1, E2, E4."""
    by_wid: dict[int, list[dict]] = defaultdict(list)
    for q in seed_pool:
        if q["webpage_id"] is not None and q["in_qdrant"]:
            by_wid[q["webpage_id"]].append(q)
    rows = {int(m["webpage_id"]): m for m in mapping if m["webpage_id"]}
    chosen = []
    for netloc, n in sorted(cfg["n_seed"].items()):
        arts = sorted(w for w, qs in by_wid.items() if qs[0]["netloc"] == netloc)
        keyed = [(-sum(not q["static_flag"] for q in by_wid[w]), rng.random(), w) for w in arts]
        top = [w for *_, w in sorted(keyed)[:n]]
        if len(top) < n:
            raise ValueError(f"seed pool {netloc}: {len(top)} статей из {n}")
        for w in top:
            m = rows[w]
            chosen.append({
                "webpage_id": w, "urn_uuid": m["urn_uuid"] or None, "uri": m["uri"],
                "published_at": m["published_at"], "netloc": m["netloc"],
                "region": cfg["seed_regions"][netloc],
                "seed_refs": sorted(q["seed_idx"] for q in by_wid[w]),
                "questions": by_wid[w],
            })
    return chosen


def sample(config_path: str) -> list[Position]:
    cfg = load_config(config_path)
    rng = random.Random(cfg["seed"])
    meta = json.loads((SNAPSHOT_DIR / "meta.json").read_text(encoding="utf-8"))
    t0 = meta["t0"]
    seed_pool = read_jsonl(SEED_POOL_DIR / "seed_pool.jsonl")
    with open(SEED_POOL_DIR / "warc_to_webpage.csv", encoding="utf-8", newline="") as fh:
        mapping = list(csv.DictReader(fh))

    seed = select_seed_positions(cfg, seed_pool, mapping, rng)
    seed_ids = {s["webpage_id"] for s in seed_pool if s["webpage_id"] is not None}
    flt = cfg["filters"]
    regions = cfg["regions"]
    netlocs = {d for ds in regions.values() for d in ds}
    candidates = [
        p for p in load_pages()
        if p["netloc"] in netlocs and p["lang_code"] in flt["lang_codes"]
        and flt["text_len_min"] <= p["text_len"] <= flt["text_len_max"]
        and flt["month_from"] <= p["month"] <= flt["month_to"]
        and p["published_at"] and p["published_at"] <= t0
        and p["webpage_id"] not in seed_ids
        and not re.search(flt["exclude_uri_regex"], p["uri"])
    ]
    n_new = cfg["n_positions"] - sum(cfg["n_seed"].values())
    main_new, reserve_new = stratified_sample(candidates, regions, n_new, cfg["n_reserve"], rng,
                                              min_cell=flt.get("min_cell_documents", 1))

    # роли: кандидаты в G⊥ поровну по регионам среди новых позиций
    unans: set[int] = set()
    for region, k in split_evenly(cfg["n_unanswerable"], sorted(regions)).items():
        pool = sorted(p["webpage_id"] for p in main_new if p["region"] == region)
        unans.update(rng.sample(pool, k))

    # пилот: seed-позиции (в том числе контроль правил исключения) и новые позиции по регионам
    pc = cfg["pilot"]
    flagged = [s for s in seed if any(q["markers"]["E1"] or q["markers"]["E4"] for q in s["questions"])]
    controls = {s["webpage_id"] for s in rng.sample(flagged, pc["dynamic_controls"])}
    rest_seed = sorted(s["webpage_id"] for s in seed if s["webpage_id"] not in controls)
    pilot = controls | set(rng.sample(rest_seed, pc["seed"] - pc["dynamic_controls"]))
    for region in sorted(regions):
        in_region = sorted(p["webpage_id"] for p in main_new if p["region"] == region)
        u = sorted(w for w in in_region if w in unans)
        a = sorted(w for w in in_region if w not in unans)
        k_new = split_evenly(pc["new"], sorted(regions))[region]
        k_u = split_evenly(pc["unanswerable"], sorted(regions))[region]
        pilot.update(rng.sample(u, k_u))
        pilot.update(rng.sample(a, k_new - k_u))

    positions: list[Position] = []
    for s in sorted(seed, key=lambda s: (s["netloc"], s["published_at"], s["webpage_id"])):
        ctl = None
        if s["webpage_id"] in controls:
            ctl = next(q["seed_idx"] for q in s["questions"] if q["markers"]["E1"] or q["markers"]["E4"])
        positions.append(Position(
            position_id="", webpage_id=s["webpage_id"], urn_uuid=s["urn_uuid"], uri=s["uri"],
            published_at=s["published_at"], netloc=s["netloc"], region=s["region"], origin="seed",
            role="dynamic_control" if ctl is not None else "answerable",
            pilot=s["webpage_id"] in pilot, reserve=False, seed_refs=s["seed_refs"],
            control_seed_idx=ctl, category_hint=category_hint(s["uri"]),
        ))
    for group, is_reserve in ((main_new, False), (reserve_new, True)):
        for p in sorted(group, key=lambda p: (p["region"], p["netloc"], p["published_at"], p["webpage_id"])):
            positions.append(Position(
                position_id="", webpage_id=p["webpage_id"], urn_uuid=p["urn_uuid"] or None, uri=p["uri"],
                published_at=p["published_at"], netloc=p["netloc"], region=p["region"], origin="new",
                role="unanswerable_candidate" if p["webpage_id"] in unans else "answerable",
                pilot=(not is_reserve) and p["webpage_id"] in pilot, reserve=is_reserve,
                category_hint=category_hint(p["uri"]), text_len=p["text_len"],
            ))
    main_i = res_i = 0
    for pos in positions:
        if pos.reserve:
            res_i += 1
            pos.position_id = f"r-{res_i:03d}"
        else:
            main_i += 1
            pos.position_id = f"p-{main_i:03d}"

    check_constraints(positions, cfg, t0, set(load_snapshot_ids()))
    return positions


def load_snapshot_ids() -> list[int]:
    with gzip.open(SNAPSHOT_CACHE / "webpage_ids.txt.gz", "rt") as fh:
        return [int(x) for x in fh.read().split()]


def check_constraints(positions: list[Position], cfg: dict, t0: str, snapshot_ids: set[int]) -> None:
    main = [p for p in positions if is_main(p)]
    pilot = [p for p in main if p.pilot]
    checks = {
        "основных позиций": (len(main), cfg["n_positions"]),
        # резерв считается вместе с уже использованными для замен позициями; статьи seed pool,
        # добранные для замены seed-позиций (s-NNN), в резерв отбора не входят
        "резервных позиций": (sum((p.reserve or p.replaces is not None) and not p.position_id.startswith("s-")
                                  for p in positions), cfg["n_reserve"]),
        "seed-позиций": (sum(p.origin == "seed" for p in main), sum(cfg["n_seed"].values())),
        "кандидатов в G⊥": (sum(p.role == "unanswerable_candidate" for p in main), cfg["n_unanswerable"]),
        "позиций пилота": (len(pilot), cfg["pilot"]["seed"] + cfg["pilot"]["new"]),
        "контрольных в пилоте": (sum(p.role == "dynamic_control" for p in pilot), cfg["pilot"]["dynamic_controls"]),
        "кандидатов в G⊥ в пилоте": (sum(p.role == "unanswerable_candidate" for p in pilot), cfg["pilot"]["unanswerable"]),
    }
    errors = [f"{name}: {got} вместо {want}" for name, (got, want) in checks.items() if got != want]
    ids = [p.webpage_id for p in positions]
    if len(ids) != len(set(ids)):
        errors.append("повторяющиеся webpage_id")
    if not set(ids) <= snapshot_ids:
        errors.append("есть документы вне снимка D_t0")
    if any(p.published_at > t0 for p in positions):
        errors.append("есть документы позже t0")
    if len({p.netloc for p in main}) < 3:
        errors.append("меньше 3 доменов")
    if len({p.region for p in main}) < 2:
        errors.append("меньше 2 регионов")
    if len({p.published_at[:7] for p in main}) < 12:
        errors.append("охват меньше 12 месяцев")
    if errors:
        raise ValueError("; ".join(errors))


def write_report(positions: list[Position], path: Path, meta: dict) -> None:
    main = [p for p in positions if is_main(p)]
    reserve_total = sum((p.reserve or p.replaces is not None) and not p.position_id.startswith("s-") for p in positions)
    from_seed_pool = sum(p.position_id.startswith("s-") for p in positions)

    def table(title: str, key) -> list[str]:
        cnt = Counter(key(p) for p in main)
        lines = [f"### {title}", "", "| Значение | Позиций |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))]
        return lines + [""]

    months = sorted({p.published_at[:7] for p in main})
    lines = [
        "# Отбор позиций для черновиков",
        "",
        f"Снимок $`D_{{t_0}}`$: $`t_0`$ = {meta['t0']}, $`N`$ = {meta['N']:,} документов, "
        f"SHA-256 списка идентификаторов `{meta['ids_sha256'][:16]}…` (`data/corpus_snapshot/meta.json`).",
        "",
        f"Основных позиций: {len(main)} (seed pool — {sum(p.origin == 'seed' for p in main)}, "
        f"новых — {sum(p.origin == 'new' for p in main)}); резерв — {reserve_total}"
        + (f", добрано из seed pool для замены seed-позиций — {from_seed_pool}" if from_seed_pool else "")
        + f"; пилот — {sum(p.pilot for p in main)}. Охват: {len(months)} месяцев ({months[0]} — {months[-1]}), "
        f"{len({p.netloc for p in main})} доменов, {len({p.region for p in main})} регионов.",
        "",
    ]
    lines += table("Регионы", lambda p: p.region)
    lines += table("Домены", lambda p: p.netloc)
    lines += table("Роли", lambda p: p.role)
    lines += table("Подсказка категории по URL (только для отчёта)", lambda p: p.category_hint or "—")
    lines += table("Годы публикации", lambda p: p.published_at[:4])
    pilot = [p for p in main if p.pilot]
    lines += ["### Пилот", "", "| Регион | Позиций | Из них контроль | Из них кандидаты в G⊥ |", "|---|---|---|---|"]
    for region in sorted({p.region for p in pilot}):
        ps = [p for p in pilot if p.region == region]
        lines.append(f"| {region} | {len(ps)} | {sum(p.role == 'dynamic_control' for p in ps)} | "
                     f"{sum(p.role == 'unanswerable_candidate' for p in ps)} |")
    replaced = [p for p in positions if p.replaced_by]
    if replaced:
        lines += ["", "### Замены", "", "| Позиция | Заменена на | Причина |", "|---|---|---|"]
        lines += [f"| {p.position_id} | {p.replaced_by} | {p.replace_reason or '—'} |" for p in replaced]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- replace

def seed_pool_candidates(positions: list[Position], old: Position) -> list[Position]:
    """Неиспользованные статьи seed pool того же домена, что и ``old``: в Qdrant и в снимке $D_{t_0}$,
    с метаданными из ``warc_to_webpage.csv``. Резерв отбора состоит только из новых документов, поэтому
    seed-позицию иначе заменить нечем."""
    with open(SEED_POOL_DIR / "warc_to_webpage.csv", encoding="utf-8", newline="") as fh:
        mapping = {int(m["webpage_id"]): m for m in csv.DictReader(fh) if m["webpage_id"]}
    used = {p.webpage_id for p in positions}
    by_wid: dict[int, list[dict]] = defaultdict(list)
    for q in read_jsonl(SEED_POOL_DIR / "seed_pool.jsonl"):
        w = q["webpage_id"]
        if w is not None and q["in_qdrant"] and q["netloc"] == old.netloc and w not in used:
            by_wid[w].append(q)
    snapshot_ids = set(load_snapshot_ids())
    out = []
    for w, qs in sorted(by_wid.items()):
        m = mapping.get(w)
        if m is None or w not in snapshot_ids:
            continue
        out.append(Position(
            position_id="", webpage_id=w, urn_uuid=m["urn_uuid"] or None, uri=m["uri"],
            published_at=m["published_at"], netloc=m["netloc"], region=old.region, origin="seed",
            role=old.role, pilot=False, reserve=True, seed_refs=sorted(q["seed_idx"] for q in qs),
            category_hint=category_hint(m["uri"]),
        ))
    return out


def replace(positions_path: Path, position_id: str, reason: str, config: str,
            allow_role_change: bool = False, from_seed_pool: bool = False) -> Position:
    r"""Замена позиции ``position_id`` резервной из той же страты.

    Кандидаты — неиспользованные резервные позиции с тем же доменом, происхождением и ролью; среди
    них берётся ближайшая по месяцу публикации (при равенстве — меньший номер), при отсутствии —
    тот же регион. Резервная получает ``reserve = false``, флаг пилота заменённой и ``replaces``;
    заменённая — ``pilot = false``, ``replaced_by`` и причину. Ограничения отбора проверяются заново.

    Если таких кандидатов нет:

    * ``allow_role_change`` — для кандидата в $G^{\bot}$ берётся резервная позиция того же
      происхождения и домена (региона) с другой ролью и получает роль заменённой: роль — это задание
      для черновика, а не свойство документа, поэтому число кандидатов в $G^{\bot}$ сохраняется;
    * ``from_seed_pool`` — для seed-позиции берётся неиспользованная статья seed pool того же домена
      (:func:`seed_pool_candidates`); она получает номер ``s-NNN`` и в резерв отбора не засчитывается.
    """
    positions = [Position(**row) for row in read_jsonl(positions_path)]
    by_id = {p.position_id: p for p in positions}
    old = by_id.get(position_id)
    if old is None or not is_main(old):
        raise ValueError(f"{position_id}: нет такой позиции в основном наборе")

    def month_gap(p: Position) -> int:
        y1, m1 = map(int, old.published_at[:7].split("-"))
        y2, m2 = map(int, p.published_at[:7].split("-"))
        return abs((y1 - y2) * 12 + (m1 - m2))

    def same_stratum(pool: list[Position]) -> list[Position]:
        return [p for p in pool if p.netloc == old.netloc] or [p for p in pool if p.region == old.region]

    free = [p for p in positions if p.reserve and p.origin == old.origin]
    candidates = same_stratum([p for p in free if p.role == old.role])
    if not candidates and allow_role_change and old.role == "unanswerable_candidate":
        candidates = same_stratum(free)
    if not candidates and from_seed_pool and old.origin == "seed":
        candidates = seed_pool_candidates(positions, old)
    if not candidates:
        raise ValueError(f"{position_id}: нет резервной позиции той же страты")
    new = min(candidates, key=lambda p: (month_gap(p), p.position_id, p.webpage_id))
    if not new.position_id:
        new.position_id = f"s-{sum(p.position_id.startswith('s-') for p in positions) + 1:03d}"
        positions.append(new)
    new.reserve, new.pilot, new.replaces, new.role = False, old.pilot, old.position_id, old.role
    old.pilot, old.replaced_by, old.replace_reason = False, new.position_id, reason

    cfg = load_config(REPO_ROOT / config)
    meta = json.loads((SNAPSHOT_DIR / "meta.json").read_text(encoding="utf-8"))
    check_constraints(positions, cfg, meta["t0"], set(load_snapshot_ids()))
    with open(positions_path, "w", encoding="utf-8") as fh:
        for p in positions:
            fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
    write_report(positions, SEED_POOL_DIR / "sampling_report.md", meta)
    return new


# ---------------------------------------------------------------- fetch

def fetch(positions_path: Path, only: set[str] | None = None) -> None:
    positions = [p for p in read_jsonl(positions_path) if only is None or p["position_id"] in only]
    DOCS_CACHE.mkdir(parents=True, exist_ok=True)
    conn = connect_webmedia()
    client, collection = connect_qdrant()
    pages = fetch_pages(conn, [p["webpage_id"] for p in positions],
                        ["uri", "date_time", "netloc", "text_content_trafilatura"])
    conn.close()
    with_ru = 0
    for p in positions:
        wid = p["webpage_id"]
        points = client.retrieve(collection, ids=[point_id_of(wid, k) for k in range(256)],
                                 with_payload=True, with_vectors=False)
        chunks = sorted(((int(pt.id) & 0xFFFF, pt.payload or {}) for pt in points), key=lambda x: x[0])
        page = pages[wid]
        tf = page["text_content_trafilatura"] or {}
        doc = {
            "webpage_id": wid,
            "uri": page["uri"],
            "published_at": page["date_time"].date().isoformat() if page["date_time"] else None,
            "netloc": page["netloc"],
            "title_zh": tf.get("title"),
            "text_zh": tf.get("text"),
            "chunks": [{"chunk": k, "text": pl.get("chunk"), "text_ru": pl.get("chunk_ru")} for k, pl in chunks],
        }
        with_ru += any(c["text_ru"] for c in doc["chunks"])
        (DOCS_CACHE / f"{wid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"тексты: {len(positions)} документов в {DOCS_CACHE.relative_to(REPO_ROOT)}; "
          f"с переводом фрагментов (chunk_ru): {with_ru}")


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["probe", "snapshot", "sample", "fetch", "replace"])
    parser.add_argument("--config", default="code/configs/sampling.yaml")
    parser.add_argument("--out", default="data/seed_pool/sampled_documents.jsonl")
    parser.add_argument("--position", help="replace: идентификатор заменяемой позиции")
    parser.add_argument("--reason", help="replace: причина замены (попадает в отчёт отбора)")
    parser.add_argument("--allow-role-change", action="store_true",
                        help="replace: для кандидата в G⊥ — резервная позиция с другой ролью, если нет такой же")
    parser.add_argument("--from-seed-pool", action="store_true",
                        help="replace: для seed-позиции — неиспользованная статья seed pool того же домена")
    parser.add_argument("--only", default=None, help="fetch: только эти позиции (через запятую)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = REPO_ROOT / args.out
    if args.command == "probe":
        probe()
    elif args.command == "snapshot":
        snapshot()
    elif args.command == "sample":
        positions = sample(args.config)
        with open(out, "w", encoding="utf-8") as fh:
            for p in positions:
                fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
        meta = json.loads((SNAPSHOT_DIR / "meta.json").read_text(encoding="utf-8"))
        write_report(positions, SEED_POOL_DIR / "sampling_report.md", meta)
        print(f"{out.relative_to(REPO_ROOT)}: {len(positions)} позиций; отчёт — data/seed_pool/sampling_report.md")
    elif args.command == "fetch":
        fetch(out, only=set(args.only.split(",")) if args.only else None)
    elif args.command == "replace":
        if not args.position or not args.reason:
            raise SystemExit("replace: нужны --position и --reason")
        new = replace(out, args.position, args.reason, args.config,
                      allow_role_change=args.allow_role_change, from_seed_pool=args.from_seed_pool)
        print(f"{args.position} → {new.position_id} ({new.netloc}, {new.published_at}); "
              f"обновлены {out.relative_to(REPO_ROOT)} и data/seed_pool/sampling_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
