# Система оценки качества ответов больших языковых моделей по новостным текстам стран Восточной Азии

*A System for Evaluating the Quality of Large Language Model Answers on East Asian News Texts*

[![License](https://badgen.net/github/license/Priestprog/east-asia-news-llm-eval?color=green)](https://github.com/Priestprog/east-asia-news-llm-eval/blob/main/LICENSE)
[![GitHub Contributors](https://img.shields.io/github/contributors/Priestprog/east-asia-news-llm-eval)](https://github.com/Priestprog/east-asia-news-llm-eval/graphs/contributors)
[![GitHub Issues](https://img.shields.io/github/issues-closed/Priestprog/east-asia-news-llm-eval.svg?color=0088ff)](https://github.com/Priestprog/east-asia-news-llm-eval/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr-closed/Priestprog/east-asia-news-llm-eval.svg?color=7f29d6)](https://github.com/Priestprog/east-asia-news-llm-eval/pulls)

<table>
    <tr>
        <td align="left"> <b> Author </b> </td>
        <td> Багров Александр Михайлович, факультет вычислительной математики и кибернетики МГУ имени М. В. Ломоносова (<a href="https://github.com/Priestprog">Priestprog</a>) </td>
    </tr>
    <tr>
        <td align="left"> <b> Advisor </b> </td>
        <td> Воронцов Константин Вячеславович, д.ф.-м.н. </td>
    </tr>
    <tr>
        <td align="left"> <b> Consultant </b> </td>
        <td> Воронцов Константин Вячеславович, д.ф.-м.н. </td>
    </tr>
    <tr>
        <td align="left"> <b> Institution </b> </td>
        <td> Московский государственный университет имени М. В. Ломоносова, факультет вычислительной математики и кибернетики (Lomonosov Moscow State University, Faculty of Computational Mathematics and Cybernetics) </td>
    </tr>
    <tr>
        <td align="left"> <b> Defense </b> </td>
        <td> июнь 2027 </td>
    </tr>
</table>


## Аннотация / Abstract

Промышленные вопросно-ответные системы на основе больших языковых моделей (LLM) с дополнением поиском (retrieval-augmented generation, RAG) над новостными корпусами внедряются быстрее, чем появляются средства количественной оценки их ответов: имеющиеся бенчмарки либо построены на англоязычных данных, либо содержат вопросы с меняющимся во времени ответом, и полученные на них результаты устаревают вместе с новостной повесткой. Объект исследования — ответ $`\hat a=f(q)`$ вопросно-ответной системы на вопрос $`q`$ о новостном корпусе стран Восточной Азии; материалом служит промышленная система «Chinese Media Analysis» (ИВ РАН) над корпусом китайскоязычных СМИ КНР, Тайваня, Гонконга и Сингапура (23,9 млн фрагментов). В работе строится система оценки качества ответов: (1) семейство метрик $`M`$ — по эталону, цитирования, отказов и поиска, включая судью на основе языковой модели; (2) эталонная выборка $`G`$ статических вопросов, ответ на которые инвариантен во времени, с протоколом независимой разметки $`R=3`$ аннотаторами и мерой согласия (Krippendorff $`\alpha`$); (3) валидация метрик по корреляции с человеческими оценками и отбор подсемейства $`M'`$; (4) применение $`M'`$ к промышленной системе $`f_{\text{prod}}`$ и открытым моделям с поиском и без него с проверкой значимости парных различий. Корпус на данном этапе китайскоязычный; расширение на японские и корейские источники — предмет дальнейшей работы.

Industrial question-answering systems built on large language models (LLM) with retrieval-augmented generation (RAG) over news corpora are deployed faster than tools for the quantitative assessment of their answers appear: existing benchmarks are either English-centric or consist of questions whose answers change over time, so results obtained on them become obsolete together with the news agenda. The object of study is the answer $`\hat a=f(q)`$ produced by a question-answering system to a question $`q`$ about an East Asian news corpus; the material is the industrial system "Chinese Media Analysis" (Institute of Oriental Studies, Russian Academy of Sciences) over a corpus of Chinese-language media from the PRC, Taiwan, Hong Kong and Singapore (23.9 million chunks). The thesis builds an answer-quality evaluation system: (1) a family of metrics $`M`$ — reference-based, citation, abstention and retrieval metrics, including a language-model judge; (2) a golden set $`G`$ of static questions whose answers are time-invariant, with an independent annotation protocol ($`R=3`$ annotators) and an inter-annotator agreement measure (Krippendorff's $`\alpha`$); (3) validation of the metrics by correlation with human judgements and selection of the subfamily $`M'`$; (4) application of $`M'`$ to the industrial system $`f_{\text{prod}}`$ and to open models with and without retrieval, with significance testing of paired differences. At this stage the corpus is Chinese-language only; extension to Japanese and Korean sources is future work.

## Общее описание задачи

Мы решаем проблему отсутствия количественной и воспроизводимой оценки качества ответов вопросно-ответных систем на основе больших языковых моделей над новостным корпусом стран Восточной Азии. Она важна, потому что такие системы уже используются востоковедами и аналитиками для работы с китайскоязычными СМИ, а единственным свидетельством их качества остаются качественные наблюдения и отдельные примеры. Известные дефекты: ложная атрибуция фактов источнику другого года, номера цитат вне списка источников, нерелевантные фрагменты с высокой косинусной близостью, непереведённые китаизмы, неоправданные отказы не измеряются, а значит, не могут быть ни отслежены при смене модели-генератора, ни сопоставлены между системами. Без системы оценки утверждение «система работает хорошо» остаётся недоказуемым.

Ключевое ограничение постановки — статические вопросы. Новостной корпус — движущаяся мишень: если ответ на вопрос меняется со временем (курс валюты, действующее должностное лицо, «текущая ситуация»), эталон устаревает через месяцы, и расхождение ответа системы с эталоном невозможно отличить от устаревания самого эталона. Ограничение предикатом $`\mathrm{Inv}(q)`$ — ответ полностью определяется зафиксированным снимком корпуса и не изменяется при $`t\ge t_0`$ — делает выборку долговечной, а расхождение — интерпретируемым как ошибка системы. Кроме того, только на статических вопросах корректно сравнение системы с поиском и модели без поиска: если открытая модель отвечает верно без доступа к корпусу, это утечка знаний из предобучения, которую можно измерить напрямую, а не списать на изменившийся мир.

Существующие бенчмарки не закрывают эту нишу. RGB (Chen et al., 2023) оценивает четыре способности моделей на новостных вопросах на китайском и английском, но не привязан к конкретному корпусу и не содержит эталонных опорных документов; CRUD-RAG (Lyu et al., 2024) построен на китайских новостях, но проверяет сценарии создания, чтения, обновления и удаления знаний, а не правильность и обоснованность ответа с цитированием; CDQA (Xu et al., 2024) и ближайший конкурент ChronoQA (2025; 5176 вопросов по 300 тыс. китайских новостей) намеренно состоят из динамических, времязависимых вопросов — противоположная постановка. Ни один из них не оценивает промышленную систему над заданным корпусом с ответами на русском языке, не включает вопросов, правильный ответ на которые — отказ, и не сообщает меру согласия аннотаторов. В России публичных работ по оценке систем с дополнением поиском над китайскоязычными новостями с эталонной выборкой, несколькими разметчиками и сравнением промышленной системы с открытыми моделями не найдено; русскоязычные бенчмарки MERA, ruMTEB и RusBEIR покрывают общие задачи и поиск, но не вопросно-ответные системы над иноязычным новостным корпусом.

## Формальная постановка задачи

Полная версия с протоколом разметки и обсуждением решений — в [docs/problem_statement.md](docs/problem_statement.md); правила разметки — в [docs/annotation_guidelines.md](docs/annotation_guidelines.md).

### Дано

1. Момент фиксации $`t_0`$ и корпус $`D=\{d_j\}_{j=1}^N`$, где $`d_j=(\iota_j,u_j,\tau_j,s_j,x_j^{zh},x_j^{ru})`$ — стабильный идентификатор документа (`webpage_id`/`urn_uuid`), URL, дата публикации $`\tau_j\le t_0`$, источник, текст оригинала и его перевод. Множество идентификаторов обозначается $`\mathcal{I}`$. Разбиение на чанки — деталь ретривера; единственное требование — каждый чанк отображается в идентификатор $`\iota_j\in\mathcal{I}`$.

2. Пространства: вопросы $`\mathcal{Q}`$ (на русском языке); ответы $`\mathcal{A}=\mathcal{A}^+\sqcup\{\varnothing\}`$, где $`\varnothing`$ — отказ («Я не знаю.»); цитирования $`2^{\mathcal{I}}`$ — подмножества идентификаторов документов.

3. Инвариантность во времени. Пусть $`a^*(q,t)`$ — истинный ответ на вопрос $`q`$ при состоянии мира в момент $`t`$. Вопрос статический, если

   $`\displaystyle \mathrm{Inv}(q)\iff\exists\,a^*(q)\in\mathcal{A}^+:\ \forall t\ge t_0\quad a^*(q,t)=a^*(q).`$

   Операционализация: ответ полностью определяется корпусом, $`a^*(q)=g(q,D)`$; существует непустое $`S^*_q\subset\mathcal{I}`$, документы которого влекут $`a^*(q)`$; вопрос содержит явную дату-якорь. Оценка предиката по меткам $`R`$ аннотаторов: $`\widehat{\mathrm{Inv}}(q)=\mathbb{1}\left[\sum_{r=1}^R z_r(q)=R\right]`$, где $`z_r(q)\in\{0,1\}`$ — метка $`r`$-го аннотатора после применения правил исключения: $`E_1`$ — прогнозы и гипотетика; $`E_2`$ — маркеры «сейчас», «на данный момент», «последний», «текущая ситуация»; $`E_3`$ — величины без даты-якоря (цены, курсы, индексы, действующие должностные лица); $`E_4`$ — ответ зависит от момента запроса или политической оценки; $`E_5`$ — ложная предпосылка. В терминах таксономии FreshQA допускаются never-changing вопросы; slow-changing — только с датой-якорем; fast-changing и false-premise исключаются.

4. Эталонная выборка $`G=G^+\sqcup G^{\varnothing}`$. Здесь $`G^+=\{(q_i,A^*_i,S^*_i,\mu_i)\}_{i=1}^{n_+}`$ — вопросы с подтверждаемым ответом: $`A^*_i`$ — канонический ответ и множество алиасов/транслитераций; $`S^*_i\subset\mathcal{I}`$, $`|S^*_i|\ge1`$ — опорные документы; $`\mu_i`$ — метаданные (тип вопроса, категория, источник, дата-якорь, голоса аннотаторов, сложность, split). $`G^{\varnothing}`$ — вопросы, инвариантные по форме, но не подтверждаемые корпусом (правильный ответ — отказ $`\varnothing`$); $`n_\varnothing\approx0.1\,n`$, $`n=n_++n_\varnothing`$.

5. Класс гипотез $`\mathcal{H}=\{f:\mathcal{Q}\to\mathcal{A}\times2^{\mathcal{I}}\}`$, $`f(q)=(\hat a,\hat S)`$ — ответ и множество процитированных документов. Оцениваемое подмножество

   $`\displaystyle \mathcal{H}_{\text{eval}}=\{f_{\text{prod}}\}\cup\{f_0^{(m)}\}_{m\in\mathcal{L}}\cup\{f_\rho^{(m)}\}_{m\in\mathcal{L}},`$

   где $`f_{\text{prod}}=g_{\theta_{\text{prod}}}\circ\rho_{\text{prod}}`$ — промышленная система (ретривер Qdrant + SearchAPI и генератор); $`f_0^{(m)}=(g_m(q),\varnothing)`$ — открытая модель $`m`$ без поиска («закрытая книга»); $`f_\rho^{(m)}=g_m\circ\rho_{\text{prod}}`$ — та же выдача промышленного ретривера с другой моделью-генератором (абляция «модель против ретривера»; контексты $`\rho_{\text{prod}}(q)`$ кэшируются и общие для всех $`m`$). $`\mathcal{L}`$ — список открытых моделей провайдера ИВ РАН (раздел «Оцениваемые системы»).

6. Семейство метрик $`M=\{m_k\}`$, $`m_k:\mathcal{A}\times2^{\mathcal{I}}\times G_i\to[0,1]\cup\{\mathrm{NA}\}`$, ориентация «больше — лучше»:
   - по эталону (на $`G^+`$): $`\mathrm{EM}=\max_{a\in A^*_i}\mathbb{1}[\mathrm{norm}(\hat a)=\mathrm{norm}(a)]`$; токенный F1 после лемматизации, максимум по алиасам; BERTScore-F1 (мультиязычный энкодер); $`m_J^{\text{corr}}`$ — судья-LLM «правильность относительно $`A^*_i`$», шкала 0–5, делённая на 5 (новое измерение, у существующей рубрики его нет); $`m_J^{(d)}`$, $`d\in`$ {faithfulness, answer_relevancy, completeness, citation_accuracy, temporal_correctness, allegory_idiom_quality, hallucination_abstention} — существующая рубрика как кандидатное подсемейство;
   - цитирование: $`\mathrm{CP}_{\text{id}}=|\hat S\cap S^*_i|/|\hat S|`$ ($`\mathrm{NA}`$ при $`\hat S=\varnothing`$); $`\mathrm{CR}_{\text{id}}=|\hat S\cap S^*_i|/|S^*_i|`$ (для закрытой книги равна 0); $`\mathrm{CP}_{\text{ent}}=\frac{1}{|\hat S|}\sum_{\iota\in\hat S}\mathbb{1}[x_\iota\models\hat a]`$ через NLI или судью (по ALCE; нужна, потому что $`S^*_i`$ может быть неполным в корпусе из 23,9 млн чанков);
   - отказы: $`\mathrm{AR}=\frac{1}{n_\varnothing}\sum_{G^{\varnothing}}\mathbb{1}[\hat a=\varnothing]`$; $`1-\mathrm{FAR}`$, где $`\mathrm{FAR}=\frac{1}{n_+}\sum_{G^+}\mathbb{1}[\hat a=\varnothing]`$;
   - поиск (компонент $`\rho`$): Hit@k, Recall@k, MRR, nDCG@k относительно $`S^*_i`$.

7. Человеческие оценки $`h^{(r)}_{i,f}\in\{0,\dots,5\}`$ (правильность, обоснованность) $`r`$-го аннотатора для ответа системы $`f`$ на вопрос $`q_i`$ на подвыборке $`G_h\subset G^+`$, $`|G_h|=n_h`$ (цель $`n_h=100`$), для подмножества систем $`\mathcal{H}_h\subset\mathcal{H}_{\text{eval}}`$; $`\bar h_{i,f}`$ — среднее по $`r`$.

### Найти

1. Выборку $`G`$, удовлетворяющую ограничениям (ниже).

2. Валидированное подсемейство метрик

   $`\displaystyle M'=\{m_k\in M:\ \rho_S(m_k,\bar h)\ge\rho_{\min}\ \text{на}\ G_h\times\mathcal{H}_h\},\qquad \rho_{\min}=0.5,`$

   где $`\rho_S`$ — коэффициент ранговой корреляции Спирмена с 95%-м бутстреп-интервалом; потолок для сравнения — среднее попарное согласие людей между собой. Детерминированные метрики без человеческого аналога (Recall@k и т.п.) включаются в $`M'`$ напрямую.

3. Для каждой $`f\in\mathcal{H}_{\text{eval}}`$ и $`m_k\in M'`$ — средние по вопросам

   $`\displaystyle \bar m_k(f)=\frac{1}{|I_k(f)|}\sum_{i\in I_k(f)}m_k\big(f(q_i);G_i\big),\qquad I_k(f)=\{i:\ m_k(f(q_i);G_i)\ne\mathrm{NA}\};`$

   композитный показатель $`Q(f)=\sum_k w_k\,\bar m_k(f)`$, $`w_k\ge0`$, $`\sum_k w_k=1`$ (по умолчанию веса равные); лучшую систему $`f^\star=\arg\max_{f\in\mathcal{H}_{\text{eval}}}Q(f)`$ с проверкой статистической значимости парных различий.

### Критерий качества и статистика

Первичная метрика фиксируется до эксперимента: $`m_J^{\text{corr}}`$, если она пройдёт валидацию по $`H_4`$, иначе токенный F1; остальные метрики — вторичные. Для пары систем $`(f,f')`$ вычисляются поточечные разности $`\delta_i=m_k(f(q_i))-m_k(f'(q_i))`$ на общих вопросах $`i\in I_k(f)\cap I_k(f')`$; применяется парный бутстреп по вопросам ($`B=10^4`$, перцентильный 95%-й интервал для $`\bar\delta`$); двусторонний критерий Уилкоксона знаковых рангов с поправкой Холма на уровне значимости $`0.05`$ по всем сравнениям $`f'\ne f_{\text{prod}}`$; размер эффекта — Cliff's $`\delta`$. Буква $`\alpha`$ везде обозначает только коэффициент согласия Криппендорфа; уровень значимости записывается числом. Разбивка по стратам (категория, источник, тип вопроса, известность события) приводится описательно, без проверки гипотез. Генерация — temperature 0 и фиксированный seed; для судьи — temperature 0 и отчёт о его собственной воспроизводимости (повторные прогоны на подвыборке).

### Ограничения

- Снимок корпуса $`D_{t_0}`$ зафиксирован: дата, $`N`$, хеш списка $`\mathcal{I}`$. Для каждого $`i`$ выполнено $`S^*_i\subset\mathcal{I}`$, и документы $`S^*_i`$ присутствуют в Qdrant, поэтому покрытие корпуса равно 1 по построению.
- Размер: $`n\ge150`$ (цель 200–300); не менее 3 доменов и 2 регионов; охват по датам публикации не менее 12 месяцев; разбиение dev (30 вопросов) / test.
- Судья $`\notin\mathcal{L}\cup\{g_{\theta_{\text{prod}}}\}`$, либо используется ансамбль двух судей; отдельная проверка самопредпочтения ($`H_5`$).
- Провайдер ИВ РАН (llama-swap): fail-fast при неизвестном идентификаторе модели; для каждого ответа записывается фактическое поле `model` из ответа API и снимок `/v1/models` на момент прогона.
- Публикуются идентификаторы документов, URL, даты и короткие evidence-span, но не полные тексты статей.
- Время: защита в июне 2027. Сентябрь–октябрь 2026 — постановка, инструкция разметки, пилот на 30 вопросах, обзор литературы; ноябрь–декабрь 2026 — разметка 250 вопросов и заморозка `v1.0`; январь 2027 — прогоны; февраль 2027 — валидация и статистика; март–апрель 2027 — текст и слайды.

### Протокол разметки (кратко)

Стратифицированный отбор документов из `webmedia.webpages ∩ Qdrant` (домен × месяц × категория) с переизбытком ×2; черновики $`(q,a,S,\text{evidence},\text{тип},\text{дата})`$ порождает модель $`g_{\text{draft}}\notin\mathcal{L}`$ (388 старых вопросов — seed pool после перекладки `warc_id → webpage_id`); независимая разметка $`R=3`$ аннотаторами (не менее одного, читающего по-китайски); согласие — Krippendorff $`\alpha`$ по инвариантности, отвечаемости и типу ($`\alpha\ge0.67`$ допустимо, $`\alpha\ge0.8`$ надёжно) и попарный F1 по ответам $`\ge0.8`$; включение в $`G`$ при единогласии, иначе адъюдикация четвёртым экспертом; пилот на 30 вопросах → правка инструкции → полный прогон → заморозка `v1.0` (sha256, CHANGELOG). Правила $`E_1`$–$`E_5`$, шкалы и примеры — в [docs/annotation_guidelines.md](docs/annotation_guidelines.md).

### Гипотезы

- $`H_1`$ (основная): $`Q(f_{\text{prod}})>Q(f_0^{(m)})`$ для всех $`m\in\mathcal{L}`$ — промышленная система с поиском превосходит любую открытую модель без поиска.
- $`H_2`$ (сильная): $`Q(f_{\text{prod}})>Q(f_\rho^{(m)})`$ для всех $`m\in\mathcal{L}`$ — при опровержении вклад ретривера и модели-генератора разделяется явно.
- $`H_3`$: $`Q(f_\rho^{(m)})>Q(f_0^{(m)})`$ — поиск помогает при фиксированной модели.
- $`H_4`$: $`\rho_S(m_J^{\text{corr}},\bar h)\ge0.5`$ и $`\alpha_{\text{human}}\ge0.67`$ — судья валиден, а человеческая разметка согласована.
- $`H_5`$: самопредпочтение судьи статистически незначимо.


## Эталонная выборка

Эталонная выборка $`G=G^+\sqcup G^{\varnothing}`$ — главный артефакт данных работы; её описание, схема и история версий лежат в [data/golden_set/README.md](data/golden_set/README.md), [data/golden_set/schema.json](data/golden_set/schema.json) и `data/golden_set/CHANGELOG.md`.

- **Состав.** $`G^+`$ — статические вопросы на русском языке с каноническим ответом, алиасами и не менее одним опорным документом из корпуса; $`G^{\varnothing}`$ — вопросы той же формы, ответ на которые корпусом не подтверждается (правильный ответ — отказ), $`n_\varnothing\approx0.1\,n`$. Требования: не менее 3 доменов, 2 регионов, охват по датам публикации не менее 12 месяцев; стратификация домен × месяц × категория; разбиение dev (30) / test.
- **Размер.** $`n\ge150`$, цель 200–300 вопросов; человеческая валидация метрик — на подвыборке $`G_h`$, $`n_h=100`$.
- **Версии.** `v0.1-pilot` — 30 вопросов (октябрь 2026) для проверки инструкции разметки и оценки согласия; `v1.0` — заморозка в декабре 2026 с sha256 всех файлов в `CHANGELOG.md`. После заморозки изменения вносятся только новыми версиями; каждая строка результатов указывает версию выборки.
- **Формат.** JSONL, одна запись на вопрос. Поля: `id`, `version`, `split`, `question{ru,zh,en}`, `question_type`, `category`, `answerable`, `answer{canonical, aliases, type, lang}`, `supporting_docs[{webpage_id, urn_uuid, uri, published_at, source, evidence_span_ru, evidence_span_zh}]`, `requires_multi_doc`, `time_invariance{label, anchor_date, votes, exclusion_rules_checked}`, `difficulty`, `provenance{draft_model, draft_prompt_id, seed_pool_ref, annotators, adjudicated, created_at}`.
- **Лицензия.** Разметка (вопросы, ответы, алиасы, метаданные, evidence-span) распространяется по лицензии CC BY 4.0.
- **Что не публикуется.** Полные тексты статей и их переводы: они остаются в корпусе ИВ РАН. В выборке — только стабильные идентификаторы `webpage_id`/`urn_uuid`, URL, даты публикации и короткие evidence-span.
- **Происхождение.** Черновики порождает модель $`g_{\text{draft}}\notin\mathcal{L}`$; 388 вопросов из промышленного репозитория используются как seed pool (`data/seed_pool/`) после перекладки ключей `warc_id → webpage_id`; они не являются эталоном, поскольку не содержат ответов и признака статичности.

## Оцениваемые системы

Описание конфигураций, промптов и режимов — в [docs/systems.md](docs/systems.md) и `code/configs/systems/`.

| Обозначение | Ретривер | Генератор | Число систем |
|---|---|---|---|
| $`f_{\text{prod}}`$ | $`\rho_{\text{prod}}`$: Qdrant (23,9 млн чанков, `distiluse-base-multilingual-cased-v2`) + SearchAPI | $`g_{\theta_{\text{prod}}}`$ — генератор промышленной системы (провайдер ИВ РАН, фактическая модель фиксируется по полю `model`) | 1 |
| $`f_\rho^{(m)}`$ | $`\rho_{\text{prod}}`$, выдача кэшируется и общая для всех $`m`$ | $`g_m`$, $`m\in\mathcal{L}`$ | 6 |
| $`f_0^{(m)}`$ | без поиска ($`\hat S=\varnothing`$) | $`g_m`$, $`m\in\mathcal{L}`$ | 6 |

Список открытых моделей $`\mathcal{L}`$ (провайдер ИВ РАН, OpenAI-совместимый API через llama-swap; замер доступности 2026-09-04):

1. DeepSeek-R1-Distill-Qwen-32B
2. Qwen3.6-27B
3. Qwen3.8-27B
4. GigaChat-20B-A3B
5. GLM-4.1V-9B-Thinking
6. Qwen-AgentWorld-35B-A3B

Исключены как специализированные: Hy-MT2-30B-A3B (машинный перевод), Laguna-XS-2.1, Qwen3-Coder-30B-A3B. Итого $`|\mathcal{H}_{\text{eval}}|=13`$.

Оговорка о провайдере: llama-swap при неизвестном идентификаторе модели может тихо подставить другую модель (так модель по умолчанию промышленной системы `Qwen/Qwen3.5-9B`, отсутствующая у провайдера, фактически заменяется на DeepSeek-R1-Distill-Qwen-32B). Поэтому клиент работает в режиме fail-fast: идентификатор проверяется по `/v1/models` до прогона, для каждого ответа сохраняется фактическое поле `model`, а снимок `/v1/models` записывается в `results/runs/<run_id>/`.

## Метрики

Определения, нормализация текста, обработка $`\mathrm{NA}`$ и промпты судьи — в [docs/metrics.md](docs/metrics.md). Все метрики принимают значения в $`[0,1]\cup\{\mathrm{NA}\}`$, ориентация «больше — лучше».

| Группа | Метрика | Определение | Область | Статус |
|---|---|---|---|---|
| По эталону | EM | $`\max_{a\in A^*_i}\mathbb{1}[\mathrm{norm}(\hat a)=\mathrm{norm}(a)]`$ | $`G^+`$ | новая |
| По эталону | F1 | токенный F1 после лемматизации, максимум по алиасам $`a\in A^*_i`$ | $`G^+`$ | новая |
| По эталону | BERTScore-F1 | мультиязычный энкодер, максимум по алиасам | $`G^+`$ | новая |
| По эталону | $`m_J^{\text{corr}}`$ | судья-LLM: правильность $`\hat a`$ относительно $`A^*_i`$, шкала 0–5, делённая на 5 | $`G^+`$ | новая, кандидат на первичную |
| По эталону | $`m_J^{(d)}`$ | рубрика судьи по семи измерениям $`d`$ (faithfulness, answer_relevancy, completeness, citation_accuracy, temporal_correctness, allegory_idiom_quality, hallucination_abstention), 0–5, делённая на 5 | $`G^+`$ | существующий прототип, подлежит валидации |
| Цитирование | $`\mathrm{CP}_{\text{id}}`$ | $`\lvert\hat S\cap S^*_i\rvert/\lvert\hat S\rvert`$; $`\mathrm{NA}`$ при $`\hat S=\varnothing`$ | $`G^+`$ | новая |
| Цитирование | $`\mathrm{CR}_{\text{id}}`$ | $`\lvert\hat S\cap S^*_i\rvert/\lvert S^*_i\rvert`$; для закрытой книги 0 | $`G^+`$ | новая |
| Цитирование | $`\mathrm{CP}_{\text{ent}}`$ | $`\frac{1}{\lvert\hat S\rvert}\sum_{\iota\in\hat S}\mathbb{1}[x_\iota\models\hat a]`$ через NLI или судью | $`G^+`$ | новая |
| Отказы | $`\mathrm{AR}`$ | $`\frac{1}{n_\varnothing}\sum_{G^{\varnothing}}\mathbb{1}[\hat a=\varnothing]`$ — доля верных отказов | $`G^{\varnothing}`$ | новая |
| Отказы | $`1-\mathrm{FAR}`$ | $`\mathrm{FAR}=\frac{1}{n_+}\sum_{G^+}\mathbb{1}[\hat a=\varnothing]`$ — доля ложных отказов | $`G^+`$ | новая |
| Поиск | Hit@k, Recall@k, MRR | относительно $`S^*_i`$, по выдаче $`\rho`$ | $`G^+`$, только $`f_{\text{prod}}`$ и $`f_\rho^{(m)}`$ | существующие, переносятся |
| Поиск | nDCG@k | относительно $`S^*_i`$, бинарная релевантность | $`G^+`$, только $`f_{\text{prod}}`$ и $`f_\rho^{(m)}`$ | новая |

Метрики по эталону и цитированию проходят валидацию по $`H_4`$ и входят в $`M'`$ только при $`\rho_S(m_k,\bar h)\ge0.5`$; метрики отказов и поиска детерминированы и включаются в $`M'`$ напрямую.

## Главная таблица результатов

Заполняется по итогам прогонов (январь–февраль 2027). Столбцы — метрики $`M'`$ (окончательный состав фиксируется после валидации), формат ячейки — `mean [lo; hi]` (парный бутстреп, 95 %); звёздочка при $`p_{\text{Holm}}<0.05`$ в сравнении с $`f_{\text{prod}}`$; последние столбцы — $`Q(f)`$ и ранг. Версия выборки: `v1.0`.

| Система | Генератор | Режим | $`m_J^{\text{corr}}`$ | F1 | BERTScore | $`\mathrm{CP}_{\text{id}}`$ | $`\mathrm{CR}_{\text{id}}`$ | $`\mathrm{AR}`$ | $`1-\mathrm{FAR}`$ | Recall@k | $`Q(f)`$ | Ранг |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| $`f_{\text{prod}}`$ | $`g_{\theta_{\text{prod}}}`$ | Qdrant + SearchAPI | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | DeepSeek-R1-Distill-Qwen-32B | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | Qwen3.6-27B | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | Qwen3.8-27B | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | GigaChat-20B-A3B | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | GLM-4.1V-9B-Thinking | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_\rho^{(m)}`$ | Qwen-AgentWorld-35B-A3B | $`\rho_{\text{prod}}`$ | — | — | — | — | — | — | — | — | — | — |
| $`f_0^{(m)}`$ | DeepSeek-R1-Distill-Qwen-32B | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |
| $`f_0^{(m)}`$ | Qwen3.6-27B | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |
| $`f_0^{(m)}`$ | Qwen3.8-27B | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |
| $`f_0^{(m)}`$ | GigaChat-20B-A3B | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |
| $`f_0^{(m)}`$ | GLM-4.1V-9B-Thinking | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |
| $`f_0^{(m)}`$ | Qwen-AgentWorld-35B-A3B | без поиска | — | — | — | — | 0 | — | — | $`\mathrm{NA}`$ | — | — |

Широкая таблица выше строится целью `make tables` из длинной таблицы `results/tables/main_table_long.csv` (одна строка — одна пара «система × метрика») со столбцами:

```
system_id, model_id_reported, quantization, retriever, k, prompt_version, temperature,
n_samples, metric, n, mean, ci_low, ci_high, delta_vs_prod, p_wilcoxon, p_holm,
run_id, git_sha, date
```

Здесь `model_id_reported` — фактическое поле `model` из ответов провайдера, `n` — число вопросов с $`m_k\ne\mathrm{NA}`$, `delta_vs_prod` — $`\bar\delta`$ относительно $`f_{\text{prod}}`$, `git_sha` — коммит кода, которым получен прогон.


## Материалы (Assets)

- [LinkReview](LINKREVIEW.md) — обзор литературы по четырём группам: оценка систем с дополнением поиском; судья на основе языковой модели и его смещения; временная динамика и построение выборок; китайско- и русскоязычные ресурсы, метрики генерации, модели
- [Code](code) — код разметки, систем, метрик и статистики; конфиги в `code/configs/`
- [Data](data/golden_set) — эталонная выборка (схема, версии, история изменений)
- [Paper](paper/main.pdf) — текст работы; собирается из [paper/main.tex](paper/main.tex)
- [Slides](slides/main.pdf) — презентация к защите; собирается из [slides/main.tex](slides/main.tex)
- [Docs](docs) — постановка задачи, инструкция разметки, метрики, системы, журнал решений


## Цитирование

```bibtex
@thesis{bagrov2027evalsystem,
  type       = {Bachelor's thesis},
  author     = {Bagrov, Alexander},
  title      = {Система оценки качества ответов больших языковых моделей по новостным текстам стран Восточной Азии},
  titleaddon = {A System for Evaluating the Quality of Large Language Model Answers on East Asian News Texts},
  school     = {Lomonosov Moscow State University, Faculty of Computational Mathematics and Cybernetics},
  address    = {Moscow},
  year       = {2027},
  url        = {https://github.com/Priestprog/east-asia-news-llm-eval},
  note       = {In Russian. English title: A System for Evaluating the Quality of Large Language Model Answers on East Asian News Texts}
}

@misc{bagrov2027goldenset,
  author       = {Bagrov, Alexander},
  title        = {East Asian News Static QA Golden Set},
  year         = {2027},
  howpublished = {\url{https://github.com/Priestprog/east-asia-news-llm-eval/tree/main/data/golden_set}},
  note         = {Version 1.0. Annotation licensed under CC BY 4.0}
}
```

## Лицензия

- Код — MIT, см. [LICENSE](LICENSE).
- Разметка эталонной выборки (вопросы, ответы, алиасы, метаданные, evidence-span в `data/golden_set/`) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Тексты новостных статей и их переводы не распространяются: в выборке публикуются только идентификаторы, URL, даты и короткие evidence-span; полные тексты остаются в корпусе ИВ РАН.
