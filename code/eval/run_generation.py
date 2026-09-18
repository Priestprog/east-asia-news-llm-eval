r"""Прогон системы $f \in \mathcal{H}_{\mathrm{eval}}$ на split Golden Set.

Результат — каталог ``results/runs/<run_id>/`` с файлами:

* ``generations.jsonl`` — по строке на вопрос: ``question_id, system_id, answer, cited_ids,
  retrieved_ids, model_reported, latency_s, raw, created_at``;
* ``meta.json`` — паспорт прогона: ``run_id, system`` (``System.describe()``), ``git_sha``
  репозитория, ``models_snapshot`` (ответ ``/v1/models`` провайдера до прогона), ``golden_set``
  (путь, версия, sha256, split, $n$), ``date``, версии ключевых пакетов.

Условия воспроизводимости: ``temperature = 0``, фиксированный ``seed``; fail-fast при
неизвестной модели (``UnknownModelError``) — прогон прерывается, частичный результат
помечается ``meta.json['status'] = 'aborted'``. Для $f_{\mathrm{prod}}$ выдача ретривера
пишется в кэш (``RetrieverCache``) для последующих прогонов $f_\rho^{(m)}$.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

GENERATION_FIELDS: tuple[str, ...] = (
    "question_id", "system_id", "answer", "cited_ids", "retrieved_ids",
    "model_reported", "latency_s", "raw", "created_at",
)
META_FIELDS: tuple[str, ...] = (
    "run_id", "system", "git_sha", "models_snapshot", "golden_set", "date", "packages", "status",
)


def load_golden_set(path: str | Path, split: str | None = None) -> list[dict]:
    """Читает JSONL Golden Set; при ``split`` оставляет записи с этим значением поля ``split``."""
    raise NotImplementedError("реализация — часть работы")


def git_sha(repo_root: str | Path | None = None) -> str:
    """``git rev-parse HEAD`` репозитория (с пометкой ``-dirty`` при незакоммиченных изменениях)."""
    raise NotImplementedError("реализация — часть работы")


def snapshot_models(base_url: str | None, api_key: str | None) -> dict:
    """Снимок ``/v1/models`` провайдера до прогона — защита от тихой подмены модели."""
    raise NotImplementedError("реализация — часть работы")


def write_meta(run_dir: Path, meta: dict) -> None:
    """Записывает ``meta.json`` (поля ``META_FIELDS``)."""
    raise NotImplementedError("реализация — часть работы")


def run(system_config_path: str, eval_config_path: str, run_id: str, resume: bool = False) -> Path:
    r"""Полный прогон: конфигурации → ``load_system`` → снимок моделей → цикл по $q_i$ →
    ``generations.jsonl`` + ``meta.json``. ``resume`` — продолжить прерванный прогон по уже
    записанным ``question_id``."""
    raise NotImplementedError("реализация — часть работы")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="code/configs/eval.yaml", help="eval.yaml")
    parser.add_argument("--system", required=True, help="YAML системы из code/configs/systems/")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"реализация — часть работы (аргументы: {vars(args)})")


if __name__ == "__main__":
    raise SystemExit(main())
