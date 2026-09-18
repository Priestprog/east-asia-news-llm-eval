r"""Программный каркас ВКР «Система оценки качества ответов больших языковых моделей
по новостным текстам стран Восточной Азии».

Пакеты:

* ``code.annotation`` — построение эталонной выборки $G = G^+ \sqcup G^{\varnothing}$
  (отбор документов, черновики, листы разметки, согласие, адъюдикация, сборка);
* ``code.systems`` — обёртки оцениваемых систем $f \in \mathcal{H}_{\mathrm{eval}}$
  ($f_{\mathrm{prod}}$, $f_0^{(m)}$, $f_\rho^{(m)}$) с единым выходом ``SystemOutput``;
* ``code.eval`` — семейство метрик $M$, судья-LLM, валидация $M'$, статистика, таблицы.

Статус: каркас. Содержательные функции снабжены докстрингами с формулами из постановки
задачи и завершаются ``NotImplementedError``; их реализация — содержание работы.
Реализованы только служебные элементы: типы данных, константы, разбор аргументов,
чтение конфигураций.

Примечание об имени пакета. ``code`` совпадает с именем модуля стандартной библиотеки,
поэтому модули запускаются из корня репозитория командой
``python -m code.<пакет>.<модуль>``: каталог запуска стоит в ``sys.path`` первым, и
локальный пакет получает приоритет. Отладчик ``pdb`` внутри этого пакета недоступен.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

REPO_ROOT = Path(__file__).resolve().parent.parent

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any) -> Any:
    """Рекурсивно подставляет значения переменных окружения вместо ``${VAR}``.

    Строка, целиком состоящая из ``${VAR}`` при незаданной переменной, заменяется на
    ``None``, чтобы отсутствие секрета обнаруживалось явно, а не тихо превращалось
    в пустую строку. Словари и списки обрабатываются поэлементно.
    """
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, str):
        full = _ENV_PATTERN.fullmatch(value.strip())
        if full:
            return os.environ.get(full.group(1))
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    return value


def load_config(path: str | Path) -> dict:
    """Читает YAML-конфигурацию из ``code/configs`` и подставляет переменные окружения.

    Переменные берутся из файла ``.env`` в корне репозитория (если установлен
    ``python-dotenv``) и из окружения процесса. Зависимости импортируются лениво,
    чтобы пакет импортировался без установленного виртуального окружения.
    """
    import yaml  # noqa: WPS433 — ленивый импорт третьесторонней зависимости

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return expand_env(raw)
