# Makefile каркаса ВКР «Система оценки качества ответов больших языковых моделей
# по новостным текстам стран Восточной Азии».
#
# Все цели вызывают модули пакета code/ из корня репозитория (python -m code.<пакет>.<модуль>),
# поэтому make запускается из корня. Интерпретатор переопределяется переменной PYTHON,
# например: make check PYTHON=code/.venv/bin/python
#
# Статус: каркас. Содержательные модули завершаются NotImplementedError; рабочей является
# цель check (компиляция, импорт, валидация JSON/YAML).

PYTHON       ?= python3
EVAL_CONFIG  ?= code/configs/eval.yaml
JUDGE_CONFIG ?= code/configs/judge.yaml
SYSTEM       ?= code/configs/systems/prod.yaml
GS_VERSION   ?= v1.0
# Идентификатор прогона: дата-время и имя конфигурации системы (например 20270115-093000-prod).
RUN_ID       ?= $(shell date +%Y%m%d-%H%M%S)-$(notdir $(basename $(SYSTEM)))

.PHONY: help drafts agreement build-gs run judge validate stats tables check

help: ## список целей
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

# --- Построение эталонной выборки G = G+ ⊔ G∅ -------------------------------------------

drafts: ## отбор документов webmedia ∩ Qdrant, черновики моделью g_draft ∉ L, листы для R=3 разметчиков
	$(PYTHON) -m code.annotation.sample_documents --config $(EVAL_CONFIG)
	$(PYTHON) -m code.annotation.generate_drafts --config $(EVAL_CONFIG)
	$(PYTHON) -m code.annotation.export_sheets --config $(EVAL_CONFIG)

agreement: ## согласие разметчиков: Krippendorff α (≥0.67 допустимо, ≥0.8 надёжно), Fleiss κ, попарный F1 ≥ 0.8
	$(PYTHON) -m code.annotation.agreement --config $(EVAL_CONFIG)

build-gs: ## адъюдикация расхождений и сборка Golden Set версии GS_VERSION (JSONL по schema.json, split, sha256)
	$(PYTHON) -m code.annotation.adjudicate --config $(EVAL_CONFIG)
	$(PYTHON) -m code.annotation.build_golden_set --config $(EVAL_CONFIG) --version $(GS_VERSION)

# --- Прогоны систем H_eval и судьи --------------------------------------------------------

run: ## генерации системы SYSTEM на split из eval.yaml → results/runs/RUN_ID/{generations.jsonl, meta.json}
	$(PYTHON) -m code.eval.run_generation --config $(EVAL_CONFIG) --system $(SYSTEM) --run-id $(RUN_ID)

judge: ## оценка генераций прогона RUN_ID судьёй (рубрика из 8 измерений) → results/runs/RUN_ID/judge.jsonl
	$(PYTHON) -m code.eval.run_judge --config $(EVAL_CONFIG) --judge-config $(JUDGE_CONFIG) --run-id $(RUN_ID)

# --- Валидация метрик, статистика, таблицы -----------------------------------------------

validate: ## отбор M' = {m_k : ρ_S(m_k, h̄) ≥ rho_min} по человеческим оценкам → results/tables/validation.csv
	$(PYTHON) -m code.eval.validate_metrics --config $(EVAL_CONFIG)

stats: ## парный бутстреп (B=10^4), Уилкоксон, поправка Холма (α=0.05), Cliff's δ для всех f' ≠ f_prod
	$(PYTHON) -m code.eval.stats --config $(EVAL_CONFIG)

tables: ## results/tables/main_table.md и main_table_long.csv (mean [lo; hi], звёздочка при p_Holm < 0.05, Q(f), ранг)
	$(PYTHON) -m code.eval.make_tables --config $(EVAL_CONFIG)

# --- Проверки каркаса ---------------------------------------------------------------------

check: ## py_compile всех модулей, импорт пакетов, валидация всех JSON и YAML (включая CITATION.cff)
	@echo "py_compile: code/**/*.py"
	@find code -name '*.py' -not -path '*/.venv/*' -print0 | xargs -0 $(PYTHON) -m py_compile
	@echo "import: code, code.annotation, code.systems, code.eval и все модули"
	@$(PYTHON) -c "import importlib, pkgutil, code as pkg; \
	  mods = [m.name for m in pkgutil.walk_packages(pkg.__path__, 'code.')]; \
	  [importlib.import_module(m) for m in mods]; \
	  print('  ok', len(mods), 'модулей')"
	@echo "JSON:"
	@find . \( -path ./.git -o -path '*/.venv' -o -path './results/runs' \) -prune -o -name '*.json' -print | sort | \
	  while read -r f; do \
	    $(PYTHON) -c "import json, sys; json.load(open(sys.argv[1], encoding='utf-8'))" "$$f" || exit 1; \
	    echo "  ok $$f"; \
	  done
	@echo "YAML:"
	@if $(PYTHON) -c "import yaml" 2>/dev/null; then \
	  { find code -name '*.yaml' -not -path '*/.venv/*' | sort; echo CITATION.cff; } | \
	  while read -r f; do \
	    $(PYTHON) -c "import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding='utf-8'))" "$$f" || exit 1; \
	    echo "  ok $$f"; \
	  done; \
	else \
	  echo "  pyyaml не установлен — проверка YAML пропущена (pip install -r code/requirements.txt)"; \
	fi
	@echo "check: успешно"
