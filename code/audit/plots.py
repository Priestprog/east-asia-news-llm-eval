r"""Рисунки аудита по готовым таблицам ``results/audit/*.csv``; сырые данные не читаются.

* ``freshqa_staleness_sketch`` — эскиз графика ошибок первого прогона: квартальные версии FreshQA,
  доля изменившихся эталонов с 95%-ми бутстреп-интервалами;
* ``main_message`` — главный вывод работы: по всем 74 поздним версиям FreshQA эталоны
  быстро и медленно меняющихся вопросов устаревают, а статических почти нет; сплошная линия —
  изменилось множество ответов (полоса — 95%-й интервал), пунктир — только канонический ответ.

Даты в метаданных PDF задаются переменной окружения ``SOURCE_DATE_EPOCH``.
"""

from __future__ import annotations

from pathlib import Path

from code.audit import FIGURES_DIR, RESULTS_DIR
from code.audit.common import read_csv, rel

FACT_TYPES = ("fast-changing", "slow-changing", "never-changing")
LABELS = {
    "never-changing": "неизменные (never-changing)",
    "slow-changing": "медленно меняющиеся (slow-changing)",
    "fast-changing": "быстро меняющиеся (fast-changing)",
}
COLORS = {"fast-changing": "#c0392b", "slow-changing": "#d68910", "never-changing": "#2e4bb3"}


def _series(rows: list[dict], fact_type: str, definition: str) -> list[dict]:
    pts = [r for r in rows if r["fact_type"] == fact_type and r["definition"] == definition]
    return sorted(pts, key=lambda r: float(r["months"]))


def _save(fig, stem: Path) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = [stem.with_suffix(".pdf"), stem.with_suffix(".png")]
    fig.savefig(paths[0])
    fig.savefig(paths[1], dpi=200)
    return paths


def plot_sketch(rows: list[dict], stem: Path = FIGURES_DIR / "freshqa_staleness_sketch") -> list[Path]:
    """Эскиз графика ошибок по квартальным версиям (первый прогон)."""
    import matplotlib.pyplot as plt

    quarterly = [r for r in rows if r["quarterly"] == "True"]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for fact_type in ("never-changing", "slow-changing", "fast-changing"):
        pts = _series(quarterly, fact_type, "any")
        x = [float(r["months"]) for r in pts]
        y = [100 * float(r["rate"]) for r in pts]
        err = [[100 * (float(r["rate"]) - float(r["ci_low"])) for r in pts],
               [100 * (float(r["ci_high"]) - float(r["rate"])) for r in pts]]
        label = {"never-changing": "статические (never-changing)", "slow-changing": "медленно меняющиеся",
                 "fast-changing": "быстро меняющиеся"}[fact_type]
        ax.errorbar(x, y, yerr=err, marker="o", capsize=3, label=label)
    ax.set_xlabel("Прошло месяцев с базовой версии")
    ax.set_ylabel("Доля изменившихся эталонных ответов, %")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend(loc="center right")
    ax.set_title("FreshQA: устаревание эталона (эскиз, 95% интервалы)")
    fig.tight_layout()
    paths = _save(fig, stem)
    plt.close(fig)
    return paths


def plot_main_message(rows: list[dict], stem: Path = FIGURES_DIR / "main_message") -> list[Path]:
    """Главный вывод: устаревание эталонов FreshQA по всем версиям с интервалами."""
    import matplotlib.pyplot as plt

    last = {ft: _series(rows, ft, "any")[-1] for ft in FACT_TYPES}
    n_versions = len({r["version"] for r in rows})
    months = float(last["fast-changing"]["months"])

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for ft in FACT_TYPES:
        pts = _series(rows, ft, "any")
        x = [0.0] + [float(r["months"]) for r in pts]
        y = [0.0] + [100 * float(r["rate"]) for r in pts]
        lo = [0.0] + [100 * float(r["ci_low"]) for r in pts]
        hi = [0.0] + [100 * float(r["ci_high"]) for r in pts]
        ax.fill_between(x, lo, hi, color=COLORS[ft], alpha=0.18, linewidth=0)
        ax.plot(x, y, color=COLORS[ft], linewidth=2, label=LABELS[ft])
        main = _series(rows, ft, "main")
        ax.plot([0.0] + [float(r["months"]) for r in main], [0.0] + [100 * float(r["rate"]) for r in main],
                color=COLORS[ft], linewidth=1, linestyle="--")
        value = 100 * float(last[ft]["rate"])
        ax.annotate(f"{value:.0f} %", xy=(months, value), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=11, fontweight="bold", color=COLORS[ft])
    ax.plot([], [], color="0.4", linewidth=1, linestyle="--", label="только канонический ответ")
    ax.set_xlim(0, months + 3.5)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Прошло месяцев с версии 15.10.2023")
    ax.set_ylabel("Изменился эталонный ответ, % вопросов")
    ax.grid(alpha=0.3)
    ax.legend(loc="center right", fontsize=9, frameon=True)
    ax.set_title("Эталон сохраняют только статические вопросы", fontsize=13, fontweight="bold", loc="left")
    fig.text(0.01, 0.01, f"FreshQA, поздних версий: {n_versions}; полосы — 95%-е бутстреп-интервалы по вопросам.",
             fontsize=8, color="0.35", ha="left", va="bottom", transform=fig.transFigure)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    paths = _save(fig, stem)
    plt.close(fig)
    return paths


def run() -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    rows = read_csv(RESULTS_DIR / "freshqa_staleness.csv")
    paths = plot_sketch(rows) + plot_main_message(rows)
    print("рисунки: " + ", ".join(rel(p) for p in paths))
    return paths


if __name__ == "__main__":
    run()
