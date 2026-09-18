r"""Судья-LLM: рубрика из 8 измерений по шкале 0–5.

Метрики судьи $m_J^{(d)} = \mathrm{score}_d / 5 \in [0, 1]$:

* $m_J^{\mathrm{corr}}$ — «правильность относительно $A^*_i$» (``correctness_vs_reference``):
  **новое измерение**, у существующей рубрики его нет; кандидат на первичную метрику
  (гипотеза $H_4$: $\rho_S(m_J^{\mathrm{corr}}, \bar h) \ge 0.5$);
* $m_J^{(d)}$, $d \in$ {faithfulness, answer_relevancy, completeness, citation_accuracy,
  temporal_correctness, allegory_idiom_quality, hallucination_abstention} — существующая
  рубрика ``production/backend/evaluation/judge/rubric.py`` репозитория ivran-lab/chinese-media
  (прототип автора, не запускавшийся и не валидированный) — кандидатное подсемейство $M$.

Ограничения постановки: судья $\notin \mathcal{L} \cup \{g_{\theta_{\mathrm{prod}}}\}$ либо ансамбль двух
судей; ``temperature = 0``; отчёт о собственной воспроизводимости; отдельная проверка
самопредпочтения ($H_5$). Правило NA: измерение, требующее эталона, не вычисляется на
$G^{\varnothing}$; измерения, требующие контекстов, — для $f_0^{(m)}$ (``None``).
Балл вне шкалы или неразобранный JSON → ``None`` с записью в ``raw['parse_error']``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCALE_MIN, SCALE_MAX = 0, 5

NEW_DIMENSIONS: tuple[str, ...] = ("correctness_vs_reference",)
LEGACY_DIMENSIONS: tuple[str, ...] = (
    "faithfulness",
    "answer_relevancy",
    "completeness",
    "citation_accuracy",
    "temporal_correctness",
    "allegory_idiom_quality",
    "hallucination_abstention",
)
RUBRIC_DIMENSIONS: tuple[str, ...] = NEW_DIMENSIONS + LEGACY_DIMENSIONS
"""Восемь измерений рубрики; описания и якоря шкалы — в ``code/configs/judge.yaml``."""


@dataclass
class JudgeVerdict:
    """Результат оценки одного ответа: балл 0–5 по каждому измерению (``None`` = NA)."""

    scores: dict[str, int | None]
    rationales: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)      # bad_citations, n_idioms_found, abstained
    raw: dict = field(default_factory=dict)
    model_reported: str = ""
    prompt_version: str = ""

    def metrics(self) -> dict[str, float | None]:
        r"""$m_J^{(d)} = \mathrm{score}_d / 5$ по всем измерениям."""
        return {d: Judge.to_metric(s) for d, s in self.scores.items()}


class Judge:
    """Судья-LLM по конфигурации ``code/configs/judge.yaml``."""

    def __init__(self, config: Mapping[str, Any], client=None) -> None:
        self.config = dict(config)
        self.model: str | None = config.get("model")
        self.ensemble: list[str] = list(config.get("ensemble") or [])
        self.dimensions: list[dict] = list(config.get("dimensions") or [])
        self.prompt_version: str = str(config.get("prompt_version", "judge-v1"))
        self._client = client
        keys = [d["key"] for d in self.dimensions]
        if keys and tuple(keys) != RUBRIC_DIMENSIONS:
            raise ValueError(f"Рубрика в конфигурации {keys} не совпадает с RUBRIC_DIMENSIONS")

    @staticmethod
    def to_metric(score: int | None) -> float | None:
        r"""$\mathrm{score} \in \{0, \dots, 5\} \mapsto \mathrm{score} / 5$; вне шкалы или ``None`` → ``None``."""
        if score is None or not SCALE_MIN <= score <= SCALE_MAX:
            return None
        return score / SCALE_MAX

    def assert_not_in_candidates(self, candidate_models: Sequence[str], prod_generator: str | None) -> None:
        r"""Проверка ограничения судья $\notin \mathcal{L} \cup \{g_{\theta_{\mathrm{prod}}}\}$ до прогона."""
        raise NotImplementedError("реализация — часть работы")

    def applicable_dimensions(self, golden_item: Mapping[str, Any], has_contexts: bool) -> list[str]:
        r"""Измерения, определённые для пары (запись, система): ``requires: [reference]`` — только $G^+$;
        ``requires: [contexts]`` — только при наличии процитированных документов."""
        raise NotImplementedError("реализация — часть работы")

    def build_prompt(
        self,
        question: str,
        answer: str | None,
        golden_item: Mapping[str, Any],
        contexts: Sequence[Mapping[str, Any]] | None,
    ) -> list[dict]:
        """Промпт версии ``prompt_version``: рубрика с якорями шкалы, эталон (для ``correctness_vs_reference``),
        процитированные документы, требование JSON-контракта ``{dimension: {score, rationale, ...}}``."""
        raise NotImplementedError("реализация — часть работы")

    def parse_verdict(self, raw_text: str, model_reported: str) -> JudgeVerdict:
        """Разбор JSON-ответа судьи; невалидный балл → ``None`` с ``raw['parse_error']``."""
        raise NotImplementedError("реализация — часть работы")

    def score(
        self,
        question: str,
        answer: str | None,
        golden_item: Mapping[str, Any],
        contexts: Sequence[Mapping[str, Any]] | None,
    ) -> JudgeVerdict:
        r"""Оценка одного ответа при ``temperature = 0``; при непустом ``ensemble`` — среднее баллов
        по судьям с округлением до целого и сохранением всех вердиктов в ``raw``."""
        raise NotImplementedError("реализация — часть работы")

    def reproducibility_report(self, items: Sequence[Mapping[str, Any]], n_repeats: int = 3) -> dict:
        r"""Собственная воспроизводимость судьи: доля точных совпадений баллов и Krippendorff $\alpha$
        (interval) между повторами при ``temperature = 0`` на выборке из ``reproducibility.sample_size`` пар."""
        raise NotImplementedError("реализация — часть работы")
