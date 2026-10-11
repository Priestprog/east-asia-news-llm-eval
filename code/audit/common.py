r"""Общие функции аудита: нормализация текста, доли с бутстреп-интервалом, запись таблиц.

Каждая измеряемая величина аудита — доля объектов (вопросов), обладающих свойством:
$\bar s = \frac{1}{n}\sum_{i=1}^{n} s_i$, $s_i \in \{0, 1\}$, с 95%-м перцентильным
бутстреп-интервалом по объектам ($B = 10^4$, фиксированный seed из ``code/configs/eval.yaml``).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable, Sequence

from code import REPO_ROOT
from code.audit import B, RESULTS_DIR, SEED

_SPACES_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Нижний регистр, схлопывание пробелов, снятие внешней пунктуации и кавычек."""
    text = _SPACES_RE.sub(" ", str(text).replace("﻿", "").strip().lower())
    return text.strip(" .?!？。\"'“”«»")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def share(values: Sequence[bool | float], B: int = B, seed: int = SEED) -> dict:
    """Доля единиц в ``values`` и её 95%-й перцентильный бутстреп-интервал."""
    from code.eval.stats import bootstrap_mean_ci

    floats = [float(v) for v in values]
    ci = bootstrap_mean_ci(floats, B=B, seed=seed)
    return {
        "n": ci.n,
        "count": int(sum(floats)),
        "rate": ci.mean,
        "ci_low": ci.ci_low,
        "ci_high": ci.ci_high,
    }


def write_csv(rows: Sequence[dict], path: Path) -> Path:
    """Пишет строки в CSV (UTF-8, заголовок по ключам первой строки) и возвращает путь."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def record_sources(dataset: str, rows: Iterable[dict], path: Path = RESULTS_DIR / "sources.csv") -> None:
    """Обновляет в ``sources.csv`` строки набора ``dataset``: файл, адрес, sha256, число записей.

    Строки других наборов сохраняются, поэтому модули расчёта можно запускать по отдельности.
    """
    fields = ["dataset", "version", "file", "url", "sha256", "records"]
    kept = [r for r in read_csv(path) if r["dataset"] != dataset] if Path(path).exists() else []
    new = [{k: r.get(k, "") for k in fields} | {"dataset": dataset} for r in rows]
    write_csv(sorted(kept + new, key=lambda r: (r["dataset"], r["version"], r["file"])), path)


def rel(path: Path) -> str:
    """Путь относительно корня репозитория для сообщений и таблиц."""
    return str(Path(path).resolve().relative_to(REPO_ROOT))
