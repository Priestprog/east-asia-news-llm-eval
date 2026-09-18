r"""Построение эталонной выборки $G = G^+ \sqcup G^{\varnothing}$.

Протокол (см. ``docs/problem_statement.md``, раздел «Протокол разметки»):

1. ``sample_documents`` — стратифицированный отбор документов из
   ``webmedia.webpages`` $\cap$ Qdrant (домен × месяц × категория), переизбыток ×2;
2. ``generate_drafts`` — черновики $(q, a, S, \text{evidence}, \text{тип}, \text{дата})$
   моделью $g_{\mathrm{draft}} \notin \mathcal{L}$; старые 388 вопросов — seed pool
   после перекладки ``warc_id`` → ``webpage_id``;
3. ``export_sheets`` — листы для независимой разметки $R = 3$ (не менее одного
   разметчика, читающего по-китайски) и для человеческой валидации $h^{(r)}_{i,f}$;
4. ``agreement`` — Krippendorff $\alpha$ по инвариантности, отвечаемости и типу
   ($\alpha \ge 0.67$ допустимо, $\ge 0.8$ надёжно), попарный F1 по ответам $\ge 0.8$;
5. ``adjudicate`` — включение при единогласии, иначе адъюдикация четвёртым экспертом;
6. ``build_golden_set`` — сборка JSONL по ``data/golden_set/schema.json``, разбиение
   dev (30) / test, заморозка версии (sha256, CHANGELOG).
"""
