#!/usr/bin/env bash
# Режим строгой обработки ошибок: 
# -e: выйти при ошибке команды, -u: ошибка при пустой переменной, -o pipefail: ошибка в пайпе
set -euo pipefail

# Определяем директорию скрипта для корректной работы из любого места
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================"
echo "  FIGMA AGENT PIPELINE STARTED"
echo "================================"

cd "$SCRIPT_DIR"

# Конфигурация пайплайна
TARGET_NODE_ID="662:808"
OUTPUT_NAME="BlockchainSection"

echo ""
echo "[1/3] Запуск bootstrap.py — загрузка секции ${TARGET_NODE_ID}..."
python bootstrap.py --node-id "${TARGET_NODE_ID}"

echo ""
echo "[2/3] Запуск analyzer.py — анализ структуры..."
python analyzer.py

echo ""
echo "[3/3] Запуск agent.py — генерация компонента ${OUTPUT_NAME}..."
python agent.py \
  --task "Create a React + Tailwind component for the provided Figma section." \
  --output-name "${OUTPUT_NAME}"

echo ""
echo "================================"
echo "  PIPELINE COMPLETED SUCCESSFULLY"
echo "================================"