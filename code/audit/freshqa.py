r"""Устаревание эталонных ответов FreshQA между версиями набора.

FreshQA (Vu et al., 2023) — 600 вопросов с разметкой типа факта ``fact_type``
(never-, slow-, fast-changing) и эталонными ответами ``answer_0`` … ``answer_9``; авторы
регулярно обновляют ответы и публикуют каждую версию отдельной таблицей Google Sheets.
Ссылки на версии перечислены в ``README.md`` репозитория github.com/freshllms/freshqa
и его истории.

Для базовой версии $v_0$ и более поздней версии $v$ вопросы сопоставляются по нормализованному
тексту (идентификаторы между версиями нестабильны). Для каждого вопроса $q$:

* $s_{\mathrm{any}}(q; v) = \mathbb{I}[A^*_v(q) \ne A^*_{v_0}(q)]$ — изменилось множество эталонных
  ответов (канонический ответ и алиасы после нормализации);
* $s_{\mathrm{main}}(q; v) = \mathbb{I}[a^*_{0,v}(q) \ne a^*_{0,v_0}(q)]$ — изменился канонический ответ
  ``answer_0``; это более строгая оценка, не учитывающая добавление алиасов.

Доля устаревших эталонов типа $c$ — среднее индикатора по вопросам этого типа в $v_0$
с 95%-м перцентильным бутстреп-интервалом по вопросам.

Запуск из корня репозитория::

    python -m code.audit.freshqa --collect-versions   # обновить список версий
    python -m code.audit.freshqa                      # загрузка, расчёт, эскиз графика
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT
from code.audit import CACHE_DIR, FIGURES_DIR, RESULTS_DIR

REPO_URL = "https://github.com/freshllms/freshqa.git"
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
VERSIONS_FILE = Path(__file__).with_name("freshqa_versions.json")
FACT_TYPES = ("never-changing", "slow-changing", "fast-changing")

_LINK_RE = re.compile(r"\[FreshQA ([^\]]+?)\]\(https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)")
_SPACES_RE = re.compile(r"\s+")


# --- Список версий ---------------------------------------------------------------------------


def collect_versions(repo_dir: Path) -> list[dict]:
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


def load_versions(path: Path = VERSIONS_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["versions"]


# --- Загрузка и разбор -----------------------------------------------------------------------


def download_version(version: dict, cache_dir: Path = CACHE_DIR / "freshqa") -> Path | None:
    """Скачивает CSV версии в кэш; возвращает путь или ``None``, если таблица недоступна."""
    import requests

    path = cache_dir / f"freshqa_{version['date']}.csv"
    if path.exists() and path.stat().st_size > 0:
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(EXPORT_URL.format(sheet_id=version["sheet_id"]), timeout=60)
    if resp.status_code != 200 or b"question" not in resp.content[:20000]:
        return None
    path.write_bytes(resp.content)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_text(text: str) -> str:
    """Нижний регистр, схлопывание пробелов, снятие внешней пунктуации и кавычек."""
    text = _SPACES_RE.sub(" ", str(text).strip().lower())
    return text.strip(" .?!\"'“”«»")


def read_version(path: Path) -> dict[str, dict]:
    """Читает CSV версии: ``{нормализованный вопрос: {fact_type, false_premise, main, answers}}``.

    В выгрузке над заголовком стоят строки-предупреждения, поэтому заголовок ищется по ячейкам
    ``question`` и ``fact_type``. Вопросы, встречающиеся в версии дважды, отбрасываются.
    """
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    header_idx = next(
        i for i, row in enumerate(rows) if "question" in row and "fact_type" in row
    )
    header = rows[header_idx]
    col = {name: header.index(name) for name in header if name}
    answer_cols = [col[f"answer_{k}"] for k in range(10) if f"answer_{k}" in col]
    out: dict[str, dict] = {}
    duplicates: set[str] = set()
    for row in rows[header_idx + 1:]:
        if len(row) <= col["question"] or not row[col["question"]].strip():
            continue
        key = normalize_text(row[col["question"]])
        answers = [normalize_text(row[c]) for c in answer_cols if c < len(row) and row[c].strip()]
        record = {
            "fact_type": row[col["fact_type"]].strip().lower(),
            "false_premise": row[col["false_premise"]].strip().upper() == "TRUE" if "false_premise" in col else False,
            "main": answers[0] if answers else "",
            "answers": frozenset(answers),
        }
        if key in out:
            duplicates.add(key)
        out[key] = record
    for key in duplicates:
        out.pop(key, None)
    return out


# --- Сравнение версий ------------------------------------------------------------------------


def staleness_rows(
    base: dict[str, dict], later: dict[str, dict], base_date: str, later_date: str,
    B: int = 10000, seed: int = 20260917,
) -> list[dict]:
    """Строки таблицы устаревания для пары версий $(v_0, v)$ по каждому типу факта и определению."""
    import pandas as pd

    from code.eval.stats import bootstrap_mean_ci

    months = (pd.Timestamp(later_date) - pd.Timestamp(base_date)).days / 30.4375
    common = [q for q in base if q in later]
    rows = []
    for fact_type in FACT_TYPES:
        qs = [q for q in common if base[q]["fact_type"] == fact_type]
        for definition in ("any", "main"):
            if definition == "any":
                values = [float(base[q]["answers"] != later[q]["answers"]) for q in qs]
            else:
                values = [float(base[q]["main"] != later[q]["main"]) for q in qs]
            ci = bootstrap_mean_ci(values, B=B, seed=seed)
            rows.append({
                "base_version": base_date,
                "version": later_date,
                "months": round(months, 2),
                "fact_type": fact_type,
                "definition": definition,
                "n": ci.n,
                "changed": int(sum(values)),
                "rate": ci.mean,
                "ci_low": ci.ci_low,
                "ci_high": ci.ci_high,
            })
    return rows


def pick_quarterly(dates: Sequence[str]) -> list[str]:
    """Последняя доступная версия каждого календарного квартала."""
    by_quarter: dict[str, str] = {}
    for d in sorted(dates):
        year, month = int(d[:4]), int(d[5:7])
        by_quarter[f"{year}Q{(month - 1) // 3 + 1}"] = d
    return sorted(by_quarter.values())


# --- Эскиз графика ---------------------------------------------------------------------------


def plot_sketch(rows: list[dict], out_stem: Path) -> None:
    """Эскиз графика ошибок: доля устаревших эталонов по типам вопросов от прошедшего времени."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = {
        "never-changing": "статические (never-changing)",
        "slow-changing": "медленно меняющиеся",
        "fast-changing": "быстро меняющиеся",
    }
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for fact_type in FACT_TYPES:
        pts = sorted(
            (r for r in rows if r["fact_type"] == fact_type and r["definition"] == "any"),
            key=lambda r: r["months"],
        )
        x = [r["months"] for r in pts]
        y = [100 * r["rate"] for r in pts]
        err = [[100 * (r["rate"] - r["ci_low"]) for r in pts], [100 * (r["ci_high"] - r["rate"]) for r in pts]]
        ax.errorbar(x, y, yerr=err, marker="o", capsize=3, label=labels[fact_type])
    ax.set_xlabel("Прошло месяцев с базовой версии")
    ax.set_ylabel("Доля изменившихся эталонных ответов, %")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend(loc="center right")
    ax.set_title("FreshQA: устаревание эталона (эскиз, 95% интервалы)")
    fig.tight_layout()
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_stem.with_suffix(".pdf"))
    fig.savefig(out_stem.with_suffix(".png"), dpi=200)
    plt.close(fig)


# --- Точка входа -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collect-versions", action="store_true",
                        help="клонировать репозиторий FreshQA и обновить freshqa_versions.json")
    parser.add_argument("--versions", choices=("quarterly", "all"), default="quarterly",
                        help="какие поздние версии сравнивать с базовой")
    parser.add_argument("--B", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--out", default=str(RESULTS_DIR / "freshqa_staleness.csv"))
    parser.add_argument("--figure", default=str(FIGURES_DIR / "freshqa_staleness_sketch"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.collect_versions:
        repo_dir = CACHE_DIR / "freshqa_repo"
        if not repo_dir.exists():
            subprocess.run(["git", "clone", "-q", REPO_URL, str(repo_dir)], check=True)
        versions = collect_versions(repo_dir)
        for v in versions:
            v["exportable"] = download_version(v) is not None
        VERSIONS_FILE.write_text(
            json.dumps({"source": REPO_URL, "export_url": EXPORT_URL, "versions": versions},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"версий: {len(versions)}, доступно для выгрузки: {sum(v['exportable'] for v in versions)}")
        return 0

    versions = [v for v in load_versions() if v.get("exportable")]
    base_v, later_vs = versions[0], versions[1:]
    if args.versions == "quarterly":
        keep = set(pick_quarterly([v["date"] for v in later_vs]))
        later_vs = [v for v in later_vs if v["date"] in keep]

    base_path = download_version(base_v)
    base = read_version(base_path)
    rows, sources = [], [{"version": base_v["date"], "sha256": sha256(base_path), "questions": len(base)}]
    for v in later_vs:
        path = download_version(v)
        if path is None:
            continue
        later = read_version(path)
        sources.append({"version": v["date"], "sha256": sha256(path), "questions": len(later)})
        rows.extend(staleness_rows(base, later, base_v["date"], v["date"], B=args.B, seed=args.seed))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(out.with_name("freshqa_sources.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sources[0]))
        writer.writeheader()
        writer.writerows(sources)
    plot_sketch(rows, Path(args.figure))
    print(f"базовая версия {base_v['date']}, сравнено версий: {len(sources) - 1}; таблица: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
