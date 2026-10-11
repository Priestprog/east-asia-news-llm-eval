r"""Базовый эксперимент целиком: ``python -m code.audit [--stage download|compute|plots|all]``.

Этапы выполняются по порядку: загрузка сторонних наборов в ``data/external/``, расчёт таблиц
``results/audit/*.csv`` (FreshQA, остальные наборы, вопросы промышленной системы, сводная
таблица) и построение рисунков ``results/figures/`` по этим таблицам. Повторный запуск
даёт те же числа: версии данных и seed бутстрепа зафиксированы.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from code.audit import B, SEED

STAGES = ("download", "compute", "plots")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m code.audit", description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=(*STAGES, "all"), default="all")
    parser.add_argument("--B", type=int, default=B, help="число бутстреп-повторов")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    stages = STAGES if args.stage == "all" else (args.stage,)

    if "download" in stages:
        from code.audit import download

        download.download_all()
    if "compute" in stages:
        from code.audit import compute_datasets, compute_freshqa, compute_seed_pool, compute_summary

        compute_freshqa.run(B=args.B, seed=args.seed)
        compute_datasets.run(B=args.B, seed=args.seed)
        compute_seed_pool.run(B=args.B, seed=args.seed)
        compute_summary.run()
    if "plots" in stages:
        from code.audit import plots

        plots.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
