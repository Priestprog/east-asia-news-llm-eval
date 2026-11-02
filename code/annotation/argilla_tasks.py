r"""Разметка в Argilla: учётные записи, датасет, выгрузка заданий и ответов.

Платформа — Argilla 2.8.0 на ``https://annotate.ai.ivran.ru`` (стек ``production/annotation``
репозитория промышленной системы). Каждая запись получает ровно $R = 3$ независимых ответа
(``TaskDistribution(min_submitted=3)``); аннотатор видит только свои ответы. Размечают только аннотаторы
(пул A1–A14, каждую запись — любые трое, ADR-027 и ADR-028); единый пул — пилот и основной раунд (``selection: pool``).

Что видит аннотатор (протокол разметки, §3): черновик вопроса; карточку черновика (ответ, алиасы,
evidence span, источник, дата публикации); документ — оригинал и перевод рядом, абзац к абзацу,
с подсветкой evidence span; топ-20 ретривера — у всех записей, чтобы роли позиций не раскрывались.
Подсказками из черновика предзаполнены дата-якорь, тип вопроса, категория, сложность, ответ,
алиасы, тип ответа, evidence span и $S^*$ (протокол разметки, §3, п. 6; решение 30.10). Инвариантность,
правила исключения, отвечаемость и метка инвариантности не предзаполняются. Роль позиции, заметка
координатора, проверки черновика и метки модели в Argilla не передаются.

Подкоманды:

* ``setup`` — рабочее пространство и учётные записи аннотаторов; пароли новых
  учётных записей пишутся в ``data/_private/annotator_accounts.csv`` (в репозиторий не входит);
* ``preflight`` — проверка записей перед загрузкой и отпечаток входных данных
  ``data/_cache/upload_manifest.json``;
* ``push`` — датасет и записи (существующий датасет — только с ``--upsert``); ``--preview FILE`` —
  только локальный HTML одной записи;
* ``update-settings`` — обновить у существующего датасета инструкцию, шаблоны полей, заголовки, подсказки ⓘ и
  подписи меток при тех же ключах (записи и ответы не затрагиваются);
* ``verify`` — сверка датасета на сервере с локальными записями и настройками: поля, шаблоны, вопросы,
  подсказки, метки, инструкция;
* ``delete`` — удаление тестовой копии (рабочий датасет и датасет с ответами не удаляются);
* ``retire`` — снятие с сервера прежних объектов: датасета ``--dataset`` в рабочем пространстве
  (не рабочего и только без ответов, включая черновики ответов), учётных записей ``--user`` и пустых
  рабочих пространств ``--workspace-name`` (``--dry-run`` — только показать);
* ``progress`` — ход разметки по аннотаторам;
* ``pull`` — отправленные ответы в ``annotations.jsonl``: строки ``{"draft_id", "annotator",
  <поля>}`` (контракт ``export_sheets.import_annotations``) с проверкой допустимости значений.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import secrets
import sys
from pathlib import Path
from typing import Sequence

from code import REPO_ROOT, load_config, load_env
from code.annotation.generate_drafts import (
    ANCHOR_RE,
    ANSWER_TYPES,
    CATEGORIES,
    DIFFICULTIES,
    LABELS,
    QUESTION_TYPES,
    read_by_position,
    read_jsonl,
    round_positions,
)

DEFAULT_CONFIG = "code/configs/annotation.yaml"
LOG_BATCH = 20                 # записей за один запрос загрузки в Argilla
RULES = ["E1", "E2", "E3", "E4", "E5"]

# ---------------------------------------------------------------- шаблоны полей

# Argilla 2.8.0 показывает CustomField в iframe (srcdoc, scrolling="no") и задаёт его высоту один раз при
# загрузке; в iframe копируются стили страницы и атрибут data-theme (light | dark | high-contrast), а фон
# body — var(--bg-field). Поэтому шаблоны сами подгоняют высоту окна под содержимое (FIT_JS) и берут
# цвета из переменных темы (THEME_CSS), а не задают тёмный текст жёстко.
THEME_CSS = """
:root { --fg: #1f2328; --muted: #57606a; --faint: #8c959f; --line: #d0d7de; --line2: #eaeef2; --head: #f6f8fa;
        --ev: #fff8c5; --mark: #ffd33d; --mark-fg: #1f2328; --link: #0969da; --src: #9a6700; --btn: #f6f8fa; }
html[data-theme="dark"], html[data-theme="high-contrast"] {
        --fg: #e6edf3; --muted: #9198a1; --faint: #6e7681; --line: #3d444d; --line2: #2a313c; --head: #151b23;
        --ev: #3a3000; --mark: #9e6a03; --mark-fg: #ffffff; --link: #4493f8; --src: #d29922; --btn: #21262d; }
html, body { color: var(--fg); }
body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif; }
a { color: var(--link); }
button { font: inherit; font-size: 12px; padding: 2px 10px; border: 1px solid var(--line); border-radius: 6px;
         background: var(--btn); color: var(--fg); cursor: pointer; white-space: nowrap; }
"""

FIT_JS = """
  // высота окна поля = высота содержимого #root (Argilla сама её не пересчитывает); мерится обёртка, а не
  // документ: высота документа в iframe не бывает меньше окна, и окно не уменьшалось бы при сворачивании
  const root = document.getElementById("root");
  const fit = () => { const f = window.frameElement;
    if (f) f.style.height = Math.ceil(root.getBoundingClientRect().height) + 4 + "px"; };
  new ResizeObserver(fit).observe(root);
  window.addEventListener("load", fit);
  fit();
"""

DOCUMENT_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>""" + THEME_CSS + """
body { font-size: 14px; }
.bar { display: flex; align-items: baseline; gap: 12px; margin: 2px 0 6px; }
.title { font-size: 15px; font-weight: 600; flex: 1; }
.info { color: var(--muted); font-size: 12px; white-space: nowrap; }
.box { max-height: 450px; overflow-y: auto; border: 1px solid var(--line); border-radius: 6px; }
.box.full { max-height: none; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th { position: sticky; top: 0; background: var(--head); text-align: left; font-weight: 600; color: var(--muted);
     padding: 4px 8px; border-bottom: 1px solid var(--line); z-index: 1; }
td { vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--line2); line-height: 1.55;
     word-wrap: break-word; color: var(--fg); }
th.n, td.n { width: 40px; color: var(--faint); font-size: 12px; white-space: nowrap; }
tr.ev td { background: var(--ev); }
mark { background: var(--mark); color: var(--mark-fg); padding: 0 1px; }
</style></head><body><div id="root">
<div class="bar"><div class="title" id="title"></div><span class="info" id="info"></span>
<button id="toggle" type="button">Показать весь документ</button></div>
<div class="box" id="box">
<table><thead><tr><th class="n">№</th><th>Оригинал (zh)</th><th>Перевод (ru), вспомогательный</th></tr></thead>
<tbody id="rows"></tbody></table></div></div>
<script>
  const doc = record.fields.document;
  document.getElementById("title").textContent = doc.title_zh || "";
  document.getElementById("info").textContent = doc.paragraphs.length + " абз.";
  const rows = document.getElementById("rows");
  const parts = doc.evidence_parts || [];
  for (const p of doc.paragraphs) {
    const tr = document.createElement("tr");
    if (p.ev) tr.className = "ev";
    const n = document.createElement("td"); n.className = "n"; n.textContent = p.i + 1;
    const zh = document.createElement("td");
    let at = -1, ev = "";
    for (const part of parts) {
      const k = p.zh.indexOf(part);
      if (k >= 0) { at = k; ev = part; break; }
    }
    if (at >= 0) {
      zh.append(p.zh.slice(0, at));
      const m = document.createElement("mark"); m.textContent = ev; zh.append(m);
      zh.append(p.zh.slice(at + ev.length));
    } else {
      zh.textContent = p.zh;
    }
    const ru = document.createElement("td"); ru.textContent = p.ru;
    tr.append(n, zh, ru); rows.append(tr);
  }
  // окно открывается на абзаце с evidence span; прокручивается только окно, не страница
  const box = document.getElementById("box");
  const first = rows.querySelector("tr.ev");
  const toEvidence = () => { if (first) box.scrollTop = Math.max(0, first.offsetTop - 40); };
  toEvidence();
  const toggle = document.getElementById("toggle");
  toggle.addEventListener("click", () => {
    const full = box.classList.toggle("full");
    toggle.textContent = full ? "Свернуть" : "Показать весь документ";
    if (!full) toEvidence();
  });
""" + FIT_JS + """</script></body></html>"""

CARD_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>""" + THEME_CSS + """
body { font-size: 14px; }
#root { padding: 2px 0; line-height: 1.6; }
.k { color: var(--muted); }
b { font-weight: 600; }
</style></head><body><div id="root"></div>
<script>
  // одна строка об источнике; цвет ссылки — из темы (markdown-поле Argilla в тёмной теме плохо читается)
  const c = record.fields.card;
  const line = document.getElementById("root");    // имя root занято в FIT_JS
  const k = document.createElement("span"); k.className = "k"; k.textContent = "Источник: ";
  const id = document.createElement("b"); id.textContent = c.webpage_id;
  const a = document.createElement("a"); a.href = c.uri; a.target = "_blank"; a.rel = "noopener";
  a.textContent = "открыть оригинал";
  line.append(k, c.netloc + " · " + c.region + " · опубликовано " + c.published_at + " · webpage_id ", id, " · ", a);
""" + FIT_JS + """</script></body></html>"""

RETRIEVAL_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>""" + THEME_CSS + """
body { font-size: 13px; }
summary { cursor: pointer; }
#all > summary { font-weight: 600; padding: 4px 0; }
.q { color: var(--muted); font-size: 12px; margin: 2px 0 6px; }
.hit { border-top: 1px solid var(--line2); }
.hit > summary { padding: 5px 0; list-style: none; }
.hit > summary::-webkit-details-marker { display: none; }
.hit > summary .meta::before { content: "▸ "; color: var(--faint); }
.hit[open] > summary .meta::before { content: "▾ "; }
.meta { color: var(--muted); font-size: 12px; }
.meta b { color: var(--fg); font-weight: 600; }
.ru { color: var(--fg); opacity: .85; margin-top: 1px; }
.more { padding: 2px 0 8px 14px; }
.zh { margin-bottom: 4px; }
.src { color: var(--src); font-weight: 600; }
</style></head><body><div id="root">
<details id="all"><summary id="sum"></summary><div class="q" id="queries"></div><div id="hits"></div></details></div>
<script>
  const r = record.fields.retrieval;
  const cut = (s, n) => (s || "").replace(/\\s+/g, " ").trim().slice(0, n) + ((s || "").length > n ? "…" : "");
  document.getElementById("sum").textContent =
    "Поиск по корпусу: " + r.results.length + " документов (развернуть)";
  document.getElementById("queries").textContent =
    "Запросы: " + r.queries.map(q => q.lang + ": " + q.text).join(" | ");
  const box = document.getElementById("hits");
  for (const h of r.results) {
    const d = document.createElement("details"); d.className = "hit";
    const s = document.createElement("summary");
    const meta = document.createElement("div"); meta.className = "meta";
    const title = document.createElement("b"); title.textContent = cut(h.title_zh, 40);
    meta.append("#" + h.rank + " · ", title, " · " + (h.source || "") + " · " + (h.published_at || "") +
      " · webpage_id " + h.webpage_id);
    if (h.is_source_doc) {
      const m = document.createElement("span"); m.className = "src"; m.textContent = " · документ-источник";
      meta.append(m);
    }
    const ru = document.createElement("div"); ru.className = "ru"; ru.textContent = cut(h.snippet_ru, 150);
    s.append(meta, ru);
    const more = document.createElement("div"); more.className = "more";
    const zh = document.createElement("div"); zh.className = "zh"; zh.textContent = h.snippet_zh || "";
    const full = document.createElement("div"); full.className = "ru"; full.textContent = h.snippet_ru || "";
    const link = document.createElement("a"); link.href = h.uri || "#"; link.target = "_blank";
    link.rel = "noopener";
    try { link.textContent = decodeURI(h.uri || ""); } catch (e) { link.textContent = h.uri || ""; }
    more.append(zh, full, link);
    d.append(s, more); box.append(d);
  }
""" + FIT_JS + """</script></body></html>"""


# ---------------------------------------------------------------- настройки датасета

def _same(values: Sequence[str]) -> dict[str, str]:
    return {v: v for v in values}


# Поля записи и вопросы формы — общее описание для датасета Argilla и локального предпросмотра
FIELDS = [
    {"name": "memo", "title": "Памятка"},
    {"name": "question", "title": "Вопрос"},
    {"name": "card", "title": "Источник"},
    {"name": "document", "title": "Документ: оригинал и перевод"},
    {"name": "retrieval", "title": "Топ-20 поиска по корпусу"},
]

# Формулировки формы — без обозначений из постановки (z, Inv, G⊥): пояснения даны словами и
# ссылками на разделы инструкции аннотатора. Пункты формы в текстах для аннотатора называются «пунктами»,
# а не «вопросами»: «вопрос» — это размечаемый вопрос. Описание (description) — markdown для памятки и полной
# инструкции: строки «- …» становятся списком, остальные — абзацами
QUESTIONS = [
    {"kind": "label", "name": "z", "title": "1. Ответ на вопрос не меняется со временем? (раздел 2)", "required": True,
     "description": "- 1 — да: ни одно правило исключения E1–E5 не сработало (правила — в пункте 2 формы и в разделе 2 "
                    "инструкции).\n"
                    "- 0 — нет, исключить: сработало хотя бы одно правило. Отметьте его в пункте 2, напишите "
                    "комментарий в пункте 16; остальные пункты не заполняйте.",
     "labels": {"1": "1 — да, оставить", "0": "0 — исключить"}},
    {"kind": "multi", "name": "excl", "title": "2. Сработавшие правила исключения (только при «0» в пункте 1)",
     "description": "Отмечается, только если в пункте 1 стоит «0», то есть сработало хотя бы одно из правил E1–E5, "
                    "описанных в разделе 1 памятки (подробно — раздел 2 инструкции). Можно отметить несколько.",
     "labels": {"E1": "E1 прогноз, суждение о будущем", "E2": "E2 «сейчас», «последний»",
                "E3": "E3 величина без даты-якоря", "E4": "E4 оценочный, спорный", "E5": "E5 ложная предпосылка"}},
    {"kind": "label", "name": "answerable", "title": "3. Есть ли ответ в корпусе? (раздел 4)",
     "description": "- 1 — ответ следует из документа-источника или документов топ-20.\n"
                    "- 0 — ответа в них нет; ставится только после просмотра топ-20.",
     "labels": {"1": "1 — ответ есть", "0": "0 — ответа нет"}},
    {"kind": "label", "name": "ti_label", "title": "4. Тип неизменности ответа (раздел 2)",
     "description": "- **never_changing** — факт не меняется в принципе (кто, что, когда произошло).\n"
                    "- **slow_changing_anchored** — величина меняется, но зафиксирована датой (должность на дату, "
                    "показатель за период).",
     "labels": _same(LABELS)},
    {"kind": "text", "name": "anchor_date", "title": "5. Дата-якорь события",
     "description": "Дата события из документа (не дата публикации) с той точностью, что есть в тексте. "
                    "Формат один для всех регионов, меняется только точность:\n"
                    "- **2023** — год\n- **2023-05** — месяц\n- **2023-05-31** — день\n- **2023-Q2** — квартал\n"
                    "- **2023-H1** — полугодие"},
    {"kind": "label", "name": "question_type", "title": "6. Тип вопроса (раздел 5)",
     "description": "- **who** — лицо, организация, орган\n"
                    "- **what** — объект, событие, название, содержание решения\n"
                    "- **when** — дата, период\n"
                    "- **where** — место, страна, регион\n"
                    "- **how_many** — количество, сумма, доля, процент\n"
                    "- **which** — выбор из явно заданного множества\n"
                    "- **yes_no** — подтверждение факта\n"
                    "- **list** — перечисление из 2–5 элементов",
     "labels": _same(QUESTION_TYPES)},
    {"kind": "label", "name": "category", "title": "7. Категория (раздел 5)",
     "description": "Тема того факта, о котором спрашивает вопрос; тема статьи в целом может быть другой. Пример: "
                    "статья о визите премьер-министра КНР в Сингапур относится к международным отношениям, но вопрос "
                    "о сумме подписанных при визите инвестиционных соглашений — economy.\n"
                    "- **politics** — внутренняя политика, государственное управление, назначения, законы\n"
                    "- **economy** — экономика, финансы, торговля, бюджет\n"
                    "- **society** — общество, образование, социальная политика, происшествия\n"
                    "- **international** — отношения между странами, визиты, международные организации\n"
                    "- **security** — оборона, армия, правопорядок\n"
                    "- **technology** — наука и технологии\n"
                    "- **culture** — культура, искусство, спорт\n"
                    "- **health** — здравоохранение, эпидемии\n"
                    "- **environment** — экология, климат, стихийные бедствия\n"
                    "- **other** — ничего из перечисленного",
     "labels": _same(CATEGORIES)},
    {"kind": "label", "name": "difficulty", "title": "8. Сложность (раздел 6)",
     "description": "- **easy** — ответ в одном предложении, слова вопроса совпадают со словами документа.\n"
                    "- **medium** — нужно сопоставить 2–3 фрагмента, пересчитать единицы, понять, к кому относятся "
                    "местоимения; либо перевод искажает ключевой термин.\n"
                    "- **hard** — нужно несколько документов, или ответ есть только в оригинале, или вопрос "
                    "почти не пересекается с документом по словам.",
     "labels": _same(DIFFICULTIES)},
    {"kind": "text", "name": "answer", "title": "9. Канонический ответ (раздел 3)",
     "description": "Кратчайшая проверяемая формулировка; составной ответ — одной строкой через «;»."},
    {"kind": "text", "name": "aliases", "title": "10. Алиасы — по одному на строку (раздел 3)",
     "description": "Написание в оригинале (иероглифами), латиницей, другие транслитерации, сокращения, другие "
                    "форматы чисел и дат."},
    {"kind": "label", "name": "answer_type", "title": "11. Тип ответа (раздел 3)",
     "description": "short_text — только для вопросов о словах конкретного лица или органа; ответ не длиннее "
                    "25 слов.",
     "labels": _same(ANSWER_TYPES)},
    {"kind": "text", "name": "evidence_ru", "title": "12. Evidence span — перевод (≤ 300 знаков)",
     "description": "Фрагмент перевода, из которого следует ответ."},
    {"kind": "text", "name": "evidence_zh", "title": "13. Evidence span — оригинал (≤ 300 знаков)",
     "description": "Заполняет и сверяет читающий по-китайски."},
    {"kind": "text", "name": "supporting_ids", "title": "14. S*: webpage_id документов, из которых следует ответ (раздел 4)",
     "description": "По одному на строку; из документа-источника и топ-20."},
    {"kind": "label", "name": "multi_doc", "title": "15. Нужно больше одного документа?",
     "description": "Да — если ответ нельзя получить из одного документа; тогда в пункт 14 вносятся все нужные "
                    "документы.",
     "labels": {"no": "нет", "yes": "да"}},
    {"kind": "text", "name": "comment", "title": "16. Комментарий",
     "description": "Обязателен, если вы исправили предзаполненное значение или исключили вопрос («0» в пункте 1).\n"
                    "Сюда же — замечания к переводу и предложенная переформулировка вопроса."},
]

# Короткие подсказки для значка ⓘ у пункта формы: всплывающее окно Argilla узкое и не настраивается, поэтому
# там 1–2 строки (перенос строки сохраняется), а полные пояснения (description) — в памятке и в полной инструкции
HINTS = {
    "z": "1 — оставить.\n0 — исключить: сработало правило E1–E5. Подробно — в «Памятке» (кнопка вверху).",
    "excl": "Только если в пункте 1 стоит «0», то есть сработало правило E1–E5 (раздел 1 памятки).",
    "answerable": "1 — ответ есть в документе или топ-20.\n0 — ответа нет; только после просмотра топ-20.",
    "ti_label": "never_changing — факт.\nslow_changing_anchored — величина на дату.",
    "anchor_date": "Дата события: 2023 · 2023-05 · 2023-05-31 · 2023-Q2 · 2023-H1.",
    "question_type": "who, what, when, where, how_many, which, yes_no, list — определения в «Памятке».",
    "category": "Тема спрашиваемого факта; у статьи в целом тема может быть другой. Значения — в «Памятке».",
    "difficulty": "easy / medium / hard — определения в «Памятке».",
    "answer": "Кратчайшая проверяемая формулировка; составной ответ — через «;».",
    "aliases": "Оригинал имени, латиница, другие форматы чисел и дат.",
    "evidence_ru": "Фрагмент перевода, из которого следует ответ.",
    "evidence_zh": "Фрагмент оригинала; сверяет читающий по-китайски.",
    "supporting_ids": "webpage_id по одному на строку.",
    "multi_doc": "Да — если ответ нельзя получить из одного документа.",
    "comment": "Обязателен при любом исправлении и при исключении («0» в пункте 1).",
}
HINT_MAX = 120

# Работа в интерфейсе Argilla: массовый режим и Discard ломают распределение «ровно 3 ответа на запись»,
# поэтому они вынесены в отдельный красный блок (> [!CAUTION])
INTERFACE_NOTES = """## Работа в интерфейсе

- Работайте по одной записи: значок ▢ вверху справа над записью.
- **Submit** — отправить ответ, запись уходит из списка Pending.
- **Save as draft** — сохранить, не отправляя.
- Значок ⓘ у пункта формы — краткая подсказка; полные пояснения — ниже, в разделе «Пояснения к пунктам формы».
- Работайте сессиями не длиннее 2 часов, не больше двух сессий в день: отправленные ответы и черновики (Save as draft) сохраняются, можно продолжить позже.

> [!CAUTION]
> **Не используйте**
> - **Режим списка (☰)** — в нём ответ ставится сразу многим записям.
> - **Discard** — неподходящий вопрос исключается ответом «0» в пункте 1 формы с комментарием.
"""

# Памятка: в шапке Argilla (кнопка «Памятка»), в начале полной инструкции и панели Guidelines; правила — как в
# разделе 2 инструкции. Блок > [!IMPORTANT] выводится крупным жирным шрифтом
GUIDELINES_MEMO = """# Памятка аннотатора

> [!IMPORTANT]
> **Предзаполненные значения подготовлены автоматически и могут быть неверными: за итоговую запись отвечает аннотатор.**

Заполняйте форму справа по порядку пунктов.

## 1. Как меняется ответ со временем

Вопрос исключается, если срабатывает хотя бы одно правило:

- **E1** — прогноз, суждение о будущем («насколько эффективными окажутся меры», «приведёт ли к росту или к спаду»). Допустим вопрос о том, что конкретное лицо или орган сказали в известную дату: это факт, а не прогноз.
- **E2** — привязка к моменту запроса: «сейчас», «в настоящее время», «последний», «недавно», «в этом году», «за последние N лет».
- **E3** — меняющаяся величина (цена, курс, индекс, численность, действующая должность) без явной даты или периода.
- **E4** — оценочный или спорный вопрос («кто прав», «законно ли», «насколько успешной была»), если ответ нельзя свести к словам конкретного лица или органа, сказанным в известную дату. Пример разметки — в разделе 2 инструкции.
- **E5** — ложная предпосылка: вопрос содержит сведения, которые противоречат документу (неверное имя, дата, сумма, событие), или опирается на то, о чём в документе не говорится.

Если вопрос исключается: в пункте 1 формы поставьте «0», в пункте 2 отметьте сработавшие правила, в пункте 16 напишите комментарий. Остальные пункты не заполняйте.

## 2. Есть ли ответ в корпусе (пункт 3 формы)

- 1 — ответ следует из документа-источника или документов топ-20.
- 0 — ответа нет; ставится только после просмотра топ-20.

## 3. Предзаполненные пункты

Дата-якорь, тип вопроса, категория, сложность, ответ, алиасы, evidence span и S* проверьте и при необходимости исправьте. Комментарий обязателен при любом исправлении.

Разметка окончательна и не перепроверяется: заполняйте все пункты полностью, сомнения пишите в комментарии.

## 4. Оригинал главнее перевода

Перевод вспомогательный; читающий по-китайски сверяет с оригиналом числа, даты и имена в ответе.

"""

MEMO_TAIL = "Ниже — разделы 2 и 3 инструкции: правила исключения с примерами, канонический ответ и алиасы.\n\n---\n\n"

# Argilla принимает инструкцию не длиннее 10 000 знаков: на панель Guidelines (запасной вариант — основная
# инструкция открывается кнопками в шапке) идут памятка и разделы, которые нужны у каждой записи: правила
# исключения и ответ с алиасами. Разделы 4 и 5 на панель уже не помещаются — они в «Полной инструкции»
ARGILLA_SECTIONS = ("2", "3")
GUIDELINES_LIMIT = 10_000

# Тексты для аннотаторов не должны раскрывать устройство репозитория и методики (замечания к инструкции,
# 01.11): пути, ссылки на ADR, формулы в разметке GitHub, обозначения постановки
FORBIDDEN_IN_ANNOTATOR_TEXT = ("docs/", "data/", "code/", ".md", ".json", "ADR-", "$`", "\\math", "⊥", "G+",
                               "problem_statement", "кандидат", "адъюдик", "пилот", "раунд")  # без учёта регистра

# Формулы инструкции (разметка GitHub $`…`$) Argilla не отрисовывает — переводятся в текст
_TEX_SYMBOLS = {
    r"\bot": "⊥", r"\ge": "≥", r"\le": "≤", r"\in": "∈", r"\subset": "⊂", r"\sqcup": "⊔", r"\times": "×",
    r"\alpha": "α", r"\tau": "τ", r"\ell": "ℓ", r"\dots": "…", r"\iff": "⇔", r"\exists": "∃", r"\forall": "∀",
    r"\sum": "Σ", r"\{": "{", r"\}": "}", r"\,": " ", r"\ ": " ", r"\left": "", r"\right": "",
}


def tex_to_text(expr: str) -> str:
    """Формула → читаемый текст: E_1 → E1, z_r(q) → z(q), G^{\\bot} → G⊥, \\mathrm{Inv} → Inv."""
    s = expr.replace(r"\{", "\u0001").replace(r"\}", "\u0002")       # фигурные скобки множества сохраняются
    while True:                                                         # вложенные \widehat{\mathrm{Inv}}
        t = re.sub(r"\\(?:mathrm|mathcal|mathbb|widehat|hat|bar)\{([^{}]*)\}", r"\1", s)
        if t == s:
            break
        s = t
    s = re.sub(r"\\(?:hat|bar) (\w)", r"\1", s)
    for tex, sym in sorted(_TEX_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(tex, sym)
    s = re.sub(r"z_r", "z", s)
    s = re.sub(r"_\{([^{}]*)\}|_(\w)", lambda m: m.group(1) or m.group(2), s)
    s = re.sub(r"\^\{([^{}]*)\}|\^(\S)", lambda m: m.group(1) or m.group(2), s)
    s = s.replace("{", "").replace("}", "").replace("\u0001", "{").replace("\u0002", "}")
    return re.sub(r"\s+", " ", s).strip()


def _plain_alerts(markdown: str) -> str:
    """Блоки ``> [!IMPORTANT]`` и ``> [!CAUTION]`` — в обычную цитату: панель Argilla их не отрисовывает и
    показала бы метку текстом."""
    return re.sub(r"(?m)^> \[!(?:IMPORTANT|CAUTION|NOTE|WARNING|TIP)\]\n", "", markdown)


def _formulas_to_text(markdown: str) -> str:
    text = re.sub(r"\$`([^`]+)`\$", lambda m: tex_to_text(m.group(1)), markdown)
    return re.sub(r"```math\n(.*?)\n```", lambda m: tex_to_text(m.group(1)), text, flags=re.S)


def _sections(text: str) -> dict[str, str]:
    """Разделы инструкции «## N. …» по номеру (подразделы «### …» входят в раздел)."""
    return {m.group(1): m.group(0) for m in re.finditer(r"(?ms)^## (\d+)\..*?(?=^## \d+\.|\Z)", text)}


def guidelines_for_annotators(markdown: str) -> str:
    """Инструкция для панели Argilla: памятка и разделы ``ARGILLA_SECTIONS`` с формулами, переведёнными
    в текст; длиннее ``GUIDELINES_LIMIT`` — ошибка (сервер такую инструкцию не примет)."""
    sections = _sections(_formulas_to_text(markdown))
    missing = [n for n in ARGILLA_SECTIONS if n not in sections]
    if missing:
        raise ValueError(f"в инструкции нет разделов {missing}")
    out = GUIDELINES_MEMO + MEMO_TAIL + "".join(sections[n].rstrip() + "\n\n" for n in ARGILLA_SECTIONS)
    out += "Остальные разделы — по кнопке «Полная инструкция» вверху страницы."
    out = _plain_alerts(out)
    if len(out) > GUIDELINES_LIMIT:
        raise ValueError(f"инструкция для Argilla — {len(out)} знаков, предел {GUIDELINES_LIMIT}")
    return out


DOC_CSS = """
:root { --fg: #1f2328; --muted: #57606a; --line: #d0d7de; --head: #f6f8fa; --bg: #ffffff; --code: #eff1f3;
        --link: #0969da; --red: #cf222e; --red-bg: #ffebe9; --red-line: #ff8182; --imp-bg: #ddf4ff; }
html[data-theme="dark"], html[data-theme="high-contrast"] {
        --fg: #e6edf3; --muted: #9198a1; --line: #3d444d; --head: #151b23; --bg: #0d1117; --code: #262c36;
        --link: #4493f8; --red: #ff7b72; --red-bg: rgba(248,81,73,.12); --red-line: #f85149;
        --imp-bg: rgba(56,139,253,.12); }
body { color: var(--fg); font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif; line-height: 1.55; }
h1 { font-size: 1.3em; margin: 4px 0 10px; } h2 { font-size: 1.15em; margin: 28px 0 8px; }
h3, h4 { font-size: 1em; margin: 18px 0 4px; }
p { margin: 5px 0; } ul, ol { margin: 4px 0 4px 20px; padding: 0; } li { margin: 3px 0; }
code { background: var(--code); border-radius: 4px; padding: 0 4px; font-size: 92%; }
table { border-collapse: collapse; margin: 6px 0; width: 100%; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: var(--head); }
a { color: var(--link); }
hr { border: 0; border-top: 1px solid var(--line); margin: 22px 0; }
blockquote { margin: 10px 0; padding: 4px 12px; border-left: 4px solid var(--line); }
.important { margin: 10px 0 18px; padding: 10px 14px; border-left: 4px solid var(--link); border-radius: 0 6px 6px 0;
             background: var(--imp-bg); font-size: 17px; line-height: 1.45; }
.important b { font-weight: 700; }
.caution { margin: 14px 0; padding: 8px 14px; border-left: 4px solid var(--red-line); border-radius: 0 6px 6px 0;
           background: var(--red-bg); color: var(--red); }
.caution b, .caution li, .caution p { color: var(--red); }
"""


def _questions_markdown() -> str:
    """Пояснения к пунктам формы из ``QUESTIONS``: заголовок пункта отдельной строкой, под ним описание
    (абзацы и списки) или краткая подсказка."""
    lines = ["## Пояснения к пунктам формы", ""]
    for q in QUESTIONS:
        desc = q.get("description") or HINTS.get(q["name"], "")
        lines += [f"### {q['title']}", ""] + ([desc, ""] if desc else [])
    return "\n".join(lines) + "\n"


def annotator_texts(markdown: str) -> str:
    """Все тексты, которые видит аннотатор (памятка, интерфейс, форма, инструкция), — для проверок."""
    return "\n".join([GUIDELINES_MEMO, INTERFACE_NOTES, _questions_markdown(), _formulas_to_text(markdown)]
                     + [q["title"] + " " + " ".join(map(str, q.get("labels", {}).values())) for q in QUESTIONS]
                     + list(HINTS.values()))


def full_guidelines_page(markdown: str) -> str:
    """Полная инструкция для отдельной вкладки: памятка, работа в интерфейсе, пояснения к пунктам формы и
    все разделы инструкции с формулами, переведёнными в текст."""
    text = _formulas_to_text(markdown)
    head = text.split("\n## ", 1)[0]                       # заголовок и строка версии
    sections = list(_sections(text).values())
    body = (GUIDELINES_MEMO + "\n" + INTERFACE_NOTES + "\n" + _questions_markdown() + "\n---\n\n"
            + head + "\n\n" + "\n".join(sections))
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>Инструкция аннотатора</title>"
            f"<style>{DOC_CSS} body {{ background: var(--bg); max-width: 960px; margin: 0 auto; padding: 16px 24px; }}"
            f"</style></head><body>{_guidelines_html(body)}</body></html>")


MEMO_CSS = """
body { font-size: 13px; }
.bar { display: flex; gap: 8px; align-items: center; }
.bar #toggle { flex: 1; text-align: left; font-size: 13px; font-weight: 600; padding: 5px 10px; }
.bar #full { font-size: 13px; padding: 5px 10px; }
#body { border: 1px solid var(--line); border-top: 0; border-radius: 0 0 6px 6px; padding: 4px 12px 8px; }
#body[hidden] { display: none; }
"""


# Панель памятки в шапке Argilla (над обеими панелями, решение 30.10). Элементы добавляются в документ
# страницы: окно поля и страница Argilla — один источник (srcdoc без sandbox). Раскрытие — на <details>,
# ссылка — blob-адрес, созданный от имени страницы: при переходе между записями Argilla пересоздаёт поля,
# и обработчики из окна поля перестали бы работать
BAR_CSS = """
#ann-memo { display: flex; gap: 10px; align-items: center; flex: 1; min-width: 0; margin: 0 16px; }
#ann-memo > details { flex: 1; min-width: 0; display: flex; }
#ann-memo .ann-btn { flex: 1; min-width: 0; box-sizing: border-box; display: block; text-align: center; cursor: pointer;
  font: 600 14px/1 -apple-system, "Segoe UI", Roboto, sans-serif; padding: 10px 14px; border-radius: 6px;
  border: 1px solid transparent; text-decoration: none; list-style: none; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; user-select: none; transition: filter .15s; }
#ann-memo .ann-btn:hover { filter: brightness(1.12); }
#ann-memo summary::-webkit-details-marker { display: none; }
#ann-memo .ann-memo-btn { background: #0969da; border-color: #0969da; color: #ffffff; }
#ann-memo .ann-full-btn { background: #1a7f37; border-color: #1a7f37; color: #ffffff; }
html[data-theme="dark"] #ann-memo .ann-memo-btn, html[data-theme="high-contrast"] #ann-memo .ann-memo-btn {
  background: #388bfd; border-color: #388bfd; color: #0d1117; }
html[data-theme="dark"] #ann-memo .ann-full-btn, html[data-theme="high-contrast"] #ann-memo .ann-full-btn {
  background: #3fb950; border-color: #3fb950; color: #0d1117; }
#ann-memo details[open] > .ann-memo-btn { box-shadow: inset 0 0 0 2px rgba(255,255,255,.75); }
#ann-memo .ann-panel { position: fixed; left: 50%; transform: translateX(-50%); width: min(980px, 94vw);
  overflow-y: auto; z-index: 1000; box-sizing: border-box; padding: 10px 20px 14px; border-radius: 8px;
  border: 1px solid #d0d7de; background: #ffffff; color: #1f2328; box-shadow: 0 12px 32px rgba(0,0,0,.35);
  font: 400 14px/1.55 -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif; text-align: left; white-space: normal; }
html[data-theme="dark"] #ann-memo .ann-panel, html[data-theme="high-contrast"] #ann-memo .ann-panel {
  border-color: #3d444d; background: #1c1c1c; color: #e6edf3; }
#ann-memo .ann-close { font-size: 12px; opacity: .7; margin-bottom: 4px; }
#ann-memo .ann-panel h1 { font-size: 18px; margin: 4px 0 8px; } #ann-memo .ann-panel h2 { font-size: 15px; margin: 26px 0 6px; }
#ann-memo .ann-panel h3 { font-size: 14px; margin: 18px 0 4px; }
#ann-memo .ann-panel p { margin: 5px 0; }
#ann-memo .ann-panel ul { margin: 4px 0 4px 20px; padding: 0; list-style: disc; }
#ann-memo .ann-panel ol { margin: 4px 0 4px 20px; padding: 0; list-style: decimal; }
#ann-memo .ann-panel li { margin: 3px 0; display: list-item; }
#ann-memo .ann-panel b { font-weight: 600; }
#ann-memo .ann-panel code { background: rgba(127,127,127,.18); border-radius: 4px; padding: 0 4px; }
#ann-memo .ann-panel hr { border: 0; border-top: 1px solid rgba(127,127,127,.35); margin: 18px 0; }
#ann-memo .ann-panel blockquote { margin: 10px 0; padding: 4px 12px; border-left: 4px solid rgba(127,127,127,.45); }
#ann-memo .ann-panel .important { margin: 6px 0 16px; padding: 10px 14px; border-left: 4px solid #0969da;
  border-radius: 0 6px 6px 0; background: #ddf4ff; font-size: 17px; line-height: 1.45; }
#ann-memo .ann-panel .important b { font-weight: 700; }
#ann-memo .ann-panel .caution { margin: 14px 0; padding: 8px 14px; border-left: 4px solid #ff8182; border-radius: 0 6px 6px 0;
  background: #ffebe9; color: #cf222e; }
#ann-memo .ann-panel .caution b, #ann-memo .ann-panel .caution li, #ann-memo .ann-panel .caution p { color: #cf222e; }
html[data-theme="dark"] #ann-memo .ann-panel .important, html[data-theme="high-contrast"] #ann-memo .ann-panel .important {
  border-color: #388bfd; background: rgba(56,139,253,.14); }
html[data-theme="dark"] #ann-memo .ann-panel .caution, html[data-theme="high-contrast"] #ann-memo .ann-panel .caution {
  border-color: #f85149; background: rgba(248,81,73,.12); color: #ff7b72; }
html[data-theme="dark"] #ann-memo .ann-panel .caution b, html[data-theme="dark"] #ann-memo .ann-panel .caution li,
html[data-theme="dark"] #ann-memo .ann-panel .caution p, html[data-theme="high-contrast"] #ann-memo .ann-panel .caution b,
html[data-theme="high-contrast"] #ann-memo .ann-panel .caution li,
html[data-theme="high-contrast"] #ann-memo .ann-panel .caution p { color: #ff7b72; }
"""
BAR_VERSION = "4"         # меняется при правке панели: открытая страница заменит старые кнопки и стили


def memo_template(markdown: str) -> str:
    """Памятка (решение 30.10): кнопки «Памятка ▾» и «Полная инструкция ↗» встраиваются в шапку Argilla над
    обеими панелями, памятка раскрывается поверх них окном с прокруткой, а поле записи «Памятка» скрывается.
    Если шапку найти не удалось (другая версия Argilla), памятка остаётся в поле, как раньше: свёрнута,
    раскрытая растягивает окно поля (FIT_JS). Хранится один раз в настройках датасета; значение поля у
    записей — константа ``{"v": 1}``."""
    core = GUIDELINES_MEMO.replace("# Памятка аннотатора", "", 1) + "\n" + INTERFACE_NOTES + "\n" + _questions_markdown()
    core_html = _guidelines_html(core)
    page = json.dumps(full_guidelines_page(markdown), ensure_ascii=False).replace("</", "<\\/")
    bar = json.dumps("<details><summary class='ann-btn ann-memo-btn'>Памятка ▾</summary><div class='ann-panel'>"
                     "<div class='ann-close'>Закрыть — нажмите «Памятка» ещё раз</div>" + core_html + "</div></details>"
                     "<a class='ann-btn ann-full-btn' target='_blank' rel='noopener' href='#FULL#'>Полная инструкция ↗</a>",
                     ensure_ascii=False).replace("</", "<\\/")
    bar_css = json.dumps(BAR_CSS, ensure_ascii=False).replace("</", "<\\/")
    return ("<!doctype html><html><head><meta charset='utf-8'><style>" + THEME_CSS + DOC_CSS + MEMO_CSS
            + "</style></head><body><div id='root'><div class='bar'>"
            "<button id='toggle' type='button'>▸ Памятка: правила E1–E5, порядок заполнения, пояснения к пунктам формы</button>"
            "<button id='full' type='button'>Полная инструкция ↗</button></div>"
            f"<div id='body' hidden>{core_html}</div></div><script>"
            f"const PAGE = {page}; const BAR = {bar}; const BAR_CSS = {bar_css}; const BAR_V = '{BAR_VERSION}';"
            """
  const pageWithTheme = (doc) =>
    PAGE.replace("<html>", '<html data-theme="' + (doc.documentElement.getAttribute("data-theme") || "light") + '">');
  // 1) шапка Argilla: кнопки над обеими панелями, поле записи «Памятка» скрывается
  let inHeader = false;
  try {
    const P = window.parent, PD = P.document;
    const host = P !== window ? PD.querySelector(".topbar--left") : null;
    if (host) {
      // старая версия кнопок и стилей (страница не перезагружалась после обновления датасета) — заменить
      const old = PD.getElementById("ann-memo");
      if (old && old.dataset.v !== BAR_V) { old.remove(); const os = PD.getElementById("ann-memo-style"); if (os) os.remove(); }
      if (!PD.getElementById("ann-memo-style")) {
        const st = PD.createElement("style"); st.id = "ann-memo-style"; st.textContent = BAR_CSS;
        PD.head.appendChild(st);
      }
      // кнопки на всю свободную ширину шапки (вариант 1, решение 30.10)
      host.style.flex = "1"; host.style.minWidth = "0"; host.style.display = "flex";
      if (!PD.getElementById("ann-memo")) {
        const url = P.URL.createObjectURL(new P.Blob([pageWithTheme(PD)], {type: "text/html"}));
        const box = PD.createElement("div"); box.id = "ann-memo"; box.dataset.v = BAR_V;
        box.innerHTML = BAR.replace("#FULL#", url);
        host.appendChild(box);
        const top = Math.ceil(host.parentElement.getBoundingClientRect().bottom) + 8;
        const panel = box.querySelector(".ann-panel");
        panel.style.top = top + "px";
        panel.style.maxHeight = "calc(100vh - " + (top + 16) + "px)";
      }
      const card = window.frameElement && window.frameElement.closest(".fields > div");
      if (card) card.style.display = "none";
      inHeader = true;
    }
  } catch (e) { inHeader = false; }
  // 2) запасной вариант: памятка в поле записи
  if (!inHeader) {
    const body = document.getElementById("body"), toggle = document.getElementById("toggle");
    toggle.addEventListener("click", () => {
      body.hidden = !body.hidden;
      toggle.textContent = (body.hidden ? "▸ " : "▾ ") + toggle.textContent.slice(2);
    });
    document.getElementById("full").addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([pageWithTheme(document)], {type: "text/html"}));
      if (!window.open(url, "_blank")) location.href = url;
    });
  }
""" + FIT_JS + "</script></body></html>")


def build_settings(guidelines: str, min_submitted: int, memo: str):
    import argilla as rg

    titles = {f["name"]: f["title"] for f in FIELDS}
    fields = [
        rg.CustomField(name="memo", title=titles["memo"], template=memo, advanced_mode=True, required=False),
        rg.TextField(name="question", title=titles["question"], use_markdown=True),
        rg.CustomField(name="card", title=titles["card"], template=CARD_TEMPLATE, advanced_mode=True),
        rg.CustomField(name="document", title=titles["document"], template=DOCUMENT_TEMPLATE, advanced_mode=True),
        rg.CustomField(name="retrieval", title=titles["retrieval"], template=RETRIEVAL_TEMPLATE, advanced_mode=True),
    ]
    kinds = {"label": rg.LabelQuestion, "multi": rg.MultiLabelQuestion, "text": rg.TextQuestion}
    questions = []
    for q in QUESTIONS:
        kwargs = {"name": q["name"], "title": q["title"], "required": q.get("required", False)}
        if HINTS.get(q["name"]):
            kwargs["description"] = HINTS[q["name"]]
        if q["kind"] != "text":
            kwargs["labels"] = q["labels"]
        questions.append(kinds[q["kind"]](**kwargs))
    return rg.Settings(guidelines=guidelines, fields=fields, questions=questions,
                       distribution=rg.TaskDistribution(min_submitted=min_submitted))


# ---------------------------------------------------------------- записи

ELLIPSIS = re.compile(r"…+|\.{3,}")


def evidence_parts(evidence_zh: str) -> list[str]:
    """Части цитаты для подсветки: цитата без переносов строк, её строки (перенос по ширине склеен
    при переводе, но в исходной цитате может остаться) и куски между многоточиями (цитата с пропуском,
    «……» в черновике)."""
    ev = (evidence_zh or "").strip()
    pieces = [s.strip() for s in ev.splitlines()]
    pieces += [s.strip() for line in pieces for s in ELLIPSIS.split(line)] if ELLIPSIS.search(ev) else []
    parts = [ev.replace("\n", "")] + [s for s in pieces if len(s) >= 4]
    return list(dict.fromkeys(p for p in parts if p))


def evidence_flags(paragraphs: list[dict], parts: list[str]) -> None:
    """Отметка абзацев evidence span: содержит часть цитаты, целиком входит в неё или пересекается
    с ней, когда цитата приходится на границу абзацев (в источнике строка перенесена внутри цитаты,
    а перевод разбил текст по этому переносу). Пробелы и переносы строк при сравнении не учитываются."""
    whole = parts[0] if parts else ""
    for p in paragraphs:
        p["ev"] = any(part in p["zh"] for part in parts) or (len(p["zh"]) >= 8 and p["zh"] in whole)
    if any(p["ev"] for p in paragraphs):
        return
    bounds, joined = [], ""
    for p in paragraphs:
        start = len(joined)
        joined += re.sub(r"\s+", "", p["zh"])
        bounds.append((start, len(joined)))
    for part in (re.sub(r"\s+", "", x) for x in parts):
        pos = joined.find(part) if part else -1
        while pos >= 0:
            end = pos + len(part)
            for p, (s, e) in zip(paragraphs, bounds):
                if s < end and pos < e:
                    p["ev"] = True
            pos = joined.find(part, end)


def card_value(position: dict) -> dict:
    """Источник одной строкой (поле ``card``, шаблон ``CARD_TEMPLATE``). Ответ, алиасы и evidence черновика —
    подсказки в полях формы, а не здесь: иначе они дублируются, а пустой ответ у кандидатов в $G^{\\bot}$
    бросается в глаза."""
    return {k: position[k] for k in ("netloc", "region", "published_at", "webpage_id", "uri")}


def suggestions_for(draft: dict) -> list[tuple[str, object]]:
    """Подсказки из черновика (решение 30.10): без z, правил, отвечаемости и метки инвариантности."""
    out: list[tuple[str, object]] = []
    if draft["anchor_date"]:
        out.append(("anchor_date", draft["anchor_date"]))
    for name, key, allowed in (("question_type", "question_type", QUESTION_TYPES),
                               ("category", "category", CATEGORIES),
                               ("difficulty", "difficulty", DIFFICULTIES)):
        if draft[key] in allowed:
            out.append((name, draft[key]))
    if draft["answer_canonical"]:
        out.append(("answer", draft["answer_canonical"]))
        if draft["answer_aliases"]:
            out.append(("aliases", "\n".join(draft["answer_aliases"])))
        if draft["answer_type"] in ANSWER_TYPES:
            out.append(("answer_type", draft["answer_type"]))
    if draft["evidence_span_ru"]:
        out.append(("evidence_ru", draft["evidence_span_ru"]))
    if draft["evidence_span_zh"]:
        out.append(("evidence_zh", draft["evidence_span_zh"]))
    if draft["supporting_ids"]:
        out.append(("supporting_ids", "\n".join(str(i) for i in draft["supporting_ids"])))
    return out


def load_materials(cfg: dict) -> list[dict]:
    """Материалы всех позиций раунда (``selection`` конфигурации: пилот, основной раунд или единый пул;
    черновики и топ-20 — из одного файла или из списка файлов); отсутствие перевода, топ-20 или
    черновика — ошибка."""
    paths = cfg["paths"]
    positions = round_positions(cfg)
    drafts = read_by_position(paths["drafts"])
    retrieval = read_by_position(paths["retrieval"])
    items, errors = [], []
    for p in positions:
        pid, wid = p["position_id"], p["webpage_id"]
        draft = drafts.get(pid)
        tr_path = REPO_ROOT / paths["translations"] / f"{wid}.json"
        if draft is None or draft["error"]:
            errors.append(f"{pid}: нет черновика")
        elif not draft["suitable"]:
            errors.append(f"{pid}: документ непригоден, нужна замена (sample_documents replace)")
        if not tr_path.exists():
            errors.append(f"{pid}: нет перевода ({tr_path.relative_to(REPO_ROOT)})")
        if pid not in retrieval:
            errors.append(f"{pid}: нет топ-20 ({paths['retrieval']})")
        if errors and errors[-1].startswith(pid):
            continue
        doc = json.loads((REPO_ROOT / paths["documents"] / f"{wid}.json").read_text(encoding="utf-8"))
        tr = json.loads(tr_path.read_text(encoding="utf-8"))
        items.append({"position": p, "draft": draft, "doc": doc, "translation": tr, "retrieval": retrieval[pid]})
    if errors:
        raise RuntimeError("материалы раунда неполны:\n  " + "\n  ".join(errors))
    return items


def record_payload(item: dict) -> dict:
    """Поля и подсказки записи Argilla (без ролей и служебных полей черновика)."""
    draft, pos, tr, ret = item["draft"], item["position"], item["translation"], item["retrieval"]
    paragraphs = [{"i": par["i"], "zh": par["zh"], "ru": par["ru"]} for par in tr["paragraphs"]]
    parts = evidence_parts(draft["evidence_span_zh"])
    evidence_flags(paragraphs, parts)
    results = [{k: h.get(k) for k in ("rank", "webpage_id", "score", "title_zh", "uri", "published_at", "source",
                                      "snippet_zh", "snippet_ru", "is_source_doc")} for h in ret["results"]]
    return {
        "id": pos["position_id"],
        "fields": {
            "memo": {"v": 1},
            "question": f"**{draft['question_ru']}**",
            "card": card_value(pos),
            "document": {"title_zh": item["doc"].get("title_zh") or "", "evidence_parts": parts,
                         "paragraphs": paragraphs},
            "retrieval": {"queries": ret["queries"], "results": results},
        },
        "suggestions": suggestions_for(draft),
    }


def _markdown_inline(text: str) -> str:
    """Строчный markdown: **жирный**, `код` и [ссылка](url)."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r"<a href='\2' target='_blank' rel='noopener'>\1</a>", out)


PREVIEW_STYLE = """
body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif; color: #1f2328;
       background: #f6f8fa; }
.top { padding: 8px 16px; color: #57606a; font-size: 13px; border-bottom: 1px solid #d0d7de; background: #fff; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: #000; color: #fff; font-size: 15px; }
.topbar--left { margin-right: auto; }
.wrap { display: flex; gap: 16px; padding: 16px; align-items: flex-start; }
.record { flex: 1 1 62%; min-width: 0; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 16px; }
.form { flex: 0 0 36%; position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow-y: auto;
        background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 16px; }
.fl { font-size: 12px; color: #57606a; margin: 14px 0 4px; text-transform: uppercase; letter-spacing: .03em; }
.q { margin: 0 0 16px; }
.qt { font-weight: 600; font-size: 14px; }
.qt .req { color: #cf222e; }
.qd { color: #57606a; font-size: 12px; margin: 2px 0 6px; white-space: pre-line; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid #d0d7de; border-radius: 14px; padding: 2px 10px; font-size: 13px; background: #fff;
        cursor: pointer; user-select: none; }
.chip:hover { border-color: #8c959f; }
.chip.on { background: #ddf4ff; border-color: #54aeff; }
.guide { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; margin: 16px 16px 0; padding: 8px 16px; }
.guide summary { cursor: pointer; font-weight: 600; }
.guide .gt { max-height: 420px; overflow-y: auto; font-size: 13px; line-height: 1.5; }
textarea { width: 100%; box-sizing: border-box; font: inherit; font-size: 13px; border: 1px solid #d0d7de;
           border-radius: 6px; padding: 6px 8px; resize: vertical; }
textarea.sug { background: #f1f8ff; border-color: #54aeff; }
.badge { display: inline-block; font-size: 11px; color: #0969da; margin-left: 6px; font-weight: 400; }
.legend { font-size: 12px; color: #57606a; border-top: 1px solid #eaeef2; padding-top: 8px; }
html[data-theme=dark] body { background: #111; color: #e6edf3; }
html[data-theme=dark] .top, html[data-theme=dark] .record, html[data-theme=dark] .form,
html[data-theme=dark] .guide { background: #1b1b1b; border-color: #3d444d; color: #e6edf3; }
html[data-theme=dark] textarea, html[data-theme=dark] .chip { background: #262626; color: #e6edf3; border-color: #3d444d; }
"""


def _preview_form(suggestions: dict[str, object]) -> str:
    """Форма разметки с подсказками из черновика: выбранная метка подсвечена, текст вписан в поле."""
    out = []
    for q in QUESTIONS:
        sug = suggestions.get(q["name"])
        badge = "<span class='badge'>предзаполнено</span>" if sug not in (None, "") else ""
        req = " <span class='req'>*</span>" if q.get("required") else ""
        head = f"<div class='qt'>{html.escape(q['title'])}{req}{badge}</div>"
        hint = HINTS.get(q["name"])                     # то, что Argilla покажет по значку ⓘ
        desc = f"<div class='qd'>ⓘ {html.escape(hint)}</div>" if hint else ""
        if q["kind"] == "text":
            value = html.escape(str(sug)) if sug not in (None, "") else ""
            rows = max(1, min(6, value.count("\n") + 1 + len(value) // 60))
            cls = " class='sug'" if value else ""
            body = f"<textarea rows='{rows}'{cls}>{value}</textarea>"
        else:
            chosen = set(sug) if isinstance(sug, list) else {sug}
            body = f"<div class='chips' data-multi='{int(q['kind'] == 'multi')}'>" + "".join(
                f"<span class='chip{' on' if key in chosen else ''}'>{html.escape(text)}</span>"
                for key, text in q["labels"].items()) + "</div>"
        out.append(f"<div class='q'>{head}{desc}{body}</div>")
    legend = ("<div class='legend'>Голубым отмечены предзаполненные значения: аннотатор принимает или правит их. "
              "Метки кликабельны (в вопросе 2 можно выбрать несколько). * — обязательный вопрос.</div>")
    # выбор меток: в одиночном вопросе — одна метка (повторный клик снимает), в вопросе 2 — несколько
    script = ("<script>document.querySelectorAll('.chips').forEach(g=>g.addEventListener('click',e=>{"
              "const c=e.target.closest('.chip');if(!c)return;if(g.dataset.multi==='1'){c.classList.toggle('on');return;}"
              "const was=c.classList.contains('on');g.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));"
              "if(!was)c.classList.add('on');}));</script>")
    return "".join(out) + legend + script


_ALERT_CLASSES = {"IMPORTANT": "important", "CAUTION": "caution", "WARNING": "caution"}
_ORDERED_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")


def _guidelines_html(markdown: str) -> str:
    """Markdown инструкции → HTML: заголовки, абзацы, маркированные и нумерованные списки, таблицы,
    разделители, цитаты; цитата ``> [!IMPORTANT]`` — блок крупным жирным шрифтом, ``> [!CAUTION]`` — красный."""
    out: list[str] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
        elif s.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            alert = re.fullmatch(r"\[!(\w+)\]", quoted[0].strip()) if quoted else None
            cls = _ALERT_CLASSES.get(alert.group(1).upper(), "") if alert else ""
            inner = _guidelines_html("\n".join(quoted[1:] if alert else quoted))
            out.append(f"<div class='{cls}'>{inner}</div>" if cls else f"<blockquote>{inner}</blockquote>")
        elif _ORDERED_ITEM.match(s):
            items = []
            start = int(_ORDERED_ITEM.match(s).group(1))
            while i < len(lines) and _ORDERED_ITEM.match(lines[i].strip()):
                items.append(f"<li>{_markdown_inline(_ORDERED_ITEM.match(lines[i].strip()).group(2))}</li>")
                i += 1
            out.append(f"<ol start='{start}'>" + "".join(items) + "</ol>")
        elif s == "---":
            out.append("<hr>")
            i += 1
        elif s.startswith("#"):
            level = min(4, len(s) - len(s.lstrip("#")))
            out.append(f"<h{level}>{_markdown_inline(s.lstrip('#').strip())}</h{level}>")
            i += 1
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, *rest = rows
            out.append("<table><tr>" + "".join(f"<th>{_markdown_inline(c)}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{_markdown_inline(c)}</td>" for c in r) + "</tr>"
                                 for r in rest) + "</table>")
        elif s.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(f"<li>{_markdown_inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
        else:
            out.append(f"<p>{_markdown_inline(s)}</p>")
            i += 1
    return "".join(out)


# Окружение iframe как в Argilla (Sandbox.vue): тема родителя, фон var(--bg-field), scrolling="no", высота —
# только та, что выставит сам шаблон (FIT_JS)
_SANDBOX_HEAD = ("<script>document.documentElement.setAttribute('data-theme',"
                 "parent.document.documentElement.getAttribute('data-theme')||'light');</script>"
                 "<style>:root{--bg-field:#ffffff} html[data-theme=dark]{--bg-field:#262626}"
                 "body{background-color:var(--bg-field)}</style>")


def write_preview(payload: dict, path: Path, guidelines: str = "", memo: str = "", dataset: str = "pilot-v0.1") -> None:
    """Локальный HTML: инструкция (свёрнута, как панель Argilla), запись слева (поля в iframe, как в Argilla)
    и форма разметки справа с предзаполненными значениями; переключатель светлой и тёмной темы."""
    record_js = json.dumps({"fields": payload["fields"]}, ensure_ascii=False).replace("</", "<\\/")
    titles = {f["name"]: f["title"] for f in FIELDS}

    def frame(template: str) -> str:
        page = _SANDBOX_HEAD + template.replace("<script>", f"<script>const record = {record_js};", 1)
        return (f"<iframe scrolling='no' style='width:100%;height:40px;border:0;display:block' "
                f"srcdoc=\"{html.escape(page, quote=True)}\"></iframe>")

    # поля — как в Argilla (RecordFields.vue): каждое в своём div внутри .fields
    record = ["<div class='fields'>",
              f"<div><div class='fl'>{titles['memo']}</div>{frame(memo)}</div>" if memo else "",
              f"<div><div class='fl'>{titles['question']}</div>"
              f"<h3 style='margin:0'>{_markdown_inline(payload['fields']['question'])}</h3></div>",
              f"<div><div class='fl'>{titles['card']}</div>{frame(CARD_TEMPLATE)}</div>",
              f"<div><div class='fl'>{titles['document']}</div>{frame(DOCUMENT_TEMPLATE)}</div>",
              f"<div><div class='fl'>{titles['retrieval']}</div>{frame(RETRIEVAL_TEMPLATE)}</div>",
              "</div>"]
    form = _preview_form(dict(payload["suggestions"]))
    theme_js = ("<script>document.getElementById('theme').addEventListener('click',()=>{"
                "const r=document.documentElement;const t=r.getAttribute('data-theme')==='dark'?'light':'dark';"
                "r.setAttribute('data-theme',t);document.querySelectorAll('iframe').forEach(f=>"
                "f.contentDocument.documentElement.setAttribute('data-theme',t));});</script>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<!doctype html><html data-theme='light'><head><meta charset='utf-8'>"
        f"<title>Предпросмотр {html.escape(payload['id'])}</title><style>{PREVIEW_STYLE}</style></head><body>"
        # шапка — как в Argilla (HeaderFeedbackTask.vue): .topbar--left между крошками и правой частью
        f"<div class='topbar'><span>Home / staging / {html.escape(dataset)} · {html.escape(payload['id'])}</span>"
        f"<div class='topbar--left'></div><div class='topbar--right'>"
        f"<button id='theme' type='button'>Светлая / тёмная тема</button></div></div>"
        + (f"<details class='guide'><summary>Инструкция (панель Argilla)</summary><div class='gt'>"
           f"{_guidelines_html(guidelines)}</div></details>" if guidelines else "")
        + f"<div class='wrap'><div class='record'>{''.join(record)}</div>"
        f"<div class='form'>{form}</div></div>{theme_js}</body></html>", encoding="utf-8")


# ---------------------------------------------------------------- Argilla

def client(cfg: dict):
    import argilla as rg

    a = cfg["argilla"]
    if not a.get("api_url") or not a.get("api_key"):
        raise RuntimeError("нет ARGILLA_API_URL или ARGILLA_API_KEY в .env")
    return rg.Argilla(api_url=a["api_url"], api_key=a["api_key"], timeout=120)


def setup(cfg: dict) -> list[str]:
    """Рабочие пространства и учётные записи; пароли новых записей — в файл вне репозитория."""
    import argilla as rg

    a, c = cfg["argilla"], client(cfg)
    plan = [(u, a["workspace"]) for u in a["annotators"]]
    workspaces = {}
    for name in {ws for _, ws in plan}:
        workspaces[name] = c.workspaces(name) or rg.Workspace(name=name, client=c).create()
    accounts_path = REPO_ROOT / cfg["paths"]["accounts"]
    accounts_path.parent.mkdir(parents=True, exist_ok=True)
    created, report = [], []
    for username, ws in plan:
        user = c.users(username)
        if user is None:
            password = secrets.token_hex(8)
            user = rg.User(username=username, first_name=username.upper(), role="annotator",
                           password=password, client=c).create()
            created.append({"username": username, "password": password, "workspace": ws, "role": "annotator"})
            report.append(f"{username}: создан, рабочее пространство {ws}")
        else:
            report.append(f"{username}: уже есть")
        if username not in {u.username for u in workspaces[ws].users}:
            user.add_to_workspace(workspaces[ws])
    if created:
        new_file = not accounts_path.exists()
        with open(accounts_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["username", "password", "workspace", "role"])
            if new_file:
                writer.writeheader()
            writer.writerows(created)
        os.chmod(accounts_path, 0o600)
        report.append(f"пароли новых учётных записей: {accounts_path.relative_to(REPO_ROOT)} (chmod 600)")
    return report


def annotator_guidelines(cfg: dict) -> str:
    return guidelines_for_annotators((REPO_ROOT / cfg["paths"]["guidelines"]).read_text(encoding="utf-8"))


def annotator_memo(cfg: dict) -> str:
    return memo_template((REPO_ROOT / cfg["paths"]["guidelines"]).read_text(encoding="utf-8"))


def find_dataset(c, workspace: str, name: str):
    """Датасет или ``None``; клиент Argilla 2.8.0 падает, если рабочего пространства ещё нет."""
    if c.workspaces(workspace) is None:
        return None
    return c.datasets(name=name, workspace=workspace)


def get_dataset(cfg: dict, c, create: bool = False):
    import argilla as rg

    a = cfg["argilla"]
    ds = find_dataset(c, a["workspace"], a["dataset"])
    if ds is None and create:
        if c.workspaces(a["workspace"]) is None:
            rg.Workspace(name=a["workspace"], client=c).create()      # без пользователей: видит только владелец
        ds = rg.Dataset(name=a["dataset"], workspace=a["workspace"], client=c,
                        settings=build_settings(annotator_guidelines(cfg), a["min_submitted"],
                                                annotator_memo(cfg))).create()
    if ds is None:
        raise RuntimeError(f"нет датасета {a['dataset']} в {a['workspace']}: сначала push")
    return ds


def count_responses(ds, submitted_only: bool = False) -> int:
    """Ответы датасета; Argilla сама сохраняет черновики ответов (status = draft) при работе с формой."""
    return sum(1 for rec in ds.records(with_responses=True) for r in rec.responses
               if not submitted_only or str(getattr(r.status, "value", r.status)) == "submitted")


def build_payloads(cfg: dict) -> list[dict]:
    """Записи раунда в порядке выдачи (перемешаны с seed из конфигурации; порядок одинаков для всех аннотаторов)."""
    payloads = [record_payload(it) for it in load_materials(cfg)]
    random.Random(cfg["argilla"]["seed"]).shuffle(payloads)
    return payloads


def push(cfg: dict, preview: Path | None, record_id: str | None = None, upsert: bool = False) -> str:
    import argilla as rg

    payloads = build_payloads(cfg)
    if preview:
        chosen = next((p for p in payloads if p["id"] == record_id), None) if record_id else payloads[0]
        if chosen is None:
            raise ValueError(f"{record_id}: нет такой записи в раунде")
        write_preview(chosen, preview, annotator_guidelines(cfg), annotator_memo(cfg), cfg["argilla"]["dataset"])
        return f"предпросмотр {chosen['id']}: {preview}"
    problems = preflight_problems(cfg, payloads)
    if problems:
        raise RuntimeError("проверка перед загрузкой не пройдена:\n  " + "\n  ".join(problems))
    a, c = cfg["argilla"], client(cfg)
    existing = find_dataset(c, a["workspace"], a["dataset"])
    if existing is not None:
        n_resp = count_responses(existing)
        if not upsert:
            raise RuntimeError(f"датасет {a['dataset']} в {a['workspace']} уже есть (ответов: {n_resp}); "
                               "обновить записи — push --upsert (ответы сохраняются)")
        print(f"обновление записей существующего датасета; ответов в нём: {n_resp}", file=sys.stderr)
    ds = get_dataset(cfg, c, create=True)
    records = [rg.Record(id=p["id"], fields=p["fields"],
                         suggestions=[rg.Suggestion(question_name=n, value=v, agent="prefill", type="model")
                                      for n, v in p["suggestions"]])
               for p in payloads]
    # записи большие (документ, перевод, топ-20): пачка по умолчанию (256) не укладывается в таймаут записи
    ds.records.log(records, batch_size=LOG_BATCH)
    n = sum(1 for _ in ds.records)
    return f"{a['dataset']} ({a['workspace']}): записей {n}"


def progress(cfg: dict) -> dict:
    return get_dataset(cfg, client(cfg)).progress(with_users_distribution=True)


def _options(q) -> list[dict] | None:
    """Метки вопроса как на сервере: [{"value", "text"}]; у текстовых вопросов — ``None``."""
    opts = getattr(getattr(q._model, "settings", None), "options", None)
    return [{"value": o["value"], "text": o.get("text")} for o in opts] if opts else None


def settings_problems(current, wanted) -> list[str]:
    """Расхождения настроек датасета на сервере с локальными: инструкция, состав и заголовки полей, шаблоны
    полей, заголовки, подсказки ⓘ, метки и обязательность вопросов."""
    problems = []
    if (current.guidelines or "").rstrip() != (wanted.guidelines or "").rstrip():  # сервер срезает концевые пробелы
        problems.append("инструкция на сервере отличается от локальной")
    if [f.name for f in current.fields] != [f.name for f in wanted.fields]:
        return problems + [f"поля: {[f.name for f in current.fields]}"]
    if [q.name for q in current.questions] != [q.name for q in wanted.questions]:
        return problems + [f"вопросы: {[q.name for q in current.questions]}"]
    for cur, want in zip(current.fields, wanted.fields):
        if cur.title != want.title:
            problems.append(f"поле {want.name}: заголовок")
        if getattr(want, "template", None) is not None and cur.template != want.template:
            problems.append(f"поле {want.name}: шаблон")
    for cur, want in zip(current.questions, wanted.questions):
        for attr in ("title", "description", "required"):
            if getattr(cur, attr) != getattr(want, attr):
                problems.append(f"вопрос {want.name}: {attr}")
        if _options(cur) != _options(want):
            problems.append(f"вопрос {want.name}: метки")
    return problems


def update_settings(cfg: dict) -> str:
    """Обновление настроек существующего датасета без пересоздания: инструкция, шаблоны и заголовки полей,
    заголовки, подсказки и подписи меток вопросов. Ключи полей, вопросов и меток должны совпадать с
    локальными (иначе ответы аннотаторов разошлись бы со схемой) — при расхождении ничего не меняется.
    Записи, подсказки из черновиков и ответы не затрагиваются."""
    a, c = cfg["argilla"], client(cfg)
    ds = get_dataset(cfg, c)
    wanted = build_settings(annotator_guidelines(cfg), a["min_submitted"], annotator_memo(cfg))
    s = ds.settings
    keys = lambda st: ([f.name for f in st.fields], [q.name for q in st.questions],
                       [[o["value"] for o in (_options(q) or [])] for q in st.questions])
    if keys(s) != keys(wanted):
        raise RuntimeError("ключи полей, вопросов или меток на сервере не совпадают с локальными: "
                           "обновление настроек отменено (нужен новый датасет)")
    before = settings_problems(s, wanted)
    if not before:
        return f"{a['dataset']} ({a['workspace']}): настройки уже совпадают с локальными"
    s.guidelines = wanted.guidelines
    for cur, want in zip(s.fields, wanted.fields):
        cur.title = want.title
        if getattr(want, "template", None) is not None:
            cur.template = want.template
    for cur, want in zip(s.questions, wanted.questions):
        cur.title, cur.description = want.title, want.description
        if _options(want) is not None:
            cur._model.settings.options = want._model.settings.options     # подписи меток при тех же ключах
    ds.update()
    after = settings_problems(get_dataset(cfg, client(cfg)).settings, wanted)
    head = f"{a['dataset']} ({a['workspace']}): обновлено расхождений {len(before)}"
    return head + ("; сверка после обновления пройдена" if not after
                   else "; после обновления остались расхождения:\n  " + "\n  ".join(after))


# ---------------------------------------------------------------- проверки до и после загрузки

def _norm(value):
    """Значение поля для сравнения: JSON с сортировкой ключей (числа и строки — как есть)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def preflight_problems(cfg: dict, payloads: list[dict]) -> list[str]:
    """Проверка записей перед загрузкой (план, шаг B)."""
    positions = round_positions(cfg)
    expected = {p["position_id"] for p in positions}
    ids = [p["id"] for p in payloads]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("повторяющиеся id записей")
    if set(ids) != expected:
        problems.append(f"id записей не совпадают с позициями раунда: лишние {sorted(set(ids) - expected)}, "
                        f"нет {sorted(expected - set(ids))}")
    labels = {q["name"]: q for q in QUESTIONS}
    for p in payloads:
        if not any(par["ev"] for par in p["fields"]["document"]["paragraphs"]):
            problems.append(f"{p['id']}: evidence span не найден ни в одном абзаце")
        for name, value in p["suggestions"]:
            q = labels.get(name)
            if q is None:
                problems.append(f"{p['id']}: подсказка к несуществующему вопросу {name}")
            elif q["kind"] == "text" and not (isinstance(value, str) and value.strip()):
                problems.append(f"{p['id']}: пустая текстовая подсказка {name}")
            elif q["kind"] != "text" and value not in q["labels"]:
                problems.append(f"{p['id']}: значение {value!r} вне меток вопроса {name}")
            if name == "anchor_date" and not ANCHOR_RE.match(str(value)):
                problems.append(f"{p['id']}: дата-якорь {value!r} в неверном формате")
        if "черновик" in _norm({k: v for k, v in p["fields"].items() if k != "document"}).lower():
            problems.append(f"{p['id']}: в полях записи упоминается черновик")
    ui_text = " ".join([f["title"] for f in FIELDS] + [q["title"] + q.get("description", "") for q in QUESTIONS])
    if "черновик" in ui_text.lower():
        problems.append("в заголовках или описаниях формы упоминается черновик")
    try:
        annotator_guidelines(cfg)
    except ValueError as exc:
        problems.append(f"инструкция: {exc}")
    # памятка, форма и инструкция: без путей репозитория, ссылок на ADR, формул и обозначений постановки
    guide_md = (REPO_ROOT / cfg["paths"]["guidelines"]).read_text(encoding="utf-8")
    texts = annotator_texts(guide_md)
    leaked = [s for s in FORBIDDEN_IN_ANNOTATOR_TEXT if s.lower() in texts.lower()]
    if leaked:
        problems.append(f"в текстах для аннотаторов недопустимые фрагменты: {leaked}")
    page = full_guidelines_page(guide_md)
    if "$`" in page or "\\mathrm" in page:
        problems.append("в полной инструкции остались формулы в разметке GitHub")
    long_hints = [n for n, h in HINTS.items() if len(h) > HINT_MAX]
    if long_hints:
        problems.append(f"подсказки длиннее {HINT_MAX} знаков: {long_hints}")
    problems += template_syntax_problems(cfg)
    return problems


def template_syntax_problems(cfg: dict) -> list[str]:
    """Синтаксис скриптов шаблонов полей (``node --check``): ошибка в скрипте даёт пустое поле в Argilla.
    Без Node проверка пропускается с предупреждением."""
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if node is None:
        print("предупреждение: node не найден, синтаксис шаблонов не проверен", file=sys.stderr)
        return []
    problems = []
    templates = {"memo": annotator_memo(cfg), "card": CARD_TEMPLATE, "document": DOCUMENT_TEMPLATE,
                 "retrieval": RETRIEVAL_TEMPLATE}
    for name, tpl in templates.items():
        js = "const record = {fields: {}};\n" + "\n".join(re.findall(r"<script>(.*?)</script>", tpl, flags=re.S))
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(js)
        try:
            run = subprocess.run([node, "--check", fh.name], capture_output=True, text=True)
        finally:
            os.unlink(fh.name)
        if run.returncode != 0:
            problems.append(f"шаблон {name}: ошибка синтаксиса JS — {run.stderr.strip().splitlines()[-1]}")
    return problems


def write_manifest(cfg: dict, payloads: list[dict]) -> Path:
    """Отпечаток входных данных загрузки: sha256 файлов, переводов, git HEAD, время."""
    import hashlib
    import subprocess
    from datetime import datetime, timezone

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def shas(value: str | list[str]) -> dict[str, str]:
        return {rel: sha(REPO_ROOT / rel) for rel in ([value] if isinstance(value, str) else value)}

    paths = cfg["paths"]
    translations = {}
    for p in round_positions(cfg):
        tr = json.loads((REPO_ROOT / paths["translations"] / f"{p['webpage_id']}.json").read_text(encoding="utf-8"))
        translations[p["position_id"]] = tr["sha256"]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": head,
        "dataset": cfg["argilla"]["dataset"], "workspace": cfg["argilla"]["workspace"],
        "records": [p["id"] for p in payloads],
        "drafts_sha256": shas(paths["drafts"]),
        "retrieval_sha256": shas(paths["retrieval"]),
        "translations_sha256": translations,
        "guidelines_sha256": hashlib.sha256(annotator_guidelines(cfg).encode("utf-8")).hexdigest(),
    }
    out = REPO_ROOT / paths.get("manifest", "data/_cache/upload_manifest.json")
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def preflight(cfg: dict) -> str:
    payloads = build_payloads(cfg)
    problems = preflight_problems(cfg, payloads)
    if problems:
        return "проверка не пройдена:\n  " + "\n  ".join(problems)
    out = write_manifest(cfg, payloads)
    n_sug = sum(len(p["suggestions"]) for p in payloads)
    return (f"проверка пройдена: записей {len(payloads)}, подсказок {n_sug}, у всех записей подсвечен evidence; "
            f"отпечаток — {out.relative_to(REPO_ROOT)}")


def verify(cfg: dict, allow_responses: bool = False) -> str:
    """Сверка датасета на сервере с локальными записями (план, шаги C–D)."""
    a, c = cfg["argilla"], client(cfg)
    ds = get_dataset(cfg, c)
    payloads = {p["id"]: p for p in build_payloads(cfg)}
    s = ds.settings
    problems = settings_problems(s, build_settings(annotator_guidelines(cfg), a["min_submitted"], annotator_memo(cfg)))
    if s.distribution.min_submitted != a["min_submitted"]:
        problems.append(f"min_submitted = {s.distribution.min_submitted}")
    seen, n_resp = set(), 0
    for rec in ds.records(with_suggestions=True, with_responses=True):
        seen.add(rec.id)
        p = payloads.get(rec.id)
        if p is None:
            problems.append(f"{rec.id}: лишняя запись на сервере")
            continue
        for name, value in p["fields"].items():
            if _norm(rec.fields[name]) != _norm(value):
                problems.append(f"{rec.id}: поле {name} отличается")
        got = {sg.question_name: sg.value for sg in rec.suggestions}
        if _norm(got) != _norm(dict(p["suggestions"])):
            problems.append(f"{rec.id}: подсказки отличаются")
        n_resp += len(list(rec.responses))
    missing = sorted(set(payloads) - seen)
    if missing:
        problems.append(f"нет записей: {missing}")
    if n_resp and not allow_responses:
        problems.append(f"в датасете уже есть ответы: {n_resp}")
    head = f"{a['dataset']} ({a['workspace']}): записей {len(seen)}, ответов {n_resp}"
    return head + ("; сверка пройдена" if not problems else "; расхождения:\n  " + "\n  ".join(problems))


def delete_dataset(cfg: dict, production: tuple[str, str]) -> str:
    """Удаление тестовой копии: рабочий датасет не удаляется никогда, тестовый — только без отправленных
    ответов (автосохранённые черновики ответов владельца при просмотре формы удалению не мешают)."""
    a, c = cfg["argilla"], client(cfg)
    if (a["workspace"], a["dataset"]) == production or a["workspace"] == production[0]:
        raise RuntimeError("рабочий датасет и его рабочее пространство этой командой не удаляются")
    ds = get_dataset(cfg, c)
    n_resp = count_responses(ds, submitted_only=True)
    if n_resp:
        raise RuntimeError(f"в датасете есть отправленные ответы ({n_resp}): удаление отменено")
    ds.delete()
    ws = c.workspaces(a["workspace"])
    note = ""
    if ws is not None and not list(ws.datasets) and not list(ws.users):
        ws.delete()
        note = f"; пустое рабочее пространство {a['workspace']} удалено"
    return f"удалён {a['dataset']} ({a['workspace']}){note}"


def retire(cfg: dict, production: tuple[str, str], dataset: str | None, users: Sequence[str],
           workspaces: Sequence[str], dry_run: bool = False) -> list[str]:
    """Снятие с сервера прежних объектов (ADR-027): датасета в рабочем пространстве конфигурации,
    учётных записей и рабочих пространств. Рабочий датасет не удаляется никогда; датасет — только без
    ответов, включая черновики ответов (значит, никто не начал разметку); рабочее пространство — только
    пустое и не рабочее; учётная запись — только не из списка аннотаторов конфигурации."""
    a, c = cfg["argilla"], client(cfg)
    report = []
    if dataset:
        if (a["workspace"], dataset) == production or dataset == production[1]:
            raise RuntimeError(f"{dataset}: рабочий датасет не снимается")
        ds = find_dataset(c, a["workspace"], dataset)
        if ds is None:
            report.append(f"датасета {dataset} в {a['workspace']} нет")
        else:
            n_resp = count_responses(ds)
            if n_resp:
                raise RuntimeError(f"{dataset}: в датасете есть ответы ({n_resp}, включая черновики) — снятие отменено")
            report.append(f"датасет {dataset} ({a['workspace']}): записей {sum(1 for _ in ds.records)}, ответов 0"
                          + ("" if dry_run else " — удалён"))
            if not dry_run:
                ds.delete()
    for username in users:
        if username in a["annotators"] or username == "owner":
            raise RuntimeError(f"{username}: учётная запись аннотатора или владельца не снимается")
        user = c.users(username)
        if user is None:
            report.append(f"учётной записи {username} нет")
            continue
        report.append(f"учётная запись {username} ({user.role})" + ("" if dry_run else " — удалена"))
        if not dry_run:
            user.delete()
    for name in workspaces:
        if name == a["workspace"]:
            raise RuntimeError(f"{name}: рабочее пространство аннотаторов не снимается")
        ws = c.workspaces(name)
        if ws is None:
            report.append(f"рабочего пространства {name} нет")
            continue
        datasets = [d.name for d in ws.datasets]
        if datasets:
            raise RuntimeError(f"{name}: в рабочем пространстве есть датасеты {datasets} — снятие отменено")
        members = [u.username for u in ws.users]
        report.append(f"рабочее пространство {name} (пользователи: {members or 'нет'})" + ("" if dry_run else " — удалено"))
        if not dry_run:
            for username in members:
                c.users(username).remove_from_workspace(ws)
            ws.delete()
    return report


# ---------------------------------------------------------------- ответы

def _lines(value) -> list[str]:
    return [s.strip() for s in str(value or "").splitlines() if s.strip()]


def normalize_response(values: dict) -> dict:
    """Значения ответа в типы схемы записи: метки 0/1, списки, целые ``webpage_id``."""
    def as_int(v):
        return int(v) if v not in (None, "") else None

    ids, bad_ids = [], []
    for s in _lines(values.get("supporting_ids")):
        (ids if re.fullmatch(r"\d+", s) else bad_ids).append(int(s) if s.isdigit() else s)
    return {
        "time_invariant": as_int(values.get("z")),
        "exclusion_rules": sorted(values.get("excl") or []),
        "answerable": as_int(values.get("answerable")),
        "label": values.get("ti_label"),
        "anchor_date": (values.get("anchor_date") or "").strip() or None,
        "question_type": values.get("question_type"),
        "category": values.get("category"),
        "difficulty": values.get("difficulty"),
        "answer_canonical_fixed": (values.get("answer") or "").strip() or None,
        "answer_aliases_fixed": _lines(values.get("aliases")),
        "answer_type": values.get("answer_type"),
        "evidence_span_ru": (values.get("evidence_ru") or "").strip() or None,
        "evidence_span_zh": (values.get("evidence_zh") or "").strip() or None,
        "supporting_ids": ids,
        "supporting_ids_invalid": bad_ids,
        "requires_multi_doc": {"yes": True, "no": False}.get(values.get("multi_doc")),
        "comment": (values.get("comment") or "").strip() or None,
    }


def validate_annotation(a: dict) -> list[str]:
    """Нарушения порядка разметки (инструкция аннотатора, §1): сообщаются, строки не отбрасываются."""
    problems = []
    if a["time_invariant"] == 0 and not a["exclusion_rules"] and not a["comment"]:
        problems.append("z = 0 без правила и комментария")
    if a["time_invariant"] == 1:
        if a["answerable"] is None:
            problems.append("z = 1 без отвечаемости")
        if not a["label"]:
            problems.append("z = 1 без метки инвариантности")
        if not a["anchor_date"] or not ANCHOR_RE.match(a["anchor_date"]):
            problems.append("дата-якорь отсутствует или в неверном формате")
        if a["answerable"] == 1 and not a["answer_canonical_fixed"]:
            problems.append("отвечаемый вопрос без ответа")
        if a["answerable"] == 1 and not a["supporting_ids"]:
            problems.append("отвечаемый вопрос без S*")
    if a["supporting_ids_invalid"]:
        problems.append(f"нечисловые webpage_id: {a['supporting_ids_invalid']}")
    for key in ("evidence_span_ru", "evidence_span_zh"):
        if a[key] and len(a[key]) > 300:
            problems.append(f"{key} длиннее 300 знаков")
    return problems


def pull(cfg: dict) -> str:
    c = client(cfg)
    ds = get_dataset(cfg, c)
    users = {u.id: u.username for u in c.users}
    rows, problems = [], []
    for rec in ds.records(with_responses=True):
        by_user: dict = {}
        for resp in rec.responses:
            by_user.setdefault(resp.user_id, {"values": {}, "status": None})
            by_user[resp.user_id]["values"][resp.question_name] = resp.value
            by_user[resp.user_id]["status"] = str(getattr(resp.status, "value", resp.status))
        for user_id, r in by_user.items():
            if r["status"] != "submitted":
                continue
            username = users.get(user_id, str(user_id))
            row = {"draft_id": rec.id, "annotator": username.upper(), **normalize_response(r["values"])}
            issues = validate_annotation(row)
            row["problems"] = issues
            problems += [f"{rec.id} {row['annotator']}: {p}" for p in issues]
            rows.append(row)
    rows.sort(key=lambda r: (r["draft_id"], r["annotator"]))
    out = REPO_ROOT / cfg["paths"]["annotations"]
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    per = {}
    for r in rows:
        per[r["annotator"]] = per.get(r["annotator"], 0) + 1
    lines = [f"{out.relative_to(REPO_ROOT)}: ответов {len(rows)} ({', '.join(f'{k} — {v}' for k, v in sorted(per.items()))})"]
    complete = sum(1 for d in {r["draft_id"] for r in rows} if sum(r["draft_id"] == d for r in rows) >= 3)
    lines.append(f"записей с тремя ответами: {complete}")
    if problems:
        lines.append(f"нарушения ({len(problems)}):\n  " + "\n  ".join(problems))
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["setup", "preflight", "push", "update-settings", "verify", "progress",
                                            "pull", "delete", "retire"])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--workspace", default=None, help="рабочее пространство (по умолчанию из конфигурации)")
    parser.add_argument("--dataset", default=None, help="датасет (по умолчанию из конфигурации)")
    parser.add_argument("--preview", type=Path, default=None, help="push: только локальный HTML одной записи")
    parser.add_argument("--record", default=None, help="push --preview: позиция для предпросмотра (по умолчанию первая)")
    parser.add_argument("--upsert", action="store_true", help="push: обновить записи существующего датасета")
    parser.add_argument("--allow-responses", action="store_true", help="verify: ответы в датасете не считать ошибкой")
    parser.add_argument("--user", action="append", default=[], help="retire: учётная запись к удалению (можно несколько)")
    parser.add_argument("--workspace-name", action="append", default=[],
                        help="retire: пустое рабочее пространство к удалению (можно несколько)")
    parser.add_argument("--dry-run", action="store_true", help="retire: только показать, что будет снято")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(REPO_ROOT / args.config)
    production = (cfg["argilla"]["workspace"], cfg["argilla"]["dataset"])
    if args.workspace:
        cfg["argilla"]["workspace"] = args.workspace
    if args.dataset:
        cfg["argilla"]["dataset"] = args.dataset
    if args.command == "setup":
        print("\n".join(setup(cfg)))
    elif args.command == "preflight":
        print(preflight(cfg))
    elif args.command == "push":
        preview = (REPO_ROOT / args.preview) if args.preview and not args.preview.is_absolute() else args.preview
        print(push(cfg, preview, args.record, upsert=args.upsert))
    elif args.command == "update-settings":
        print(update_settings(cfg))
    elif args.command == "verify":
        print(verify(cfg, allow_responses=args.allow_responses))
    elif args.command == "progress":
        print(json.dumps(progress(cfg), ensure_ascii=False, indent=1, default=str))
    elif args.command == "pull":
        print(pull(cfg))
    elif args.command == "delete":
        print(delete_dataset(cfg, production))
    elif args.command == "retire":
        print("\n".join(retire(cfg, production, args.dataset, args.user, args.workspace_name, args.dry_run)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
