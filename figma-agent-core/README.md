# Figma Agent Core

Python-агент для анализа макетов Figma и генерации React / Next.js / Tailwind CSS компонентов с помощью LLM.

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
cp .env.example .env
```

Отредактируй `.env`:

- `FIGMA_TOKEN` — токен из [Figma → Settings → Personal Access Tokens](https://www.figma.com/settings).
- `FIGMA_URL` — ссылка на файл или конкретный node в Figma.
- Выбери провайдера LLM: раскомментируй нужную секцию (Ollama или Kimi) и закомментируй другую.

> **Важно:** файл `.env` не коммитится — он уже добавлен в `.gitignore`. Если токен был случайно раскрыт, немедленно отзови его в панели Figma и создай новый.

### 3. Запуск полного пайплайна

```bash
bash run_all.sh
```

Или пошагово:

```bash
# 1. Загрузить структуру из Figma в figma_node.json (с семантическим сжатием)
python bootstrap.py

# 2. Посмотреть список секций и их ID
python analyzer.py

# 3. Отправить задачу агенту и сохранить компонент
python agent.py \
  --task "Create a React + Tailwind component for the 'Блокчейн' section." \
  --node-id "662:808" \
  --output-name "BlockchainSection"
```

### Работа с конкретной секцией

Чтобы не передавать в LLM весь холст, используй `--node-id`:

```bash
# Загрузить только одну секцию
python bootstrap.py --node-id "662:808"

# Проанализировать её
python analyzer.py --node-id "662:808"

# Сгенерировать компонент
python agent.py \
  --task "Create a React + Tailwind component for this section." \
  --output-name "BlockchainSection"
```

После выполнения в директории `components/` появится файл `BlockchainSection.tsx`, а полный ответ LLM будет сохранён в `agent_outputs/`.

Агент поддерживает два режима генерации:
1. **Инструменты (ReAct):** модель может вызвать `ACTION: WRITE_FILE(component_name='...', code='''...''')` — агент перехватит вызов и запишет файл.
2. **Fallback:** если модель не использовала `WRITE_FILE`, но пользователь указал `--output-name`, агент извлечёт код из markdown-блока ```tsx ... ``` и сохранит его.

## Семантическое сжатие контекста

`bootstrap.py` по умолчанию применяет семантическое сжатие дерева Figma:

- Удаляются невидимые слои (`visible: false`).
- Пропускаются декоративные примитивы без Auto Layout (`RECTANGLE`, `ELLIPSE`, `VECTOR`), если у них нет структурной роли или дизайн-токенов.
- На глубине > 8 дети заменяются на краткое `children_summary`.
- Сохраняются `FRAME` с Auto Layout, `TEXT`, `INSTANCE`, `COMPONENT`, а также ноды с `fills` / `strokes` / `effects`.

Это позволяет уместить даже большие макеты в контекст локальной LLM.

Чтобы отключить сжатие:

```bash
python bootstrap.py --no-compress
```

## Дизайн-токены и ассеты

`bootstrap.py` извлекает и сохраняет в `figma_node.json`:

- `fills` — цвета в HEX и `rgb()` (SOLID, GRADIENT_LINEAR, IMAGE).
- `strokes` — обводки.
- `effects` — тени и размытия.
- `style` для TEXT — `fontSize`, `fontWeight`, `fontFamily`, `lineHeightPx`, `letterSpacing`.
- `absoluteBoundingBox` — координаты и размеры.

При запуске `agent.py` автоматически:

1. Находит ноды, помеченные как ассеты (`isAsset`).
2. Запрашивает URL экспорта через Figma Images API.
3. Скачивает PNG/SVG в `public/images/`.
4. Добавляет `publicPath` в контекст, чтобы LLM мог использовать локальный путь.

Чтобы отключить скачивание ассетов:

```bash
python agent.py --task "..." --output-name X --skip-assets
```

## Структура проекта

| Файл | Назначение |
|------|------------|
| `bootstrap.py` | Подключается к Figma API, извлекает дизайн-токены (цвета, шрифты, тени), сжимает дерево и кеширует в `figma_node.json`. Поддерживает `--node-id`. |
| `analyzer.py` | Читает `figma_node.json`, выводит семантическую карту макета и статистику, предоставляет инструмент `get_node_details`. Поддерживает `--node-id`. |
| `agent.py` | Загружает JSON-контекст, скачивает ассеты в `public/images/`, отправляет задачу в LLM, распознаёт инструменты (`WRITE_FILE`, `FETCH_NODE`) и сохраняет компонент в `components/`. |
| `file_writer.py` | Утилита для безопасной записи `.tsx` компонентов с валидацией имён и защитой от Path Traversal. |
| `asset_downloader.py` | Скачивает изображения и векторы через Figma Images API и сохраняет их в `public/images/`. |
| `run.sh` | Wrapper для запуска отдельных Python-скриптов в Git Bash / MSYS2. |
| `run_all.sh` | Полный пайплайн: bootstrap → analyzer → agent. |

## Требования

- Python 3.10+
- `requests`
- `python-dotenv`
- Локально запущенная [Ollama](https://ollama.com/) (если используется локальная модель) или доступ к Kimi API.

## Безопасность

- Никогда не добавляй `.env` в git.
- Храни токены Figma и LLM только в переменных окружения или секрет-менеджере.
- При утечке токена немедленно отзови его и выпусти новый.
