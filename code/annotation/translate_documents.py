r"""Перевод документов позиций на русский для разметки (ADR-025).

Переводчик — модель машинного перевода Hy-MT2 на OpenAI-совместимом сервере ИВ РАН
(``code/configs/translation.yaml``); в $\mathcal{L}$ она не входит. Перевод идёт по абзацам —
непустым строкам ``text_zh``; предыдущий абзац передаётся как контекст по шаблону авторов модели.
Так оригинал и перевод выравниваются абзац к абзацу для показа рядом, а длина ответа не упирается
в ограничение генерации. Абзац длиннее ``max_piece_chars`` делится по границам предложений.

Каждый документ сохраняется в ``data/_cache/translations/<webpage_id>.json`` (в репозиторий не
входит): абзацы ``{i, zh, ru, prompt}``, фактическая модель из поля ``model`` ответа (ADR-009),
параметры, идентификатор промпта, дата, SHA-256 перевода и автоматические проверки. Повторный
запуск переводит только недостающие документы.

Проверки — подсказки координатору и читающему по-китайски аннотатору, а не исправление:
числа оригинала есть в переводе; 万/亿 — сверить порядок величины; иероглифы в переводе вне
скобок; отношение длин перевода и оригинала; повторы предложений; пустой перевод. Абзац с пустым
переводом, повтором или иероглифами переводится ещё раз без контекста, остаётся лучший вариант.

Запуск: ``python -m code.annotation.translate_documents --pilot`` (``--probe`` — проверка модели
на одной фразе, ``--report`` — только отчёт по готовому кэшу).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config, load_env
from code.annotation.generate_drafts import load_document, load_positions

DEFAULT_CONFIG = "code/configs/translation.yaml"

SENTENCE_END = re.compile(r"(?<=[。！？!?])")
PARAGRAPH_END = re.compile(r"[。！？!?…」』”）)]$")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
HANZI = re.compile(r"[㐀-鿿]")
PARENS = re.compile(r"\([^)]*\)|（[^）]*）")
WAN_YI = re.compile(r"\d\s*[万萬亿億]")
ZH_NOT_LITERAL = re.compile(r"\d+(?:[.,]\d+)*\s*(?:月|[万萬亿億])")
RU_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def unwrap_lines(lines: list[str]) -> list[str]:
    """Склейка строк, перенесённых по ширине: если у документа есть типичная ширина строки (≥ 4 строк
    одной длины и ≥ 30 % длинных строк), строка этой ширины без знака конца предложения продолжается
    следующей. Заголовки, списки и таблицы без переноса по ширине не затрагиваются."""
    widths = Counter(len(line) for line in lines if len(line) >= 20)
    if not widths:
        return lines
    width, count = widths.most_common(1)[0]
    if count < 4 or count < 0.3 * sum(widths.values()):
        return lines
    out: list[str] = []
    cut = False
    for line in lines:
        if cut:
            out[-1] += line
        else:
            out.append(line)
        cut = width - 3 <= len(line) <= width and not PARAGRAPH_END.search(line)
    return out


def split_paragraphs(text: str, max_chars: int) -> list[str]:
    """Абзацы документа: непустые строки (перенос по ширине склеивается); строка длиннее
    ``max_chars`` делится по концам предложений."""
    pieces: list[str] = []
    for line in unwrap_lines([s.strip() for s in (text or "").splitlines() if s.strip()]):
        if len(line) <= max_chars:
            pieces.append(line)
            continue
        buf = ""
        for sent in filter(None, SENTENCE_END.split(line)):
            if buf and len(buf) + len(sent) > max_chars:
                pieces.append(buf)
                buf = ""
            buf += sent
        if buf:
            pieces.append(buf)
    return pieces


class Translator:
    """Клиент модели перевода: шаблоны авторов, temperature из конфигурации, проверка модели (ADR-009)."""

    def __init__(self, cfg: dict):
        from openai import OpenAI

        if not cfg.get("base_url") or not cfg.get("api_key"):
            raise RuntimeError("нет IVRAN_LLM_BASE_URL или IVRAN_LLM_API_KEY в .env (см. code/README.md)")
        self.cfg = cfg
        self.model = cfg["model"]
        self.client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"],
                             timeout=cfg["timeout"], max_retries=cfg["max_retries"])

    def check_model(self) -> None:
        """Модель есть в ``/models`` провайдера, иначе прогон не начинается."""
        ids = [m.id for m in self.client.models.list().data]
        if self.model not in ids:
            raise RuntimeError(f"модели {self.model} нет у провайдера; доступны: {', '.join(ids)}")

    def translate(self, source: str, direction: str = "zh_ru", context: str | None = None) -> tuple[str, str]:
        """Перевод одного фрагмента; возвращает (перевод, фактическая модель)."""
        key = f"{direction}_ctx" if context else direction
        prompt = self.cfg["prompts"][key].replace("{context}", context or "").replace("{source}", source)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.cfg["temperature"],
            max_tokens=min(self.cfg["max_tokens"], 64 + 4 * len(source)),
        )
        # llama.cpp за llama-swap возвращает в model путь к файлу весов: «/models/hf/<id>.gguf»
        if resp.model != self.model and Path(resp.model).stem != self.model:
            raise RuntimeError(f"ответила модель {resp.model} вместо {self.model} (ADR-009)")
        return (resp.choices[0].message.content or "").strip(), resp.model


# ---------------------------------------------------------------- проверки

def _numbers(text: str) -> Counter:
    # полноширинные цифры и знаки («５８﹒７０») приводятся к ASCII; разделители тысяч и пробелы внутри
    # чисел не различаем: «1,234», «1 234» и «1234» — одно число
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\d)[\s  ](?=\d{3}\b)", "", text)
    return Counter(re.sub(r"[.,](?=\d{3}\b)", "", n).replace(",", ".") for n in NUMBER.findall(text))


def paragraph_flags(zh: str, ru: str, checks: dict) -> list[str]:
    """Сработавшие проверки абзаца.

    Номера месяцев («5月» → «мая») и числа перед 万/亿 («64萬» → «640 тысяч») переводятся словами
    или пересчитываются, поэтому в проверку чисел не входят; числа перед 万/亿 отмечаются ``wan_yi``.
    """
    flags = []
    if not ru:
        return ["empty"]
    if _numbers(ZH_NOT_LITERAL.sub(" ", unicodedata.normalize("NFKC", zh))) - _numbers(ru):
        flags.append("numbers")
    if WAN_YI.search(zh):
        flags.append("wan_yi")
    if HANZI.search(PARENS.sub("", ru)):
        flags.append("hanzi")
    if len(zh) >= checks["ratio_min_len"] and not checks["ratio_min"] <= len(ru) / len(zh) <= checks["ratio_max"]:
        flags.append("ratio")
    sents = [s for s in RU_SENTENCE.split(ru) if len(s) >= 20]
    if len(sents) != len(set(sents)):
        flags.append("repeat")
    return flags


RETRY_FLAGS = {"empty", "repeat", "hanzi"}


# ---------------------------------------------------------------- документ

def translate_document(doc: dict, translator: Translator, cfg: dict) -> dict:
    """Перевод документа по абзацам с контекстом предыдущего абзаца и проверками."""
    zh_pars = split_paragraphs(doc.get("text_zh") or "", cfg["max_piece_chars"])
    paragraphs, models = [], set()
    for i, zh in enumerate(zh_pars):
        context = zh_pars[i - 1] if i else None
        ru, model = translator.translate(zh, "zh_ru", context)
        models.add(model)
        flags, prompt = paragraph_flags(zh, ru, cfg["checks"]), "ctx" if context else "plain"
        if RETRY_FLAGS & set(flags) and context:
            ru2, _ = translator.translate(zh, "zh_ru")
            flags2 = paragraph_flags(zh, ru2, cfg["checks"])
            if len(RETRY_FLAGS & set(flags2)) < len(RETRY_FLAGS & set(flags)):
                ru, flags, prompt = ru2, flags2, "plain_retry"
        paragraphs.append({"i": i, "zh": zh, "ru": ru, "prompt": prompt, "flags": flags})
    ru_all = "\n".join(p["ru"] for p in paragraphs)
    return {
        "webpage_id": doc["webpage_id"],
        "model": sorted(models)[0] if len(models) == 1 else sorted(models),
        "params": {"temperature": cfg["temperature"], "max_piece_chars": cfg["max_piece_chars"]},
        "prompt_id": cfg["prompt_id"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paragraphs": paragraphs,
        "sha256": hashlib.sha256(ru_all.encode("utf-8")).hexdigest(),
        "checks": dict(Counter(f for p in paragraphs for f in p["flags"])),
    }


def translation_path(cfg: dict, webpage_id: int) -> Path:
    return REPO_ROOT / cfg["paths"]["out"] / f"{webpage_id}.json"


def translate_positions(positions: Sequence[dict], cfg: dict, workers: int, force: bool = False) -> None:
    """Перевод документов позиций; готовые документы пропускаются (кроме ``force``)."""
    out_dir = REPO_ROOT / cfg["paths"]["out"]
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in positions if force or not translation_path(cfg, p["webpage_id"]).exists()]
    print(f"документов: {len(positions)}, к переводу: {len(todo)}", file=sys.stderr)
    if not todo:
        return
    translator = Translator(cfg)
    translator.check_model()
    docs = {p["webpage_id"]: load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"]) for p in todo}
    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(translate_document, docs[p["webpage_id"]], translator, cfg): p for p in todo}
        for done, future in enumerate(as_completed(futures), 1):
            p = futures[future]
            try:
                result = future.result()
            except RuntimeError:
                pool.shutdown(cancel_futures=True)
                raise
            translation_path(cfg, p["webpage_id"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            print(f"[{done}/{len(todo)}] {p['position_id']} {p['webpage_id']}: {len(result['paragraphs'])} абз., "
                  f"проверки {result['checks'] or '—'} ({time.time() - started:.0f} с)", file=sys.stderr)


# ---------------------------------------------------------------- отчёт

def recheck(positions: Sequence[dict], cfg: dict) -> None:
    """Пересчёт проверок по готовому кэшу (после правки правил) без повторного перевода."""
    for p in positions:
        path = translation_path(cfg, p["webpage_id"])
        if not path.exists():
            continue
        tr = json.loads(path.read_text(encoding="utf-8"))
        for par in tr["paragraphs"]:
            par["flags"] = paragraph_flags(par["zh"], par["ru"], cfg["checks"])
        tr["checks"] = dict(Counter(f for par in tr["paragraphs"] for f in par["flags"]))
        path.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")


def write_report(positions: Sequence[dict], cfg: dict) -> str:
    """Отчёт по переводам без текстов: абзацы и сработавшие проверки по документам."""
    kinds = ["empty", "numbers", "wan_yi", "hanzi", "ratio", "repeat"]
    rows, total, missing, models = [], Counter(), [], set()
    n_par = 0
    for p in positions:
        path = translation_path(cfg, p["webpage_id"])
        if not path.exists():
            missing.append(p["position_id"])
            continue
        tr = json.loads(path.read_text(encoding="utf-8"))
        models.add(str(tr["model"]))
        checks = Counter(tr["checks"])
        total.update(checks)
        n_par += len(tr["paragraphs"])
        retried = sum(par["prompt"] == "plain_retry" for par in tr["paragraphs"])
        rows.append(f"| {p['position_id']} | {p['webpage_id']} | {p['region']} | {len(tr['paragraphs'])} | "
                    + " | ".join(str(checks.get(k, 0)) for k in kinds) + f" | {retried} |")
    lines = [
        "# Перевод документов пилота (ADR-025)",
        "",
        f"Модель: {', '.join(sorted(models)) or '—'}; промпт `{cfg['prompt_id']}` (шаблоны авторов модели, "
        f"`code/configs/translation.yaml`); temperature {cfg['temperature']}; по абзацам, контекст — предыдущий абзац.",
        f"Документов: {len(rows)} из {len(positions)}; абзацев: {n_par}. Тексты переводов в репозиторий не входят "
        "(`data/_cache/translations/`).",
        "",
        "Проверки — подсказки, а не ошибки: `numbers` — число оригинала не найдено в переводе (номера месяцев "
        "и числа перед 万/亿 не проверяются); `wan_yi` — в оригинале 万/亿, сверить порядок величины; `hanzi` — иероглифы в переводе "
        "вне скобок; `ratio` — необычное отношение длин; `repeat` — повтор предложения; `retry` — абзац переведён "
        "повторно без контекста.",
        "",
        "| Позиция | webpage_id | Регион | Абзацев | " + " | ".join(kinds) + " | retry |",
        "|---|---|---|---|" + "---|" * (len(kinds) + 1),
        *rows,
        "",
        "Итого по проверкам: " + (", ".join(f"{k} — {total[k]}" for k in kinds if total[k]) or "нет срабатываний") + ".",
    ]
    if missing:
        lines.append(f"Нет перевода: {', '.join(missing)}.")
    report = REPO_ROOT / cfg["paths"]["report"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines[3:5] + lines[-2:])


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--pilot", action="store_true", help="только документы пилота")
    parser.add_argument("--limit", type=int, default=None, help="не больше N документов (отладка)")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="перевести заново и готовые документы")
    parser.add_argument("--probe", action="store_true", help="проверить модель на одной фразе")
    parser.add_argument("--report", action="store_true", help="пересчёт проверок и отчёт по готовому кэшу")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(REPO_ROOT / args.config)
    if args.probe:
        translator = Translator(cfg)
        translator.check_model()
        started = time.time()
        ru, model = translator.translate("香港特區政府今日宣布，2023年第一季本地生產總值按年實質上升2.7%。")
        print(f"{model} ({time.time() - started:.1f} с): {ru}")
        return 0
    positions = load_positions(REPO_ROOT / cfg["paths"]["positions"], pilot=args.pilot)[: args.limit]
    if args.report:
        recheck(positions, cfg)
    else:
        translate_positions(positions, cfg, args.workers or cfg["workers"], force=args.force)
    print(write_report(positions, cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
