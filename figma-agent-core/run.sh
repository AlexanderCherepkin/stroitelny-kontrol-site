#!/usr/bin/env bash
# Wrapper для запуска Python-скриптов проекта в Git Bash / MSYS2 на Windows.
# Решает проблему ложного exit code 1 из-за удалённой временной cwd-директории Claude Code.
#
# Использование:
#   bash run.sh agent.py
#   bash run.sh analyzer.py
#   bash run.sh bootstrap.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${1:-}"

if [[ -z "$PYTHON_SCRIPT" ]]; then
    echo "Ошибка: не указан Python-скрипт для запуска."
    echo "Пример: bash run.sh agent.py"
    exit 1
fi

# Переходим в директорию проекта и заменяем текущий процесс на Python.
# exec нужен, чтобы bash не пытался возвращаться в несуществующую временную cwd.
cd "$SCRIPT_DIR" && exec python "$PYTHON_SCRIPT"
