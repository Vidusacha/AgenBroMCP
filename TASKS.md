# AgenBroMCP — План разработки и задачи (Development Backlog)

Цель проекта: переносимый драйвер браузера и MCP-сервер (с поддержкой JSON-stdin и CLI), который открывает страницы, извлекает структурированный контент из DOM, распознаёт текст на картинках через OCR, заполняет формы и выполняет клики/переходы с полной записью артефактов и защитой от опасных действий.

---

## Архитектурные принципы и переносимость
1. **Кроссплатформенность (Windows / Linux / macOS):**
   - Все пути строятся через `pathlib.Path`.
   - Зависимости фиксируются в `pyproject.toml` и `uv.lock` / `requirements.txt` + скрипт быстрой инициализации на новой машине (`scripts/bootstrap.ps1` и `scripts/bootstrap.sh`).
   - Поддержка OCR: `tesseract` (с автоопределением пути на Windows/Linux) + встроенный portable-fallback через `rapidocr-onnxruntime` (работает без системных бинарников сразу после `pip install`).
2. **Двойной интерфейс:**
   - **MCP Server (`stdio`)** на базе официального `mcp` SDK (`FastMCP`).
   - **JSON-stdin & CLI (`src/driver/cli.py`)** в полном соответствии с матрицей приёмочных тестов из исходного плана.
3. **Захват картинок через рендер браузера:**
   - Снятие скриншотов элементов (`locator.screenshot()`) с fallback на сетевое скачивание в контексте сессии, фильтрация трекинг-пикселей и мелких иконок.

---

## Фазы и задачи

### Фаза 0 — Подготовка окружения и переносимость
- [ ] `pyproject.toml`, `.gitignore`, скрипты `bootstrap.ps1` / `bootstrap.sh`.
- [ ] Проверка/установка `playwright` (`chromium`), `tesseract` + `pytesseract` + `Pillow` (+ `rapidocr-onnxruntime` как переносимый движок).
- [ ] Генерация `env.log` со списком версий окружения.
- **Тесты (`tests/test_phase0_env.py`):**
  - `test_env_pwd`
  - `test_playwright_launch`
  - `test_tesseract_available`
  - `test_playwright_screenshot`

### Фаза 1 — Сессия и артефакты
- [ ] Структура `artifacts/<session>/<page>/` (`page.html`, `page.png`, `manifest.json`, `actions.log`).
- [ ] Конфигурация: `user_agent`, `viewport`, `timeout`, `ocr_langs`.
- [ ] Сохранение и переиспользование состояния сессии (`storage_state.json`, cookies).
- **Тесты (`tests/test_phase1_session.py`):**
  - `test_open_page_creates_dir`
  - `test_manifest_fields`
  - `test_screenshot_nonempty`
  - `test_session_reuse`

### Фаза 2 — Читатель страницы (DOM: текст, ссылки, инвентарь картинок)
- [ ] `read_text()`, `read_links()`, `read_images()`, `read_headings()`.
- [ ] Снапшот дерева доступности (accessibility roles/labels) и очистка от `script`/`style`.
- **Тесты (`tests/test_phase2_reader.py`):**
  - `test_read_links`
  - `test_read_images_inventory`
  - `test_read_headings`
  - `test_text_blocks`

### Фаза 3 — Картинки: инвентарь + сохранение + препроцессинг + OCR
- [ ] Пайплайн извлечения изображений (`images/img_N.png`), препроцессинг (resize, grayscale, adaptive threshold/contrast) и распознавание текста.
- [ ] Запись в `manifest.json`: `images[i] = {url, alt, size, file, ocr_text, conf}`.
- [ ] Честный fallback: `alt` или пометка `ocr_failed`.
- **Тесты (`tests/test_phase3_ocr.py`):**
  - `test_ocr_synthetic`
  - `test_ocr_real_image`
  - `test_inventory_has_all_images`
  - `test_ocr_on_page_images`
  - `test_ocr_preprocess`

### Фаза 4 — Активные элементы: маппинг selector → роль
- [ ] `collect_actionables()` → `{id, role, label, value, selector, href}`.
- [ ] Приоритет селекторов: `id` > `name` > `aria-label` > текст кнопки > стабильный `css-path` / `data-agb-id`.
- **Тесты (`tests/test_phase4_actionables.py`):**
  - `test_collect_inputs`
  - `test_button_text`
  - `test_link_selector`
  - `test_no_dupes`

### Фаза 5 — Заполнение полей
- [ ] `fill(selector, value)`, `select(selector, option)`, `check(selector)` / `uncheck(selector)`.
- [ ] Запись в `actions.log`: `{action, selector, value, before, after, ts}`.
- **Тесты (`tests/test_phase5_fill.py`):**
  - `test_fill_text`
  - `test_select`
  - `test_checkbox`
  - `test_actions_logged`

### Фаза 6 — Нажатия, клики и переходы
- [ ] `click(selector)`, `press(key)`, `goto(url)`.
- [ ] Пост-экшен снапшот: скриншот + HTML diff + фиксация смены URL/DOM.
- **Тесты (`tests/test_phase6_click.py`):**
  - `test_click_navigates`
  - `test_click_button_state`
  - `test_press_enter`
  - `test_action_logged`

### Фаза 7 — Протокол управления (stdin JSON + MCP Server)
- [ ] Обработчик JSON-команд из `stdin`: `{op: open|fill|click|press|read|select|check, target, value, session, danger, confirm}`.
- [ ] Ответ: `{ok, artifacts[], state, page, error}`.
- [ ] MCP Server (`FastMCP`): инструменты `browser_open`, `browser_read`, `browser_fill`, `browser_select`, `browser_check`, `browser_click`, `browser_press`.
- **Тесты (`tests/test_phase7_protocol.py`):**
  - `test_protocol_roundtrip`
  - `test_bad_action_rejected`
  - `test_timeout`
  - `test_artifact_chain`
  - `test_mcp_tools_execution`

### Фаза 8 — Состояние и мульти-страничность
- [ ] Сохранение/загрузка `storage_state`, авторизованные сессии.
- [ ] Мониторинг переходов (`html_hash`, `screenshot`, `page_diff`).
- **Тесты (`tests/test_phase8_state.py`):**
  - `test_login_persists`
  - `test_multi_page_state`
  - `test_state_after_click`

### Фаза 9 — Безопасность и границы
- [ ] Блокировка неподтверждённых опасных операций (`danger: true` или деструктивные кнопки без `confirm: true`), allow-list доменов, лимиты действий (`max_actions`), таймауты.
- **Тесты (`tests/test_phase9_safety.py`):**
  - `test_blocked_op`
  - `test_limits`
  - `test_timeout_cleanup`

### Фаза 10 — Упаковка репозитория, CLI и кросс-фазные тесты
- [ ] Структура `src/driver/`, `tests/`, `fixtures/`, `config/`, `artifacts/` (gitignored).
- [ ] CLI: `run --url --session --actions file` + точка входа MCP-сервера.
- **Тесты (`tests/test_phase10_packaging.py` & `tests/test_acceptance_matrix.py`):**
  - `test_repo_layout`
  - `test_cli_smoke`
  - `test_suite_green`
  - Полная матрица кросс-фазных приёмочных тестов (`test_open_read_ocr`, `test_fill_click_navigate` и др.).
