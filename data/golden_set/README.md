# Эталонная выборка (Golden Set)

Эталонная выборка $G = G^+ \sqcup G^{\varnothing}$ вопросов на русском языке с инвариантным во времени ответом по корпусу новостных текстов $D$ — основной артефакт данных выпускной квалификационной работы «Система оценки качества ответов больших языковых моделей по новостным текстам стран Восточной Азии». Формальные определения — в [`docs/problem_statement.md`](../../docs/problem_statement.md), процедура разметки — в [`docs/annotation_guidelines.md`](../../docs/annotation_guidelines.md), схема записи — в [`schema.json`](schema.json), история версий — в [`CHANGELOG.md`](CHANGELOG.md).

## Назначение

Выборка служит эталоном для вычисления семейства метрик $M = \{m_k\}$ качества ответов $\hat a = f(q)$ систем $f \in \mathcal{H}_{\text{eval}}$: метрик по эталону (EM, F1, BERTScore, судья-LLM «правильность относительно $A^*_i$»), метрик цитирования ($\mathrm{CP}_{\text{id}}$, $\mathrm{CR}_{\text{id}}$, $\mathrm{CP}_{\text{ent}}$), метрик отказа ($\mathrm{AR}$, $\mathrm{FAR}$) и метрик поиска (Hit@k, Recall@k, MRR, nDCG@k относительно $S^*_i$). Подмножество $G_h \subset G^+$ объёмом $n_h = 100$ используется для человеческой оценки ответов и валидации метрик (см. [`data/human_validation/README.md`](../human_validation/README.md)).

Корпус $D$ — снимок $D_{t_0}$ китайскоязычных СМИ КНР, Тайваня, Гонконга и Сингапура (оригинал и машинный перевод на русский), индексированный в промышленной системе «Chinese Media Analysis» (ИВ РАН, репозиторий `ivran-lab/chinese-media`). Название работы говорит о странах Восточной Азии в целом; в версии `v1.0` корпус — только китайскоязычный, расширение на японские и корейские источники — дальнейшая работа, для которой протокол разметки и схема записи спроектированы языконезависимыми.

## Состав

$G = G^+ \sqcup G^{\varnothing}$, $n = n_+ + n_\varnothing$.

| Часть | Что содержит | Правильный ответ | Объём |
|---|---|---|---|
| $G^+$ | Вопросы $q_i$ с каноническим ответом $A^*_i$ (канонический вариант и алиасы), множеством документов-источников $S^*_i \subset \mathcal{I}$, $\lvert S^*_i \rvert \ge 1$, и метаданными $\mu_i$ | $a^*(q_i) \in \mathcal{A}^+$ | $n_+$ |
| $G^{\varnothing}$ | Вопросы, инвариантные по форме и с датой-якорем, но не подтверждаемые корпусом | отказ $\varnothing$ («Я не знаю.») | $n_\varnothing \approx 0{,}1\, n$ |

Каждый элемент $G$ удовлетворяет $\widehat{\mathrm{Inv}}(q) = 1$: все $R = 3$ аннотатора независимо поставили $z_r(q) = 1$ после проверки правил исключения $E_1$–$E_5$, либо элемент включён решением адъюдикатора (`provenance.adjudicated = true`). Требования к объёму и покрытию (постановка задачи, раздел «Ограничения»): $n \ge 150$ (цель 200–300); не менее 3 доменов и 2 регионов; охват по датам публикации не менее 12 месяцев; разбиение `dev` (около 30 элементов) / `test`. Каждый $S^*_i$ присутствует в снимке $D_{t_0}$ и в индексе Qdrant, поэтому покрытие корпусом равно 1 по построению.

## Версии

| Версия | Каталог | Срок | Содержание |
|---|---|---|---|
| `v0.1-pilot` | [`v0.1-pilot/`](v0.1-pilot/) | октябрь 2026 | 30 элементов пилота; служит для расчёта согласия и правки инструкции, в эксперименте не используется |
| `v1.0` | [`v1.0/`](v1.0/) | декабрь 2026 | Замороженная выборка для всех прогонов и таблиц работы |

В каталоге каждой версии: `golden_set.jsonl` (одна запись на строку по `schema.json`), `SHA256SUMS`, `agreement.json` (меры согласия аннотаторов), `stats.md` (распределение по доменам, категориям, типам, сложности). После заморозки записи не изменяются; исправления ошибок выходят как `v1.1`, `v1.2` и т. д. с перечислением затронутых `id` в `CHANGELOG.md`. Идентификаторы `id` стабильны и не переиспользуются.

## Лицензия

Разметка (формулировки вопросов, канонические ответы и алиасы, метки, метаданные, evidence span как короткие цитаты) распространяется по лицензии [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). Код репозитория — по лицензии MIT (см. [`LICENSE`](../../LICENSE) в корне). При использовании выборки просьба ссылаться на работу (BibTeX — в корневом `README.md`).

## Что не публикуется

- **Полные тексты статей** (оригинал и перевод): авторские права принадлежат издателям. Публикуются только идентификаторы `webpage_id` и `urn_uuid`, URL, дата публикации, домен и короткие evidence span (не более 300 символов, в объёме цитирования).
- **Соответствие идентификаторов аннотаторов реальным лицам.**
- **Черновики, отклонённые аннотаторами**, и промежуточные разметки: в `CHANGELOG.md` публикуются только агрегаты (сколько исключено по каждому правилу, доля адъюдицированных).

## Поля записи

Полное описание типов, перечислений и условий — в [`schema.json`](schema.json) (JSON Schema draft 2020-12). Сводка:

| Поле | Тип | Смысл |
|---|---|---|
| `id` | `gs-NNNN` | Стабильный идентификатор элемента |
| `version` | строка | Версия выборки, в которой запись зафиксирована |
| `split` | `dev` / `test` | Разбиение |
| `question.{ru,zh,en}` | строки | Вопрос $q_i$; `ru` обязателен и подаётся системам |
| `question_type` | перечисление | Форма вопроса: `who`, `what`, `when`, `where`, `how_many`, `which`, `yes_no`, `list` |
| `category` | перечисление | Тематика факта |
| `answerable` | логическое | `true` — $G^+$, `false` — $G^{\varnothing}$ |
| `answer.{canonical,aliases,type,lang}` | объект или `null` | $A^*_i$: канонический ответ и алиасы; `null` для $G^{\varnothing}$ |
| `supporting_docs[]` | массив | $S^*_i$: `webpage_id`, `urn_uuid`, `uri`, `published_at`, `source`, `evidence_span_ru`, `evidence_span_zh`; пуст для $G^{\varnothing}$ |
| `requires_multi_doc` | логическое | Ответ требует не менее двух документов |
| `time_invariance.{label,anchor_date,votes,exclusion_rules_checked}` | объект | Метка инвариантности, дата-якорь, голоса $z_r$, проверенные правила $E_1$–$E_5$ |
| `difficulty` | `easy` / `medium` / `hard` | Сложность |
| `provenance.{draft_model,draft_prompt_id,seed_pool_ref,annotators,adjudicated,adjudication_note,created_at,unanswerable_check}` | объект | Происхождение записи; `unanswerable_check` обязательно для $G^{\varnothing}$ |

Условия схемы: при `answerable = false` поле `answer` равно `null`, `supporting_docs` пуст и обязателен `provenance.unanswerable_check`; при `requires_multi_doc = true` в `supporting_docs` не менее двух документов; при `adjudicated = false` все голоса `votes` равны 1, при `adjudicated = true` обязательна `adjudication_note`.

## Пример записи $G^+$

Иллюстративная запись (идентификаторы документа, URL и значения `provenance` условные; фактические значения появятся в `v1.0`):

```json
{"id": "gs-0001", "version": "v1.0", "split": "test", "question": {"ru": "Какой орган власти в Китае одобрил увеличение лимита выпуска облигаций местными органами власти в ноябре 2024 года?", "zh": "2024年11月，中国哪个机构批准提高地方政府债务限额？", "en": "Which authority in China approved the increase of the local government bond issuance limit in November 2024?"}, "question_type": "who", "category": "economy", "answerable": true, "answer": {"canonical": "Постоянный комитет Всекитайского собрания народных представителей", "aliases": ["Постоянный комитет ВСНП", "ПК ВСНП", "全国人民代表大会常务委员会", "全国人大常委会", "Standing Committee of the National People's Congress", "NPC Standing Committee"], "type": "organization", "lang": "ru"}, "supporting_docs": [{"webpage_id": 1234567, "urn_uuid": "0f8fad5b-d9cb-469f-a165-70867728950e", "uri": "https://example.com/news/2024-11-08/local-government-debt-limit", "published_at": "2024-11-08", "source": "example.com", "evidence_span_ru": "Постоянный комитет Всекитайского собрания народных представителей одобрил увеличение лимита долга местных органов власти.", "evidence_span_zh": "全国人民代表大会常务委员会批准增加地方政府债务限额。"}], "requires_multi_doc": false, "time_invariance": {"label": "never_changing", "anchor_date": "2024-11", "votes": [1, 1, 1], "exclusion_rules_checked": ["E1", "E2", "E3", "E4", "E5"]}, "difficulty": "easy", "provenance": {"draft_model": "Qwen3-235B-A22B-Instruct", "draft_prompt_id": "draft-v0.1", "seed_pool_ref": null, "annotators": ["A1", "A2", "A3"], "adjudicated": false, "adjudication_note": null, "created_at": "2026-11-15T10:00:00Z"}}
```

## Пример записи $G^{\varnothing}$

Вопрос инвариантен по форме, содержит дату-якорь и корректную предпосылку, но корпус не содержит ответа; правильный ответ системы — отказ:

```json
{"id": "gs-0187", "version": "v1.0", "split": "test", "question": {"ru": "Сколько членов Постоянного комитета ВСНП проголосовали против решения об увеличении лимита облигаций местных органов власти 8 ноября 2024 года?", "zh": null, "en": null}, "question_type": "how_many", "category": "economy", "answerable": false, "answer": null, "supporting_docs": [], "requires_multi_doc": false, "time_invariance": {"label": "never_changing", "anchor_date": "2024-11-08", "votes": [1, 1, 1], "exclusion_rules_checked": ["E1", "E2", "E3", "E4", "E5"]}, "difficulty": "medium", "provenance": {"draft_model": "Qwen3-235B-A22B-Instruct", "draft_prompt_id": "draft-v0.1", "seed_pool_ref": null, "annotators": ["A1", "A2", "A3"], "adjudicated": false, "adjudication_note": null, "created_at": "2026-11-20T14:30:00Z", "unanswerable_check": {"method": "retrieval_topk_and_manual", "retriever": "prod_qdrant", "k": 20, "queries": ["Сколько членов ПК ВСНП проголосовали против увеличения лимита облигаций 8 ноября 2024 года?", "ВСНП голосование лимит долга местных органов власти ноябрь 2024 против"], "answerable_votes": [0, 0, 0], "checked_at": "2026-11-20"}}}
```

## Проверка целостности версии `v1.0`

Заморозка версии фиксируется контрольной суммой файла `golden_set.jsonl` и тегом git `golden-set-v1.0`. Ожидаемое значение SHA-256 для `v1.0`: **заполняется при заморозке** (декабрь 2026); оно же публикуется в `CHANGELOG.md` и в файле `v1.0/SHA256SUMS`.

```bash
# из корня репозитория
shasum -a 256 data/golden_set/v1.0/golden_set.jsonl
# сравнить с ожидаемым значением из CHANGELOG.md или проверить весь каталог:
cd data/golden_set/v1.0 && shasum -a 256 -c SHA256SUMS
```

Проверка структуры записей по схеме (требуется пакет `jsonschema`):

```bash
python3 -c "
import json, sys
from jsonschema import Draft202012Validator, FormatChecker
schema = json.load(open('data/golden_set/schema.json'))
v = Draft202012Validator(schema, format_checker=FormatChecker())
bad = 0
for n, line in enumerate(open('data/golden_set/v1.0/golden_set.jsonl', encoding='utf-8'), 1):
    for e in v.iter_errors(json.loads(line)):
        bad += 1; print(f'line {n}: {e.json_path}: {e.message}')
sys.exit(1 if bad else 0)
"
```
