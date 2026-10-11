r"""Загрузка сторонних наборов вопросов в кэш ``data/external/``.

Версии зафиксированы, чтобы повторный запуск давал те же файлы:

* FreshQA — 75 доступных для выгрузки таблиц Google Sheets из ``freshqa_versions.json``;
  список собирается по истории ``README.md`` репозитория github.com/freshllms/freshqa;
* RGB, CDQA, ChronoQA — файлы репозиториев GitHub на зафиксированных коммитах;
* DRAGOn — parquet-файлы наборов Hugging Face ``ai-forever/hist-rag-bench-*`` на тегах
  первой (1.0.0) и последней (1.15.0) версий.

Повторная загрузка пропускает уже скачанные файлы. Запуск: ``python -m code.audit --stage download``;
обновить список версий FreshQA: ``python -m code.audit.download --collect-freshqa-versions``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Sequence

from code.audit import CACHE_DIR

# --- Адреса и версии -------------------------------------------------------------------------

FRESHQA_REPO = "https://github.com/freshllms/freshqa.git"
FRESHQA_EXPORT = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
FRESHQA_VERSIONS_FILE = Path(__file__).with_name("freshqa_versions.json")

RGB_COMMIT = "65ec39e40e7dc9abb50e9bf1b4f32be3f6f16615"
CDQA_COMMIT = "ba4b198c1e8ea0761bb238870270777e32c29c5b"
CHRONOQA_COMMIT = "dba13ba1d39a2307cfb6b0b8ba1b723860c07c87"
DRAGON_TAGS = ("1.0.0", "1.15.0")

GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"
HF_RESOLVE = "https://huggingface.co/datasets/ai-forever/hist-rag-bench-{name}/resolve/{tag}/data/train-00000-of-00001.parquet"


def static_files() -> list[dict]:
    """Файлы RGB, CDQA, ChronoQA и DRAGOn: ``{dataset, version, url, path}``."""
    files = []
    for name in ("en", "en_refine", "zh", "zh_refine"):
        files.append({
            "dataset": "RGB", "version": RGB_COMMIT[:7],
            "url": GITHUB_RAW.format(repo="chen700564/RGB", commit=RGB_COMMIT, path=f"data/{name}.json"),
            "path": CACHE_DIR / "rgb" / f"{name}.json",
        })
    files.append({
        "dataset": "CDQA", "version": CDQA_COMMIT[:7],
        "url": GITHUB_RAW.format(repo="Alibaba-NLP/CDQA", commit=CDQA_COMMIT, path="CDQA_v1.json"),
        "path": CACHE_DIR / "cdqa" / "CDQA_v1.json",
    })
    files.append({
        "dataset": "ChronoQA", "version": CHRONOQA_COMMIT[:7],
        "url": GITHUB_RAW.format(repo="czy1999/ChronoQA", commit=CHRONOQA_COMMIT, path="chronoqa.json"),
        "path": CACHE_DIR / "chronoqa" / "chronoqa.json",
    })
    for tag in DRAGON_TAGS:
        files.append({
            "dataset": "DRAGOn", "version": tag,
            "url": HF_RESOLVE.format(name="private-qa", tag=tag),
            "path": CACHE_DIR / "dragon" / f"private-qa-{tag}.parquet",
        })
    return files


# --- FreshQA ---------------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[FreshQA ([^\]]+?)\]\(https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)")


def collect_freshqa_versions(repo_dir: Path) -> list[dict]:
    """Собирает пары «дата версии — идентификатор таблицы» из всех редакций ``README.md``.

    Редакции просматриваются по времени, и для каждой таблицы сохраняется дата из последней
    редакции. Так исправляются переименования и опечатки в подписях: одна таблица, подписанная
    сначала «Oct 6, 2023», затем «Oct 15, 2023», или «April 21, 2025» вместо «April 21, 2026»,
    даёт одну версию с последней датой.
    """
    import pandas as pd

    shas = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--reverse", "--format=%H", "--", "README.md"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    date_by_id: dict[str, str] = {}
    for sha in shas:
        text = subprocess.run(
            ["git", "-C", str(repo_dir), "show", f"{sha}:README.md"],
            check=True, capture_output=True, text=True,
        ).stdout
        for label, sheet_id in _LINK_RE.findall(text):
            date = pd.to_datetime(label.strip().rstrip("."), errors="coerce")
            if pd.isna(date):
                continue
            date_by_id[sheet_id] = date.strftime("%Y-%m-%d")
    by_date: dict[str, str] = {}
    for sheet_id, date in date_by_id.items():
        by_date[date] = sheet_id
    return [{"date": d, "sheet_id": by_date[d]} for d in sorted(by_date)]


def load_freshqa_versions(path: Path = FRESHQA_VERSIONS_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["versions"]


def freshqa_path(version: dict) -> Path:
    return CACHE_DIR / "freshqa" / f"freshqa_{version['date']}.csv"


def download_freshqa_version(version: dict) -> Path | None:
    """Скачивает CSV версии FreshQA; возвращает путь или ``None``, если таблица недоступна."""
    import requests

    path = freshqa_path(version)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(FRESHQA_EXPORT.format(sheet_id=version["sheet_id"]), timeout=60)
    if resp.status_code != 200 or b"question" not in resp.content[:20000]:
        return None
    path.write_bytes(resp.content)
    return path


def update_freshqa_versions() -> list[dict]:
    """Клонирует репозиторий FreshQA, собирает версии, проверяет выгрузку и обновляет JSON."""
    repo_dir = CACHE_DIR / "freshqa_repo"
    if not repo_dir.exists():
        subprocess.run(["git", "clone", "-q", FRESHQA_REPO, str(repo_dir)], check=True)
    versions = collect_freshqa_versions(repo_dir)
    for v in versions:
        v["exportable"] = download_freshqa_version(v) is not None
    FRESHQA_VERSIONS_FILE.write_text(
        json.dumps({"source": FRESHQA_REPO, "export_url": FRESHQA_EXPORT, "versions": versions},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return versions


# --- Загрузка всего --------------------------------------------------------------------------


def download_file(url: str, path: Path) -> Path:
    import requests

    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=600)
    resp.raise_for_status()
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(path)
    return path


def download_all() -> None:
    versions = [v for v in load_freshqa_versions() if v.get("exportable")]
    missing = [v["date"] for v in versions if download_freshqa_version(v) is None]
    print(f"FreshQA: {len(versions) - len(missing)} из {len(versions)} версий в кэше"
          + (f"; недоступны: {', '.join(missing)}" if missing else ""))
    for f in static_files():
        download_file(f["url"], f["path"])
        print(f"{f['dataset']} {f['version']}: {f['path'].name}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collect-freshqa-versions", action="store_true",
                        help="клонировать репозиторий FreshQA и обновить freshqa_versions.json")
    args = parser.parse_args(argv)
    if args.collect_freshqa_versions:
        versions = update_freshqa_versions()
        print(f"версий: {len(versions)}, доступно для выгрузки: {sum(v['exportable'] for v in versions)}")
        return 0
    download_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
