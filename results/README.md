# Результаты

Каталог артефактов экспериментов. Сырые прогоны не коммитятся (`results/runs/` в `.gitignore`),
таблицы и рисунки — коммитятся.

## `results/runs/<run_id>/` (не в git)

Один каталог на прогон одной системы $`f \in \mathcal{H}_{\mathrm{eval}}`$. `run_id` —
`<дата>-<время>-<имя конфигурации системы>`, например `20270115-093000-prod`.

| Файл | Содержимое |
|---|---|
| `generations.jsonl` | по строке на вопрос: `question_id, system_id, answer` (`null` — отказ), `cited_ids` ($`\hat S`$, `webpage_id`), `retrieved_ids` (ранжированная выдача $`\rho_{\mathrm{prod}}`$), `model_reported` (поле `model` ответа провайдера), `latency_s, raw, created_at` |
| `judge.jsonl` | по строке на вопрос: `question_id, system_id, scores{<измерение>: 0..5 | null}, rationales, extra, judge_model_reported, judge_prompt_version, raw` |
| `meta.json` | паспорт прогона: `run_id`; `system` — паспорт системы (`system_id, kind, retriever, model_id, quantization, k, m, threshold, temperature, seed, prompt_version`); `git_sha` репозитория; `models_snapshot` — ответ `/v1/models` провайдера до прогона; `golden_set` — путь, версия, sha256, split, $`n`$; `date`; `packages` — версии ключевых пакетов; `status` (`completed` / `aborted`); блок `judge` после `make judge` |

`results/runs/_retriever_cache/prod.jsonl` — кэш выдачи $`\rho_{\mathrm{prod}}`$, заполняемый прогоном
$`f_{\mathrm{prod}}`$ и читаемый системами $`f_\rho^{(\ell)}`$ (тоже не в git).

Сырые генерации публикуются отдельно как приложение к работе (архив с указанием `git_sha`
и sha256 Golden Set); полные тексты документов корпуса не публикуются.

## `results/tables/`

| Файл | Содержимое |
|---|---|
| `main_table.md` | широкая таблица: строки — системы, столбцы — метрики $`m_k \in M'`$ в виде `mean [lo; hi]`, звёздочка при $`p_{\mathrm{Holm}} < 0.05`$ относительно $`f_{\mathrm{prod}}`$, последние столбцы — $`Q(f)`$ и ранг; подпись — split, $`n`$, $`B`$, дата, `git_sha` |
| `main_table_long.csv` | длинный формат, по строке на (система, метрика); столбцы — ниже |
| `validation.csv` | валидация метрик: `metric, rho_spearman, ci_low, ci_high, n_pairs, passed` (порог $`r_{\min} = 0.5`$), потолок — среднее попарное согласие людей, $`\alpha`$ Криппендорфа аннотаторов, решение о первичной метрике |
| `stats.csv` | парные сравнения с $`f_{\mathrm{prod}}`$ по первичной метрике: $`\bar\delta`$ с бутстреп-интервалом, $`p`$ Уилкоксона, $`\tilde p`$ Холма, $`\Delta_{\mathrm{C}}`$ Клиффа |

Столбцы `main_table_long.csv` (схема из постановки задачи):

```
system_id, model_id_reported, quantization, retriever, k, prompt_version, temperature, n_samples,
metric, n, mean, ci_low, ci_high, delta_vs_prod, p_wilcoxon, p_holm, run_id, git_sha, date
```

- `n` — $`|I_k(f)|`$, число вопросов, на которых метрика не равна NA;
- `mean` — $`\bar m_k(f)`$; `ci_low`, `ci_high` — перцентильный 95%-й бутстреп-интервал ($`B = 10^4`$);
- `delta_vs_prod` — $`\bar m_k(f) - \bar m_k(f_{\mathrm{prod}})`$ на общих вопросах; для $`f_{\mathrm{prod}}`$ пусто;
- `p_wilcoxon`, `p_holm` — критерий Уилкоксона знаковых рангов и поправка Холма по всем $`f' \ne f_{\mathrm{prod}}`$;
- `model_id_reported` — фактическая модель по полю `model` ответов (не запрошенная).

## `results/audit/`

Базовый эксперимент: аудит существующих наборов вопросов (ADR-020). Таблицы строят модули
`code/audit/compute_*.py` (`python -m code.audit --stage compute`) по сторонним данным, которые
скачиваются в `data/external/` и в репозиторий не входят. Во всех таблицах `n` — число вопросов,
`count` — число вопросов со свойством, `rate` — их доля, `ci_low`, `ci_high` — 95%-й перцентильный
бутстреп-интервал по вопросам ($`B = 10^4`$, seed из `eval.yaml`).

| Файл | Содержимое |
|---|---|
| `freshqa_staleness.csv` | доля изменившихся эталонных ответов FreshQA относительно версии от 15.10.2023 по 74 поздним версиям: `base_version, version, months, fact_type, definition, n, count, rate, ci_low, ci_high, quarterly`; `definition = any` — изменилось множество ответов с алиасами, `main` — канонический ответ; `quarterly` — последняя версия квартала (первый прогон) |
| `freshqa_never_changed.csv` | 12 неизменных по разметке вопросов, эталон которых изменился к последней версии: ответы и алиасы до и после |
| `datasets_measures.csv` | дефекты FreshQA, RGB, CDQA, ChronoQA, DRAGOn: `dataset, subset, measure, label` и доля с интервалом; определения величин — в докстринге `compute_datasets.py` |
| `seed_pool_markers.csv` | доли 388 вопросов промышленной системы, отмеченных эвристиками правил $`E_1`$, $`E_2`$, $`E_4`$ и маркерами формулировки (`markers.py`) |
| `seed_pool_flagged.csv` | отмеченные вопросы с перечнем сработавших правил, доменом и `warc_id` — для ручной проверки эвристик |
| `datasets_summary.csv`, `datasets_summary.md` | сводная таблица девяти наборов «почему не подходят»: язык, эталон, опорные документы, отказы, согласие, время, версии, измеренный дефект |
| `sources.csv` | использованные файлы: набор, версия (дата, коммит или тег), путь в кэше, адрес, sha256, число записей |

## `results/figures/`

Рисунки для текста и слайдов (PNG/PDF). Рисунки основного эксперимента строятся ноутбуками из
`code/notebooks/` по данным `results/tables/`, имя файла совпадает с именем ноутбука. Рисунки
аудита строит `code/audit/plots.py` только по таблицам `results/audit/`
(`python -m code.audit --stage plots`): `freshqa_staleness_sketch` — эскиз графика ошибок первого
прогона по квартальным версиям, `main_message` — главный вывод по всем версиям FreshQA.
