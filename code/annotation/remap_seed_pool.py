r"""Перекладка seed pool ``warc_id`` → ``webpage_id / urn_uuid / uri`` (ADR-023).

Ключ ``warc_id`` вида ``trans_txt_<netloc>-<YYYY-MM>.warc_record_<N>.txt`` — имя файла перевода
записи WARC; в ``webmedia.webpages`` такого поля нет. URL и WARC-Record-ID статей сохранились
в заголовках исходных файлов промышленной системы:

* ``og_<stem>`` (каталог ``old_DB/data_ch_en``) — первая строка файла содержит URL статьи;
* ``trans_txt_<stem>`` (каталог ``data_en``) — строки ``URL: …`` и ``WARC: <uuid>``.

Поэтому сопоставление точное: по ``urn_uuid`` (WARC-Record-ID), а при его отсутствии — по
``md5(uri)`` с вариантами написания URL (схема, ``www.``, процентное кодирование, завершающий
слэш). Совпадение подтверждается поиском заголовка статьи из ``og_``-файла в тексте документа.

Стадии:

* ``headers`` — заголовки 143 статей → ``data/seed_pool/warc_headers.csv``;
* ``match`` — поиск в ``webmedia.webpages`` и проверка индекса Qdrant →
  ``data/seed_pool/warc_to_webpage.csv``;
* ``seedpool`` — 388 вопросов с идентификаторами документов и маркерами правил →
  ``data/seed_pool/seed_pool.jsonl``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Sequence
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from code import REPO_ROOT
from code.audit.markers import DATE_ANCHOR, SEED_POOL_RULES, STATIC_RULES, has

SEED_POOL_DIR = REPO_ROOT / "data" / "seed_pool"
HEADERS_CSV = SEED_POOL_DIR / "warc_headers.csv"
MAPPING_CSV = SEED_POOL_DIR / "warc_to_webpage.csv"
SEED_POOL_JSONL = SEED_POOL_DIR / "seed_pool.jsonl"

LEGACY_ROOT = Path("/Users/alexanderbagrov/PycharmProjects/Chinese news/last_version")
DEFAULT_OG_DIR = LEGACY_ROOT / "old_DB" / "data_ch_en"
DEFAULT_TRANS_DIR = LEGACY_ROOT / "data_en"

WARC_RE = re.compile(r"^trans_txt_(?P<netloc>.+)-(?P<month>\d{4}-\d{2})\.warc_record_(?P<n>\d+)\.txt$")
UUID_RE = re.compile(r"^WARC:\s*([0-9a-fA-F-]{36})\s*$")
URL_RE = re.compile(r"^URL:\s*(\S+)\s*$")

HEADER_FIELDS = ["warc_id", "netloc", "warc_month", "record_n", "uri", "warc_uuid", "uri_source", "uuid_source"]
MAPPING_FIELDS = [
    "warc_id", "webpage_id", "urn_uuid", "uri", "published_at", "netloc",
    "match_method", "match_score", "in_qdrant",
]


def load_questions(lang: str) -> list[tuple[str, str]]:
    """Пары ``(вопрос, warc_id)`` в порядке файла промышленной системы."""
    with open(SEED_POOL_DIR / f"{lang}_rag_questions.json", encoding="utf-8") as fh:
        return list(json.load(fh).items())


def seed_warc_ids() -> list[str]:
    return sorted({w for _, w in load_questions("RU")})


def _read_head(path: Path, n: int = 6) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [fh.readline().rstrip("\n") for _ in range(n)]


def og_title(path: Path) -> str | None:
    """Заголовок статьи из ``og_``-файла (вторая строка без суффикса издания)."""
    if not path.exists():
        return None
    lines = [ln.strip() for ln in _read_head(path, 4)]
    title = lines[1] if len(lines) > 1 else ""
    return title.split(" - ")[0].split(" | ")[0].strip() or None


def extract_headers(og_dir: Path, trans_dir: Path) -> list[dict]:
    rows = []
    for warc_id in seed_warc_ids():
        m = WARC_RE.match(warc_id)
        if not m:
            raise ValueError(f"нераспознанный warc_id: {warc_id}")
        stem = warc_id[len("trans_txt_"):]
        row = {
            "warc_id": warc_id, "netloc": m["netloc"], "warc_month": m["month"], "record_n": int(m["n"]),
            "uri": "", "warc_uuid": "", "uri_source": "", "uuid_source": "",
        }
        trans = trans_dir / warc_id
        if trans.exists():
            for line in _read_head(trans):
                if (u := URL_RE.match(line)) and not row["uri"]:
                    row["uri"], row["uri_source"] = u.group(1), "data_en"
                if (w := UUID_RE.match(line)) and not row["warc_uuid"]:
                    row["warc_uuid"], row["uuid_source"] = w.group(1).lower(), "data_en"
        og = og_dir / f"og_{stem}"
        if og.exists():
            first = _read_head(og, 1)[0].strip()
            if first.startswith("http"):
                if row["uri"] and row["uri"] != first:
                    raise ValueError(f"URL в og_ и data_en расходятся: {warc_id}")
                if not row["uri"]:
                    row["uri"], row["uri_source"] = first, "og"
        rows.append(row)
    return rows


def url_variants(uri: str) -> list[str]:
    """Варианты написания URL, под которыми документ мог попасть в ``webmedia.webpages``."""
    parts = urlsplit(uri)
    paths = {parts.path, unquote(parts.path), quote(unquote(parts.path), safe="/%:@!$&'()*+,;=-._~")}
    hosts = {parts.netloc, parts.netloc.removeprefix("www."), "www." + parts.netloc.removeprefix("www.")}
    out = set()
    for scheme in ("https", "http"):
        for host in hosts:
            for path in paths:
                for p in {path, path.rstrip("/"), path.rstrip("/") + "/"}:
                    out.add(urlunsplit((scheme, host, p, parts.query, "")))
    out.discard("")
    return sorted(out)


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def match(headers: list[dict], og_dir: Path) -> list[dict]:
    from code.annotation.corpus import connect_qdrant, connect_webmedia, indexed_webpages

    conn = connect_webmedia()
    rows = []
    cols = "id, uri, urn_uuid::text, date_time, netloc, text_content, text_content_trafilatura"
    with conn.cursor() as cur:
        for h in headers:
            found, method = [], "not_found"
            if h["warc_uuid"]:
                cur.execute(f"SELECT {cols} FROM webmedia.webpages WHERE urn_uuid = %s::uuid", (h["warc_uuid"],))
                found, method = cur.fetchall(), "urn_uuid"
            if not found and h["uri"]:
                cur.execute(f"SELECT {cols} FROM webmedia.webpages WHERE md5(uri) = %s", (_md5(h["uri"]),))
                found, method = cur.fetchall(), "uri_exact"
            if not found and h["uri"]:
                hashes = [_md5(v) for v in url_variants(h["uri"])]
                cur.execute(f"SELECT {cols} FROM webmedia.webpages WHERE md5(uri) = ANY(%s)", (hashes,))
                found, method = cur.fetchall(), "uri_variant"
            if not found and h["uri"]:
                # в корпусе к адресу статьи может быть добавлен заголовок: /article/<номер>/<заголовок>
                prefix = h["uri"].rstrip("/").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                cur.execute(f"SELECT {cols} FROM webmedia.webpages WHERE netloc = %s AND uri LIKE %s",
                            (h["netloc"], prefix + "/%"))
                found, method = cur.fetchall(), "uri_prefix"

            title = og_title(og_dir / f"og_{h['warc_id'][len('trans_txt_'):]}")

            def has_title(rec) -> bool:
                tf = rec[6] or {}
                return title is not None and title in f"{rec[5] or ''}\n{tf.get('title') or ''}\n{tf.get('text') or ''}"

            if len({r[0] for r in found}) > 1 and title is not None:
                # несколько версий одной статьи: остаётся та, в тексте которой есть заголовок исходного файла
                titled = [r for r in found if has_title(r)]
                if len({r[0] for r in titled}) == 1:
                    found, method = titled, f"{method}+title"
                else:
                    # заголовок встречается в тексте нескольких версий: решает совпадение начала заголовка страницы
                    exact = [r for r in titled if ((r[6] or {}).get("title") or "").startswith(title)]
                    if len({r[0] for r in exact}) == 1:
                        found, method = exact, f"{method}+title_exact"
            row ={k: "" for k in MAPPING_FIELDS}
            row.update(warc_id=h["warc_id"], netloc=h["netloc"])
            if not found:
                row["match_method"] = "not_found"
            elif len({r[0] for r in found}) > 1:
                row["match_method"] = f"ambiguous_{method}"
            else:
                wid, uri, urn, dt, netloc, _, _ = found[0]
                row.update(
                    webpage_id=wid, urn_uuid=urn or "", uri=uri, netloc=netloc,
                    published_at=dt.date().isoformat() if dt else "",
                    match_method=method,
                    match_score="" if title is None else (1.0 if has_title(found[0]) else 0.0),
                )
            rows.append(row)
    conn.close()

    client, collection = connect_qdrant()
    ids = [int(r["webpage_id"]) for r in rows if r["webpage_id"] != ""]
    indexed = indexed_webpages(client, collection, ids)  # фрагменты нумеруются с 0
    for r in rows:
        if r["webpage_id"] != "":
            r["in_qdrant"] = int(r["webpage_id"]) in indexed
    return rows


def build_seed_pool(mapping: dict[str, dict]) -> list[dict]:
    ru, en = load_questions("RU"), load_questions("EN")
    if [w for _, w in ru] != [w for _, w in en]:
        raise ValueError("порядок warc_id в RU и EN различается")
    out = []
    for idx, ((q_ru, warc_id), (q_en, _)) in enumerate(zip(ru, en)):
        m = WARC_RE.match(warc_id)
        flags = {rule: has(pattern, q_ru) for rule, (_, pattern) in SEED_POOL_RULES.items()}
        flags["no_date_anchor"] = not has(DATE_ANCHOR["ru"], q_ru)
        mp = mapping.get(warc_id, {})
        wid = mp.get("webpage_id") or None
        out.append({
            "seed_idx": idx,
            "question_ru": q_ru,
            "question_en": q_en,
            "warc_id": warc_id,
            "netloc": m["netloc"],
            "warc_month": m["month"],
            "webpage_id": int(wid) if wid else None,
            "in_qdrant": str(mp.get("in_qdrant")) == "True" if wid else False,
            "markers": flags,
            "static_flag": any(flags[r] for r in STATIC_RULES),
        })
    return out


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(rows: Sequence[dict], path: Path, fields: Sequence[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=["headers", "match", "seedpool", "all"])
    parser.add_argument("--og-dir", type=Path, default=DEFAULT_OG_DIR)
    parser.add_argument("--trans-dir", type=Path, default=DEFAULT_TRANS_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.stage in ("headers", "all"):
        rows = extract_headers(args.og_dir, args.trans_dir)
        write_csv(rows, HEADERS_CSV, HEADER_FIELDS)
        print(f"{HEADERS_CSV.relative_to(REPO_ROOT)}: {len(rows)} статей, "
              f"с URL {sum(bool(r['uri']) for r in rows)}, с UUID {sum(bool(r['warc_uuid']) for r in rows)}")
    if args.stage in ("match", "all"):
        rows = match(read_csv(HEADERS_CSV), args.og_dir)
        write_csv(rows, MAPPING_CSV, MAPPING_FIELDS)
        by_method: dict[str, int] = {}
        for r in rows:
            by_method[r["match_method"]] = by_method.get(r["match_method"], 0) + 1
        print(f"{MAPPING_CSV.relative_to(REPO_ROOT)}: {by_method}; "
              f"в Qdrant {sum(r['in_qdrant'] is True for r in rows)}")
    if args.stage in ("seedpool", "all"):
        mapping = {r["warc_id"]: r for r in read_csv(MAPPING_CSV)} if MAPPING_CSV.exists() else {}
        items = build_seed_pool(mapping)
        with open(SEED_POOL_JSONL, "w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"{SEED_POOL_JSONL.relative_to(REPO_ROOT)}: {len(items)} вопросов, "
              f"с документом {sum(i['webpage_id'] is not None for i in items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
