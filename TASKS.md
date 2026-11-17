# AgenBroMCP — План разработки и задачи (Development Backlog)

Цель проекта: переносимый драйвер браузера и MCP-сервер (с поддержкой JSON-stdin и CLI), который открывает страницы, извлекает структурированный контент из DOM, распознаёт текст на картинках через OCR, заполняет формы и выполняет клики/переходы с полной записью артефактов и защитой от опасных действий.

---

## Архитектурные принципы и переносимость
1. **Кроссплатформенность (Windows / Linux / macOS):**
   - Все пути строятся через `pathlib.Path`.
   - Зависимости фиксируются в `pyproject.toml` и `uv.lock` + скрипты быстрой инициализации на новой машине (`scripts/bootstrap.ps1` и `scripts/bootstrap.sh`).
   - Поддержка OCR: `tesseract` (с автоопределением пути на Windows/Linux) + встроенный portable-fallback через `rapidocr-onnxruntime` (работает без системных бинарников сразу после `uv sync`).
2. **Двойной интерфейс:**
   - **MCP Server (`stdio`)** на базе официального `mcp` SDK (`MCPServer`).
   - **JSON-stdin & CLI (`src/driver/cli.py`)** в полном соответствии с матрицей приёмочных тестов из исходного плана.
3. **Захват картинок через контекст и рендер браузера:**
   - Скачивание в контексте сессии и снятие скриншотов элементов (`locator.screenshot()`), препроцессинг и OCR с честным fallback на `alt` / `ocr_failed`.

---

## Фазы и задачи (Статус: Выполнено 100%)

### Фаза 0 — Подготовка окружения и переносимость
- [x] `pyproject.toml`, `uv.lock`, `.gitignore`, скрипты `bootstrap.ps1` / `bootstrap.sh`.
- [x] Проверка/установка `playwright` (`chromium`), `tesseract` + `pytesseract` + `Pillow` (+ `rapidocr-onnxruntime` как переносимый движок).
- [x] Генерация `env.log` со списком версий окружения.
- **Тесты (`tests/test_phase0_env.py`):**
  - [x] `test_env_pwd`
  - [x] `test_playwright_launch`
  - [x] `test_tesseract_available`
  - [x] `test_playwright_screenshot`

### Фаза 1 — Сессия и артефакты
- [x] Структура `artifacts/<session>/<page>/` (`page.html`, `page.png`, `manifest.json`, `actions.log`, `page.diff`).
- [x] Конфигурация: `user_agent`, `viewport`, `timeout`, `ocr_langs`.
- [x] Сохранение и переиспользование состояния сессии (`storage_state.json`, cookies).
- **Тесты (`tests/test_phase1_session.py`):**
  - [x] `test_open_page_creates_dir`
  - [x] `test_manifest_fields`
  - [x] `test_screenshot_nonempty`
  - [x] `test_session_reuse`

### Фаза 2 — Читатель страницы (DOM: текст, ссылки, инвентарь картинок)
- [x] `read_text()`, `read_links()`, `read_images()`, `read_headings()`.
- [x] Снапшот дерева доступности (roles/labels) и очистка от `script`/`style`.
- **Тесты (`tests/test_phase2_reader.py`):**
  - [x] `test_read_links`
  - [x] `test_read_images_inventory`
  - [x] `test_read_headings`
  - [x] `test_text_blocks`

### Фаза 3 — Картинки: инвентарь + сохранение + препроцессинг + OCR
- [x] Пайплайн извлечения изображений (`images/img_N.png`), препроцессинг (resize, grayscale, autocontrast, adaptive binarize, margin) и распознавание текста.
- [x] Запись в `manifest.json`: `images[i] = {url, alt, size, file, ocr_text, conf, status}`.
- [x] Честный fallback: `alt` или пометка `ocr_failed`.
- **Тесты (`tests/test_phase3_ocr.py`):**
  - [x] `test_ocr_synthetic`
  - [x] `test_ocr_real_image`
  - [x] `test_inventory_has_all_images`
  - [x] `test_ocr_on_page_images`
  - [x] `test_ocr_preprocess`

### Фаза 4 — Активные элементы: маппинг selector → роль
- [x] `collect_actionables()` → `{id, role, label, value, selector, href}`.
- [x] Приоритет селекторов: `id` > `name` > `aria-label` > текст кнопки > стабильный `css-path` + `data-agb-id`.
- **Тесты (`tests/test_phase4_actionables.py`):**
  - [x] `test_collect_inputs`
  - [x] `test_button_text`
  - [x] `test_link_selector`
  - [x] `test_no_dupes`

### Фаза 5 — Заполнение полей
- [x] `fill(selector, value)`, `select(selector, option)`, `check(selector)` / `uncheck(selector)`.
- [x] Запись в `actions.log`: `{action, selector, value, before, after, ts}`.
- **Тесты (`tests/test_phase5_fill.py`):**
  - [x] `test_fill_text`
  - [x] `test_select`
  - [x] `test_checkbox`
  - [x] `test_actions_logged`

### Фаза 6 — Нажатия, клики и переходы
- [x] `click(selector)`, `press(key)`, `goto(url)`.
- [x] Пост-экшен снапшот: скриншот + HTML diff + фиксация смены URL/DOM.
- **Тесты (`tests/test_phase6_click.py`):**
  - [x] `test_click_navigates`
  - [x] `test_click_button_state`
  - [x] `test_press_enter`
  - [x] `test_action_logged`

### Фаза 7 — Протокол управления (stdin JSON + MCP Server)
- [x] Обработчик JSON-команд из `stdin`: `{op: open|fill|click|press|read|select|check, target, value, session, danger, confirm}`.
- [x] Ответ: `{ok, artifacts[], state, page, error, data}`.
- [x] MCP Server (`MCPServer`): инструменты `browser_open`, `browser_read`, `browser_fill`, `browser_select`, `browser_check`, `browser_click`, `browser_press`, `browser_close_session`.
- **Тесты (`tests/test_phase7_protocol.py`):**
  - [x] `test_protocol_roundtrip`
  - [x] `test_bad_action_rejected`
  - [x] `test_timeout`
  - [x] `test_artifact_chain`
  - [x] `test_mcp_tools`

### Фаза 8 — Состояние и мульти-страничность
- [x] Сохранение/загрузка `storage_state.json`, авторизованные сессии.
- [x] Мониторинг переходов (`html_hash`, `screenshot_hash`, `page.diff`, `session.log`).
- **Тесты (`tests/test_phase8_state.py`):**
  - [x] `test_login_persists`
  - [x] `test_multi_page_state`
  - [x] `test_state_after_click`

### Фаза 9 — Безопасность и границы
- [x] Блокировка неподтверждённых опасных операций (`danger: true` или деструктивные кнопки без `confirm: true`), allow-list доменов, лимиты действий (`max_actions`), таймауты.
- **Тесты (`tests/test_phase9_safety.py`):**
  - [x] `test_blocked_op`
  - [x] `test_limits`
  - [x] `test_timeout_cleanup`

### Фаза 10 — Упаковка репозитория, CLI и кросс-фазные тесты
- [x] Структура `src/driver/`, `tests/`, `fixtures/`, `config/`, `artifacts/` (gitignored), `scripts/`.
- [x] CLI: `run --url --session --actions file` + точка входа MCP-сервера `agenbro-mcp`.
- **Тесты (`tests/test_phase10_packaging.py`):**
  - [x] `test_repo_layout`
  - [x] `test_cli_smoke`
  - [x] `test_open_read_ocr`
  - [x] `test_fill_click_navigate`
  - [x] `test_suite_green`
