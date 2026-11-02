r"""Черновики записей эталонной выборки моделью $\ell_{\mathrm{draft}} \notin \mathcal{L}$ (ADR-022, ADR-023).

Позиция — документ корпуса из ``data/seed_pool/sampled_documents.jsonl``; по каждой позиции
генератор $g_{\mathrm{draft}}$ формирует один кортеж $(q, a, S, \text{evidence}, \text{тип}, \text{дата})$:
вопрос на русском с явной датой-якорем, канонический ответ и алиасы, $S = \{\iota_j\}$ —
документ позиции, evidence-span на китайском и русском, тип вопроса, категорию, метку
инвариантности и сложность. Задание зависит от роли позиции:

* ``answerable`` — вопрос по документу; для статей seed pool за основу берётся один из исходных
  вопросов промышленной системы (``seed_refs``), переформулированный по правилам $E_1$–$E_5$;
* ``dynamic_control`` — контроль применения правил: вопросом служит исходный вопрос seed pool
  с маркером $E_1$ или $E_4$ без изменений, модель заполняет остальные поля;
* ``unanswerable_candidate`` — кандидат в $G^{\bot}$: вопрос с верной предпосылкой, ответа на
  который в документе нет; проверка выдачей ретривера ($K = 20$) выполняется при подготовке листов.

Черновик — только заготовка: в $G$ запись попадает после независимой разметки $R = 3$
аннотаторами. Промпт, модель и параметры — ``code/configs/drafts.yaml``. Параметр
``temperature`` у модели черновиков недоступен, поэтому воспроизводимость обеспечивается
не детерминизмом генерации, а хранением черновика без изменений (``provenance.draft``)
вместе с фактическим полем ``model`` ответа и ``request_id``.

К каждому черновику добавляются автоматические проверки (``checks``): формат даты-якоря по
схеме выборки, наличие даты в тексте вопроса, эвристики правил $E_1$, $E_2$, $E_4$
(``code/audit/markers.py``), дословное вхождение ``evidence_span_zh`` в текст документа.
Это подсказки координатору, а не разметка.

Запуск пилота (30 позиций): ``python -m code.annotation.generate_drafts --pilot``; основной раунд
(270 позиций без пилота) — ``--main``. Повторный запуск дописывает только недостающие позиции.

Основной раунд идёт с промптом ``draft-v2`` (``--prompt draft-v2``, ADR-026): по документу модель
предлагает меню — до одного кандидата на каждый тип вопроса с оценкой ``fit``, — а один кандидат
на позицию выбирает :mod:`code.annotation.balance_types` так, чтобы типы вопроса были представлены
поровну. Меню собираются только через ``--export-requests`` / ``--import-responses``
(``data/golden_set/drafts/candidates.jsonl``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config, load_env
from code.audit.markers import DATE_ANCHOR, SEED_POOL_RULES, STATIC_RULES, has

DEFAULT_CONFIG = "code/configs/drafts.yaml"

QUESTION_TYPES = ["who", "what", "when", "where", "how_many", "which", "yes_no", "list"]
CATEGORIES = ["politics", "economy", "society", "international", "security", "technology",
              "culture", "health", "environment", "other"]
ANSWER_TYPES = ["entity", "person", "organization", "location", "date", "number", "quantity",
                "percentage", "boolean", "list", "short_text"]
LABELS = ["never_changing", "slow_changing_anchored"]
DIFFICULTIES = ["easy", "medium", "hard"]

# Формат даты-якоря — как в data/golden_set/schema.json (time_invariance.anchor_date).
ANCHOR_RE = re.compile(r"^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?|-Q[1-4]|-H[12])?$")
EVIDENCE_MAX = 300

# Схема ответа модели (structured outputs). Пустая строка и -1 вместо null.
DRAFT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "suitable": {"type": "boolean"},
        "unsuitable_reason": {"type": "string"},
        "question_ru": {"type": "string"},
        "answer_canonical": {"type": "string"},
        "answer_aliases": {"type": "array", "items": {"type": "string"}},
        "answer_type": {"type": "string", "enum": ANSWER_TYPES},
        "evidence_span_zh": {"type": "string"},
        "evidence_span_ru": {"type": "string"},
        "question_type": {"type": "string", "enum": QUESTION_TYPES},
        "category": {"type": "string", "enum": CATEGORIES},
        "anchor_date": {"type": "string"},
        "time_invariance_label": {"type": "string", "enum": LABELS},
        "difficulty": {"type": "string", "enum": DIFFICULTIES},
        "seed_question_used": {"type": "integer"},
        "coordinator_note": {"type": "string"},
    },
    "required": ["suitable", "unsuitable_reason", "question_ru", "answer_canonical", "answer_aliases",
                 "answer_type", "evidence_span_zh", "evidence_span_ru", "question_type", "category",
                 "anchor_date", "time_invariance_label", "difficulty", "seed_question_used",
                 "coordinator_note"],
    "additionalProperties": False,
}

# Промпт с mode = menu (draft-v2, ADR-026): по документу — кандидаты, не больше одного на тип вопроса;
# у каждого — поля черновика без suitable/unsuitable_reason (они относятся к документу) и оценка fit.
CANDIDATE_SCHEMA: dict = {
    "type": "object",
    "properties": {**{k: v for k, v in DRAFT_SCHEMA["properties"].items() if k not in ("suitable", "unsuitable_reason")},
                   "fit": {"type": "integer", "enum": [1, 2, 3]}},
    "required": [k for k in DRAFT_SCHEMA["required"] if k not in ("suitable", "unsuitable_reason")] + ["fit"],
    "additionalProperties": False,
}
MENU_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "suitable": {"type": "boolean"},
        "unsuitable_reason": {"type": "string"},
        "candidates": {"type": "array", "items": CANDIDATE_SCHEMA, "minItems": 1, "maxItems": len(QUESTION_TYPES)},
    },
    "required": ["suitable", "unsuitable_reason", "candidates"],
    "additionalProperties": False,
}


def is_menu(prompt: dict) -> bool:
    return prompt.get("mode") == "menu"


@dataclass
class Draft:
    """Черновик по позиции; поля ``question_ru``, ``answer_canonical``, ``answer_aliases`` и
    ``supporting_ids`` переносятся в ``provenance.draft`` записи ``data/golden_set/schema.json``."""

    position_id: str
    webpage_id: int
    role: str
    origin: str
    pilot: bool
    question_ru: str = ""
    answer_canonical: str | None = None          # None — кандидат в G⊥
    answer_aliases: list[str] = field(default_factory=list)
    answer_type: str = ""
    supporting_ids: list[int] = field(default_factory=list)   # S ⊂ I
    evidence_span_zh: str = ""
    evidence_span_ru: str = ""
    question_type: str = ""
    category: str = ""
    anchor_date: str = ""
    time_invariance_label: str = ""
    difficulty: str = ""
    requires_multi_doc: bool = False
    answerable: bool = True                      # False — кандидат в G⊥
    suitable: bool = True
    unsuitable_reason: str = ""
    coordinator_note: str = ""
    seed_pool_ref: str | None = None             # seed_idx исходного вопроса seed pool
    draft_model: str = ""                        # фактическое поле model ответа
    draft_prompt_id: str = ""
    channel: str = "api"                         # api | session (запрос выполнен вне API, см. export_requests)
    request_id: str | None = None
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)
    error: str | None = None
    checks: dict = field(default_factory=dict)
    created_at: str = ""


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_positions(path: str | Path, pilot: bool = False, include_reserve: bool = False,
                   main: bool = False) -> list[dict]:
    """Позиции для черновиков: пилот (30), основной раунд без пилота (``main``, 270) либо все основные
    (300), по желанию с резервом (60). Заменённые позиции не возвращаются; резервная позиция после
    замены (``sample_documents replace``) получает ``reserve = false`` и попадает в выборку сама."""
    positions = [p for p in read_jsonl(path) if not p.get("replaced_by")]
    if pilot:
        return [p for p in positions if p["pilot"]]
    if main:
        return [p for p in positions if not p["pilot"] and not p["reserve"]]
    return [p for p in positions if include_reserve or not p["reserve"]]


def round_positions(cfg: dict) -> list[dict]:
    """Позиции раунда разметки по ключу ``selection`` конфигурации разметки (``code/configs/annotation*.yaml``):
    ``pilot`` (по умолчанию, 30), ``main`` (270 без пилота) или ``pool`` (все 300 основных позиций — единый
    пул разметки, ADR-027)."""
    selection = cfg.get("selection", "pilot")
    if selection not in ("pilot", "main", "pool"):
        raise ValueError(f"selection = {selection!r}: ожидается pilot, main или pool")
    return load_positions(REPO_ROOT / cfg["paths"]["positions"], pilot=selection == "pilot", main=selection == "main")


def read_by_position(paths: str | Sequence[str]) -> dict[str, dict]:
    """Строки JSONL одного или нескольких файлов (``paths.drafts``, ``paths.retrieval`` конфигурации — строка
    или список) по ``position_id``; позиция в двух файлах — ошибка, отсутствующий файл пропускается."""
    out: dict[str, dict] = {}
    for rel in [paths] if isinstance(paths, str) else paths:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        for row in read_jsonl(path):
            if row["position_id"] in out:
                raise ValueError(f"{row['position_id']}: позиция встречается в нескольких файлах ({rel})")
            out[row["position_id"]] = row
    return out


def load_seed_pool(path: str | Path) -> dict[int, dict]:
    """Вопросы seed pool по ``seed_idx`` (``data/seed_pool/seed_pool.jsonl``)."""
    return {int(q["seed_idx"]): q for q in read_jsonl(path)}


def load_document(documents_dir: str | Path, webpage_id: int) -> dict:
    """Текст документа из локального кэша ``data/_cache/documents`` (``sample_documents fetch``)."""
    path = Path(documents_dir) / f"{webpage_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"нет текста документа {webpage_id}: запустите sample_documents fetch")
    return json.loads(path.read_text(encoding="utf-8"))


def build_draft_prompt(position: dict, doc: dict, seed_pool: dict[int, dict], prompt: dict) -> str:
    r"""Сообщение пользователя: метаданные позиции, текст оригинала $x^{zh}_j$ и задание по роли.

    Перевода в корпусе нет (ADR-023), поэтому модель получает только оригинал. Для статей
    seed pool к заданию добавляются исходные вопросы промышленной системы.
    """
    role = position["role"]
    task_key = "answerable_seed" if role == "answerable" and position["origin"] == "seed" else role
    task = prompt["tasks"][task_key + "_menu" if is_menu(prompt) else task_key].strip()
    if is_menu(prompt):
        task += "\n\n" + prompt["menu"].strip()
    lines = [
        f"Документ webpage_id={position['webpage_id']}; источник: {position['netloc']} "
        f"({position['region']}); дата публикации: {position['published_at']}.",
        f"Заголовок: {(doc.get('title_zh') or '').strip()}",
        "<document>",
        (doc.get("text_zh") or "").strip(),
        "</document>",
        "",
        task,
    ]
    if task_key == "answerable_seed":
        lines.append("")
        lines.append("Исходные вопросы:")
        for idx in position["seed_refs"]:
            lines.append(f"{idx}. {seed_pool[idx]['question_ru']}")
    elif task_key == "dynamic_control":
        idx = position["control_seed_idx"]
        lines.append("")
        lines.append(f"Вопрос (номер {idx}): {seed_pool[idx]['question_ru']}")
    return "\n".join(lines)


def run_checks(draft: Draft, doc: dict, seed_question: str | None) -> dict:
    """Автоматические проверки черновика — подсказки координатору, не разметка."""
    q = draft.question_ru
    text = re.sub(r"\s+", "", doc.get("text_zh") or "") + re.sub(r"\s+", "", doc.get("title_zh") or "")
    span = re.sub(r"\s+", "", draft.evidence_span_zh)
    checks = {
        "anchor_format_ok": bool(ANCHOR_RE.match(draft.anchor_date or "")),
        "date_in_question": has(DATE_ANCHOR["ru"], q),
        "markers": [rule for rule in STATIC_RULES if has(SEED_POOL_RULES[rule][1], q)],
        "compound": has(SEED_POOL_RULES["compound"][1], q),
        "evidence_in_document": bool(span) and span in text,
        "evidence_len_ok": len(draft.evidence_span_zh) <= EVIDENCE_MAX and len(draft.evidence_span_ru) <= EVIDENCE_MAX,
    }
    if seed_question is not None:
        checks["control_question_verbatim"] = q.strip() == seed_question.strip()
    if not draft.answerable:
        checks["answer_empty"] = not draft.answer_canonical and not draft.answer_aliases
    return checks


def generate_one(position: dict, doc: dict, seed_pool: dict[int, dict], client, cfg: dict) -> Draft:
    r"""Один черновик моделью $g_{\mathrm{draft}}$; при подмене модели прогон прерывается (ADR-009)."""
    import anthropic

    prompt = cfg["prompts"][cfg["prompt_id"]]
    draft = new_draft(position, cfg)
    try:
        response = client.messages.create(
            model=cfg["draft_model"],
            max_tokens=cfg["max_tokens"],
            system=[{"type": "text", "text": prompt["system"], "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": build_draft_prompt(position, doc, seed_pool, prompt)}],
            output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": DRAFT_SCHEMA}},
        )
    except anthropic.APIStatusError as exc:
        draft.error = f"HTTP {exc.status_code}: {exc.message}"
        return draft
    except anthropic.APIConnectionError as exc:
        draft.error = f"соединение: {exc}"
        return draft

    draft.draft_model = response.model
    draft.request_id = response._request_id
    draft.stop_reason = response.stop_reason
    draft.usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
    }
    if response.model != cfg["draft_model"]:
        raise RuntimeError(f"ответ модели {response.model}, ожидалась {cfg['draft_model']}: прогон прерван")
    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        draft.error = f"отказ модели (категория {category})"
        return draft
    if response.stop_reason == "max_tokens":
        draft.error = "ответ обрезан по max_tokens"
        return draft

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        out = json.loads(text)
    except json.JSONDecodeError as exc:
        draft.error = f"ответ не разобран как JSON: {exc}"
        return draft
    return fill_draft(draft, out, position, doc, seed_pool)


def new_draft(position: dict, cfg: dict) -> Draft:
    return Draft(position_id=position["position_id"], webpage_id=position["webpage_id"],
                 role=position["role"], origin=position["origin"], pilot=position["pilot"],
                 draft_prompt_id=cfg["prompt_id"], answerable=position["role"] != "unanswerable_candidate",
                 created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def fill_draft(draft: Draft, out: dict, position: dict, doc: dict, seed_pool: dict[int, dict]) -> Draft:
    """Переносит ответ модели (объект по ``DRAFT_SCHEMA``) в черновик и добавляет проверки."""
    draft.question_ru = out["question_ru"].strip()
    draft.answer_canonical = out["answer_canonical"].strip() or None
    draft.answer_aliases = [a.strip() for a in out["answer_aliases"] if a.strip()]
    draft.answer_type = out["answer_type"]
    draft.supporting_ids = [position["webpage_id"]] if draft.answerable else []
    draft.evidence_span_zh = out["evidence_span_zh"].strip()
    draft.evidence_span_ru = out["evidence_span_ru"].strip()
    draft.question_type = out["question_type"]
    draft.category = out["category"]
    draft.anchor_date = out["anchor_date"].strip()
    draft.time_invariance_label = out["time_invariance_label"]
    draft.difficulty = out["difficulty"]
    draft.suitable = out["suitable"]
    draft.unsuitable_reason = out["unsuitable_reason"].strip()
    draft.coordinator_note = out["coordinator_note"].strip()
    used = out["seed_question_used"]
    if position["role"] == "dynamic_control":
        draft.seed_pool_ref = str(position["control_seed_idx"])
    elif used in position.get("seed_refs", []):
        draft.seed_pool_ref = str(used)
    control_q = seed_pool[position["control_seed_idx"]]["question_ru"] if position["role"] == "dynamic_control" else None
    draft.checks = run_checks(draft, doc, control_q)
    return draft


def generate_drafts(positions: Sequence[dict], seed_pool: dict[int, dict], cfg: dict, out_path: Path,
                    workers: int) -> list[Draft]:
    r"""Черновики по позициям в ``workers`` параллельных запросах; каждый черновик дописывается
    в ``out_path`` сразу после получения, поэтому прерванный прогон продолжается с места остановки."""
    import anthropic

    client = anthropic.Anthropic(max_retries=cfg["max_retries"])
    docs = {p["webpage_id"]: load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"]) for p in positions}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    drafts: list[Draft] = []
    with ThreadPoolExecutor(max_workers=workers) as pool, open(out_path, "a", encoding="utf-8") as fh:
        futures = {pool.submit(generate_one, p, docs[p["webpage_id"]], seed_pool, client, cfg): p for p in positions}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                draft = future.result()
            except RuntimeError:
                pool.shutdown(cancel_futures=True)
                raise
            drafts.append(draft)
            fh.write(json.dumps(asdict(draft), ensure_ascii=False) + "\n")
            fh.flush()
            status = draft.error or ("ok" if draft.suitable else "непригоден")
            print(f"[{done}/{len(positions)}] {draft.position_id} {draft.role}: {status}", file=sys.stderr)
    return drafts


def export_requests(positions: Sequence[dict], seed_pool: dict[int, dict], cfg: dict, out_dir: Path) -> None:
    r"""Запросы к модели черновиков в файлы ``<position_id>.json``: системный промпт, сообщение
    пользователя, схема ответа, модель и усилие — ровно то, что отправил бы :func:`generate_one`.

    Нужны, когда запрос выполняется вне API (``channel = "session"``): каждый файл обрабатывается
    отдельным вызовом той же модели, видящим только этот запрос; ответ — JSON по ``DRAFT_SCHEMA``
    в ``<position_id>.json`` каталога ответов (:func:`import_responses`).
    """
    prompt = cfg["prompts"][cfg["prompt_id"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in positions:
        doc = load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"])
        request = {
            "position_id": p["position_id"],
            "model": cfg["draft_model"],
            "effort": cfg["effort"],
            "prompt_id": cfg["prompt_id"],
            "system": prompt["system"],
            "user": build_draft_prompt(p, doc, seed_pool, prompt),
            "response_schema": MENU_SCHEMA if is_menu(prompt) else DRAFT_SCHEMA,
        }
        (out_dir / f"{p['position_id']}.json").write_text(json.dumps(request, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")


def import_responses(positions: Sequence[dict], seed_pool: dict[int, dict], cfg: dict, responses_dir: Path,
                     out_path: Path, model: str) -> list[Draft]:
    """Черновики из ответов, полученных вне API: проверка по ``DRAFT_SCHEMA`` и те же проверки, что у API."""
    import jsonschema

    drafts = []
    for p in positions:
        draft = new_draft(p, cfg)
        draft.channel, draft.draft_model = "session", model
        path = responses_dir / f"{p['position_id']}.json"
        if not path.exists():
            draft.error = "нет ответа"
        else:
            draft.created_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            try:
                out = json.loads(path.read_text(encoding="utf-8"))
                jsonschema.validate(out, DRAFT_SCHEMA)
            except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
                draft.error = f"ответ не соответствует схеме: {str(exc).splitlines()[0]}"
            else:
                doc = load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"])
                fill_draft(draft, out, p, doc, seed_pool)
        drafts.append(draft)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(asdict(d), ensure_ascii=False) + "\n" for d in drafts), encoding="utf-8")
    return drafts


def candidate_draft(position: dict, cfg: dict, menu: dict, cand: dict, doc: dict,
                    seed_pool: dict[int, dict]) -> Draft:
    """Черновик из одного кандидата меню (draft-v2): поля кандидата и пригодность документа."""
    draft = new_draft(position, cfg)
    out = {**cand, "suitable": menu["suitable"], "unsuitable_reason": menu["unsuitable_reason"]}
    return fill_draft(draft, out, position, doc, seed_pool)


def import_menus(positions: Sequence[dict], seed_pool: dict[int, dict], cfg: dict, responses_dir: Path,
                 out_path: Path, model: str) -> list[dict]:
    """Меню кандидатов из ответов вне API (draft-v2): проверка по ``MENU_SCHEMA``, один кандидат на тип
    вопроса, проверки черновика у каждого кандидата. Строка на позицию — в ``out_path``."""
    import jsonschema

    rows = []
    for p in positions:
        row = {"position_id": p["position_id"], "webpage_id": p["webpage_id"], "role": p["role"],
               "origin": p["origin"], "region": p["region"], "draft_model": model,
               "draft_prompt_id": cfg["prompt_id"], "channel": "session", "created_at": "", "error": None,
               "suitable": None, "unsuitable_reason": "", "candidates": []}
        path = responses_dir / f"{p['position_id']}.json"
        try:
            if not path.exists():
                raise ValueError("нет ответа")
            row["created_at"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            menu = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.validate(menu, MENU_SCHEMA)
            types = [c["question_type"] for c in menu["candidates"]]
            if len(types) != len(set(types)):
                raise ValueError(f"повторяются типы вопроса: {types}")
        except (ValueError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            row["error"] = str(exc).splitlines()[0]
            rows.append(row)
            continue
        doc = load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"])
        row["suitable"], row["unsuitable_reason"] = menu["suitable"], menu["unsuitable_reason"].strip()
        for cand in menu["candidates"]:
            row["candidates"].append({**cand, "checks": candidate_draft(p, cfg, menu, cand, doc, seed_pool).checks})
        rows.append(row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return rows


def summarize_menus(path: Path) -> str:
    """Сводка по меню кандидатов: ошибки, пригодность, предложение по типам вопроса и оценкам fit."""
    rows = read_jsonl(path)
    ok = [r for r in rows if not r["error"]]
    lines = [f"Позиций: {len(rows)}; с ошибкой: {len(rows) - len(ok)}; файл: {path.relative_to(REPO_ROOT)}",
             f"Непригодные документы (suitable = false): {sum(r['suitable'] is False for r in ok)}",
             f"Кандидатов: {sum(len(r['candidates']) for r in ok)}; в среднем на позицию: "
             f"{sum(len(r['candidates']) for r in ok) / max(len(ok), 1):.1f}"]
    for role in sorted({r["role"] for r in ok}):
        group = [r for r in ok if r["role"] == role]
        supply = {t: sum(any(c["question_type"] == t for c in r["candidates"]) for r in group) for t in QUESTION_TYPES}
        lines.append(f"{role} ({len(group)}), позиций с кандидатом типа: "
                     + ", ".join(f"{t} — {n}" for t, n in supply.items()))
    for err in [r for r in rows if r["error"]]:
        lines.append(f"ошибка {err['position_id']}: {err['error']}")
    return "\n".join(lines)


def summarize(path: Path) -> str:
    """Сводка по файлу черновиков: роли, ошибки, пригодность, проверки, токены."""
    drafts = read_jsonl(path)
    ok = [d for d in drafts if not d["error"]]
    lines = [f"Черновиков: {len(drafts)}; с ошибкой: {len(drafts) - len(ok)}; файл: {path.relative_to(REPO_ROOT)}"]
    roles: dict[str, int] = {}
    for d in drafts:
        roles[d["role"]] = roles.get(d["role"], 0) + 1
    lines.append("Роли: " + ", ".join(f"{k} — {v}" for k, v in sorted(roles.items())))
    lines.append(f"Непригодные документы (suitable = false): {sum(not d['suitable'] for d in ok)}")
    for key in ("anchor_format_ok", "date_in_question", "evidence_in_document", "evidence_len_ok"):
        lines.append(f"{key}: {sum(bool(d['checks'].get(key)) for d in ok)}/{len(ok)}")
    flagged = [d for d in ok if d["checks"].get("markers") and d["role"] != "dynamic_control"]
    lines.append(f"Маркеры E1/E2/E4 в вопросах (кроме контрольных): {len(flagged)}")
    tokens_in = sum(d["usage"].get("input_tokens", 0) for d in drafts)
    tokens_out = sum(d["usage"].get("output_tokens", 0) for d in drafts)
    lines.append(f"Токены: входные {tokens_in}, выходные {tokens_out}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--prompt", default=None,
                        help="версия промпта (по умолчанию prompt_id конфигурации); draft-v2 — меню кандидатов")
    parser.add_argument("--pilot", action="store_true", help="только 30 позиций пилота")
    parser.add_argument("--main", action="store_true", help="основной раунд: 270 позиций без пилота")
    parser.add_argument("--include-reserve", action="store_true", help="вместе с 60 резервными позициями")
    parser.add_argument("--limit", type=int, default=None, help="не больше N позиций (отладка)")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true", help="собрать промпты без вызова модели")
    parser.add_argument("--summary", action="store_true", help="только сводка по готовому файлу")
    parser.add_argument("--export-requests", type=Path, default=None,
                        help="выгрузить запросы в каталог вместо вызова API")
    parser.add_argument("--import-responses", type=Path, default=None,
                        help="собрать черновики из ответов в каталоге (запросы выполнены вне API)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(REPO_ROOT / args.config)
    if args.pilot and args.main:
        raise SystemExit("--pilot и --main несовместимы")
    if args.prompt:
        cfg["prompt_id"] = args.prompt
    menu = is_menu(cfg["prompts"][cfg["prompt_id"]])
    if menu and args.pilot:
        raise SystemExit(f"{cfg['prompt_id']}: меню кандидатов только для основного раунда (пилот — draft-v1)")
    if menu and not (args.export_requests or args.import_responses or args.summary or args.dry_run):
        raise SystemExit(f"{cfg['prompt_id']}: меню кандидатов — только через --export-requests / --import-responses; "
                         "черновики из меню собирает code.annotation.balance_types")
    default_out = "candidates_main" if menu else ("out_pilot" if args.pilot else "out_main")
    out_path = REPO_ROOT / (args.out or cfg["paths"][default_out])
    if args.summary:
        print(summarize_menus(out_path) if menu else summarize(out_path))
        return 0

    positions = load_positions(REPO_ROOT / cfg["paths"]["positions"], pilot=args.pilot,
                               include_reserve=args.include_reserve, main=args.main)
    kept = [d for d in read_jsonl(out_path) if not d["error"]] if out_path.exists() else []
    done = {d["position_id"] for d in kept}
    todo = [p for p in positions if p["position_id"] not in done][: args.limit]
    seed_pool = load_seed_pool(REPO_ROOT / cfg["paths"]["seed_pool"])
    print(f"позиций: {len(positions)}, готово: {len(done)}, к генерации: {len(todo)}", file=sys.stderr)

    if args.export_requests:
        export_requests(positions, seed_pool, cfg, REPO_ROOT / args.export_requests)
        print(f"запросов: {len(positions)} → {args.export_requests}", file=sys.stderr)
        return 0
    if args.import_responses:
        if menu:
            import_menus(positions, seed_pool, cfg, REPO_ROOT / args.import_responses, out_path, cfg["draft_model"])
            print(summarize_menus(out_path))
            return 0
        import_responses(positions, seed_pool, cfg, REPO_ROOT / args.import_responses, out_path, cfg["draft_model"])
        print(summarize(out_path))
        return 0

    if args.dry_run:
        prompt = cfg["prompts"][cfg["prompt_id"]]
        for p in todo:
            doc = load_document(REPO_ROOT / cfg["paths"]["documents"], p["webpage_id"])
            msg = build_draft_prompt(p, doc, seed_pool, prompt)
            print(f"{p['position_id']} {p['role']}: {len(msg)} знаков")
        return 0

    if out_path.exists():
        # строки с ошибками отбрасываются: эти позиции генерируются заново
        out_path.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in kept), encoding="utf-8")
    try:
        generate_drafts(todo, seed_pool, cfg, out_path, args.workers or cfg["workers"])
    except TypeError as exc:
        if "authentication" not in str(exc):
            raise
        print("нет учётных данных API модели черновиков: задайте ANTHROPIC_API_KEY в .env "
              "(см. code/README.md)", file=sys.stderr)
        return 2
    print(summarize(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
