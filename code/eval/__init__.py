r"""Семейство метрик $M$, судья, валидация, статистика и таблицы.

Каждая метрика $m_k : \mathcal{A} \times 2^{\mathcal{I}} \times G_i \to [0, 1] \cup \{\mathrm{NA}\}$,
«больше — лучше»; ``None`` в коде обозначает $\mathrm{NA}$. Агрегация по системе $f$:
$\bar m_k(f) = \frac{1}{|I_k(f)|} \sum_{i \in I_k(f)} m_k(f(q_i); G_i)$,
$I_k(f) = \{i : m_k \ne \mathrm{NA}\}$.

Модули:

* ``metrics_reference`` — по эталону ($G^+$): EM, токенный F1, BERTScore-F1, косинусная близость;
* ``metrics_citation`` — цитирование: $\mathrm{CP}_{\mathrm{id}}$, $\mathrm{CR}_{\mathrm{id}}$, $\mathrm{CP}_{\mathrm{ent}}$;
* ``metrics_abstention`` — отказы: $\mathrm{AR}$, $\mathrm{FAR}$ (в таблице — $1 - \mathrm{FAR}$);
* ``metrics_retrieval`` — компонент $\rho$: Hit@k, Recall@k, MRR, nDCG@k;
* ``judge`` — судья-LLM: $m_J^{\mathrm{corr}}$ (новое измерение) и $m_J^{(d)}$ по существующей рубрике;
* ``validate_metrics`` — отбор $M' = \{m_k : \rho_S(m_k, \bar h) \ge \rho_{\min}\}$;
* ``stats`` — парный бутстреп, критерий Уилкоксона, поправка Холма, Cliff's $\delta$, композит $Q(f)$;
* ``run_generation``, ``run_judge``, ``make_tables`` — конвейер прогона и отчётные таблицы.
"""

NA = None
"""Обозначение $\\mathrm{NA}$: метрика не определена для данной пары (ответ, эталон)."""
