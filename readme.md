# AgenBroMCP

**Переносимый драйвер браузера + MCP-сервер**: открывает страницы, читает контент из DOM (включая текст на картинках через OCR), заполняет формы и выполняет клики/переходы — с полной записью артефактов на диск.

## Что это

AgenBroMCP управляется агентом через два интерфейса:

1. **MCP Server (`stdio`)** — стандартные MCP-инструменты для любого MCP-клиента (на базе официального `mcp` SDK / FastMCP).
2. **JSON-действия через `stdin` / CLI** — драйвер исполняет команды, пишет артефакты и возвращает JSON-ответ.

Каждая страница фиксируется снапшотом: `artifacts/<session>/<page>/` → `page.html`, `page.png`, `manifest.json`, `actions.log`. Ничего не «выдумывается»: весь контент извлекается из DOM и пикселей, OCR-текст картинок записывается в манифест с честной пометкой `ocr_failed`, если распознавание не удалось.

## Возможности

| Область | Инструменты |
|---|---|
| Сессия и артефакты | `open_page`, снапшоты, `storage_state` (cookies) |
| Читатель страницы | текст, ссылки, заголовки, инвентарь картинок, accessibility-tree |
| Картинки | захват через рендер браузера, препроцессинг, OCR (`tesseract` + `rapidocr` fallback) |
| Активные элементы | реестр `collect_actionables()`: `input`, `select`, `checkbox`, `radio`, `button`, `link` |
| Формы | `fill`, `select`, `check` / `uncheck` — каждый шаг логируется (`before`/`after`) |
| Клики и переходы | `click`, `press`, `goto` + пост-экшен снапшот (скриншот, HTML-diff, URL) |
| Протокол | JSON-команды `{op, target, value, session}` → ответ `{ok, artifacts[], state, page}` |

## Установка

```bash
git clone https://github.com/Vidusacha/AgenBroMCP.git
cd AgenBroMCP
uv sync                      # или: pip install -r requirements.txt
playwright install chromium  # браузер
scripts/bootstrap.ps1        # Windows  /  scripts/bootstrap.sh — Linux/macOS
```

Зависимости: Python 3.11+, Playwright, Chromium. OCR: системный `tesseract` (с автопоиском пути) **или** portable-fallback `rapidocr-onnxruntime` (работает сразу после `pip install`, без системных бинарников).

## Использование

**Как MCP-сервер** (например, в MCP-клиенте):

```json
{
  "mcpServers": {
    "agenbro": { "command": "python", "args": ["-m", "agenbro.mcp_server"] }
  }
}
```

Инструменты: `browser_open`, `browser_read`, `browser_fill`, `browser_select`, `browser_check`, `browser_click`, `browser_press`.

**Через CLI / JSON-stdin:**

```bash
python -m agenbro.cli   # подаёт JSON-команды в stdin, получает JSON-ответы
```

## Тесты

Каждая фаза развития покрыта приёмочными тестами (`tests/test_phase*.py`) — запуск окружения, создание артефактов, читатель DOM, OCR, реестр actionables, заполнение форм, клики, протокол. Полный план и матрица тестов: [`plan.md`](plan.md), задачи: [`TASKS.md`](TASKS.md).

```bash
pytest
```

## Roadmap

- [x] Фаза 0 — подготовка окружения и переносимость
- [ ] Фаза 1 — сессия и артефакты
- [ ] Фаза 2 — читатель страницы (текст, ссылки, картиночный инвентарь)
- [ ] Фаза 3 — картинки: инвентарь + скачивание + препроцессинг + OCR
- [ ] Фаза 4 — реестр активных элементов (selector → роль)
- [ ] Фаза 5 — заполнение полей
- [ ] Фаза 6 — клики, нажатия, переходы
- [ ] Фаза 7 — протокол управления (stdin JSON + MCP Server)
- [ ] Фаза 8 — состояние и мульти-страничность
- [ ] Защита от опасных действий (`danger`/`confirm` в командах)

## Принципы

- **Кроссплатформенность**: все пути через `pathlib.Path`, Windows / Linux / macOS.
- **Честность агента**: драйвер не интерпретирует «по памяти» — только DOM, скриншоты и OCR-манифест.
- **Полная трассировка**: каждое действие оставляет артефакт и запись в `actions.log` с `before`/`after`.

## Лицензия

MIT (см. репозиторий).

