# Код

Программный каркас ВКР «Система оценки качества ответов больших языковых моделей по новостным
текстам стран Восточной Азии». Здесь живут три пакета: построение эталонной выборки
$`G = G^+ \sqcup G^{\varnothing}`$, обёртки оцениваемых систем $`\mathcal{H}_{\mathrm{eval}}`$
и семейство метрик $`M`$ с валидацией, статистикой и отчётными таблицами. Обозначения совпадают
с постановкой задачи в `README.md` репозитория и `docs/problem_statement.md`.

> [!IMPORTANT]
> Jupyter-ноутбуки используются **только для визуализации** (`code/notebooks/`). Вся логика —
> в Python-модулях `.py`, вызываемых через `Makefile`.

**Статус: каркас.** Содержательные функции содержат докстринги с формулами и правилами NA
и завершаются `NotImplementedError`; реализованы только служебные элементы (типы данных,
константы, разбор аргументов, чтение конфигураций). Реализация метрик и конвейера — содержание
работы (график — в `docs/problem_statement.md`). Модули импортируются и проходят
`python -m py_compile` без установленных зависимостей: третьесторонние пакеты импортируются лениво.

## Установка

```bash
git clone https://github.com/Priestprog/east-asia-news-llm-eval.git
cd east-asia-news-llm-eval/code
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Требуется Python 3.10 или новее. Каталог `.venv` игнорируется git.

## Переменные окружения

Секреты и адреса сервисов задаются в файле `.env` в корне репозитория (игнорируется git;
читается `python-dotenv`). В YAML-конфигурациях на них ссылаются как `${ИМЯ}`.

| Переменная | Назначение |
|---|---|
| `IVRAN_LLM_BASE_URL` | OpenAI-совместимый адрес провайдера ИВ РАН (llama-swap) для открытых моделей $`\mathcal{L}`$ и судьи |
| `IVRAN_LLM_API_KEY` | ключ провайдера |
| `IVRAN_LLM_MODEL` | модель генератора промышленной системы (ожидаемая; фактическая берётся из поля `model` ответа) |
| `JUDGE_LLM_MODEL` | модель-судья; должна быть вне $`\mathcal{L}`$ и не совпадать с генератором прода |
| `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION` | векторная база корпуса (23,9 млн чанков) — для пересечения с `webmedia` и снимка $`\mathcal{I}`$ |
| `WEBMEDIA_POSTGRES_HOST`, `WEBMEDIA_POSTGRES_PORT` | PostgreSQL с таблицей `webmedia.webpages` (метаданные документов, `webpage_id`, `urn_uuid`, `uri`) |
| `WEBMEDIA_CC_NEWS_USER`, `WEBMEDIA_CC_NEWS_USER_PASSWORD`, `WEBMEDIA_CC_NEWS_DB_NAME` | учётные данные и имя базы `webmedia` |
| `PROD_API_BASE_URL` | HTTP API промышленной системы «Chinese Media Analysis» ($`f_{\mathrm{prod}}`$) |

Пример `.env` (значения условные):

```dotenv
IVRAN_LLM_BASE_URL=http://llm.example.local/v1
IVRAN_LLM_API_KEY=...
IVRAN_LLM_MODEL=DeepSeek-R1-Distill-Qwen-32B-Q5_K_M
JUDGE_LLM_MODEL=...
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=cc_news
WEBMEDIA_POSTGRES_HOST=localhost
WEBMEDIA_POSTGRES_PORT=5432
WEBMEDIA_CC_NEWS_USER=...
WEBMEDIA_CC_NEWS_USER_PASSWORD=...
WEBMEDIA_CC_NEWS_DB_NAME=webmedia
PROD_API_BASE_URL=http://localhost:10090
```

Файл `.env` не коммитится (`*.env`, `secret.env` в `.gitignore`).

## Структура

```
code/
├── __init__.py                  # load_config(): YAML + подстановка ${VAR}
├── configs/
│   ├── eval.yaml                # пути, первичная метрика, B, α, Холм, ρ_min, α_min, seed, split, список M
│   ├── judge.yaml               # судья: модель (∉ L), temperature 0, рубрика из 8 измерений
│   └── systems/
│       ├── prod.yaml            # f_prod: prod_api, qdrant+searchapi, k=5, m=3, threshold=0.3
│       ├── open_closed_book.yaml    # f_0^{(m)}: openai_compat, retriever none
│       └── open_with_retrieval.yaml # f_ρ^{(m)}: openai_compat, retriever cached_prod
├── annotation/                  # построение G
│   ├── sample_documents.py      # стратифицированный отбор webmedia ∩ Qdrant, снимок D_{t0}
│   ├── generate_drafts.py       # черновики (q, a, S, evidence, тип, дата) моделью g_draft ∉ L; seed pool
│   ├── export_sheets.py         # листы для R=3 разметчиков и для человеческой валидации h
│   ├── agreement.py             # krippendorff_alpha, fleiss_kappa, pairwise_answer_f1
│   ├── adjudicate.py            # расхождения → четвёртый эксперт
│   └── build_golden_set.py      # JSONL по schema.json, split dev/test, sha256
├── systems/                     # H_eval
│   ├── base.py                  # System.answer(question) -> SystemOutput(answer, cited_ids, raw, model_reported)
│   ├── prod_api.py              # f_prod через HTTP API прода; разбор (N) и source_map
│   ├── openai_compat.py         # f_0^{(m)} и f_ρ^{(m)} через OpenAI-совместимый API
│   └── retriever_cache.py       # кэш выдачи ρ_prod для абляции «модель против ретривера»
├── eval/                        # M, судья, валидация, статистика, таблицы
│   ├── metrics_reference.py     # exact_match, token_f1, bertscore_f1, cosine_similarity
│   ├── metrics_citation.py      # citation_precision_id, citation_recall_id, citation_precision_entailment
│   ├── metrics_abstention.py    # abstention_rate, false_abstention_rate
│   ├── metrics_retrieval.py     # hit_at_k, recall_at_k, mrr, ndcg_at_k
│   ├── judge.py                 # Judge, JudgeVerdict, RUBRIC_DIMENSIONS (8)
│   ├── validate_metrics.py      # spearman_with_ci, select_validated_metrics → M'
│   ├── stats.py                 # paired_bootstrap_ci, wilcoxon_signed_rank, holm_correction, cliffs_delta, Q(f)
│   ├── run_generation.py        # прогон системы → results/runs/<run_id>/generations.jsonl + meta.json
│   ├── run_judge.py             # оценка судьёй → judge.jsonl
│   └── make_tables.py           # main_table.md, main_table_long.csv
├── notebooks/                   # только визуализация
└── requirements.txt
```

Соглашение о NA: значение `None` обозначает $`\mathrm{NA}`$ — метрика не определена для данной пары
(ответ, эталон); правило NA каждой метрики записано в её докстринге. Агрегация
$`\bar m_k(f)`$ идёт по $`I_k(f) = \{i : m_k \ne \mathrm{NA}\}`$.

## Запуск

Модули запускаются **из корня репозитория** как `python -m code.<пакет>.<модуль>` (имя пакета
`code` совпадает с модулем стандартной библиотеки; при запуске из корня локальный пакет имеет
приоритет). Удобнее — через `Makefile` в корне (`PYTHON` можно переопределить):

| Цель | Что делает |
|---|---|
| `make drafts` | отбор документов, черновики моделью $`g_{\mathrm{draft}}`$, листы разметки |
| `make agreement` | Krippendorff $`\alpha`$, Fleiss $`\kappa`$, попарный F1 ответов разметчиков |
| `make build-gs` | адъюдикация и сборка Golden Set версии `GS_VERSION` (JSONL, sha256) |
| `make run SYSTEM=code/configs/systems/prod.yaml` | генерации системы на split из `eval.yaml` |
| `make judge RUN_ID=<run_id>` | оценка генераций судьёй |
| `make validate` | отбор $`M'`$ по согласию с разметчиками → `results/tables/validation.csv` |
| `make stats` | парный бутстреп, Уилкоксон, Холм, Cliff's $`\delta`$ относительно $`f_{\mathrm{prod}}`$ |
| `make tables` | `results/tables/main_table.md`, `main_table_long.csv` |
| `make check` | `py_compile` всех модулей, импорт пакетов, валидация JSON и YAML |

Пример с виртуальным окружением из `code/.venv`:

```bash
make check PYTHON=code/.venv/bin/python
```

Порядок для полного эксперимента: `drafts → agreement → build-gs → run` (сначала `prod.yaml`,
он заполняет кэш ретривера; затем `open_*.yaml` для каждой $`m \in \mathcal{L}`$) `→ judge → validate → stats → tables`.
