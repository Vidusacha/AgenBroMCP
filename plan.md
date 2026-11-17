# Разработка драйвера браузера и MCP-сервера: пошаговый план с тестами

Цель: переносимый драйвер и MCP-сервер, который открывает страницу, читает её (включая картинки через OCR), заполняет формы/поля и нажимает на активные элементы/ссылки. Все артефакты (HTML, скриншоты, скачанные изображения, OCR-манифест, лог действий) пишутся в заданную директорию.

- Рабочая директория: корень репозитория (`AgenBroMCP`), пути разрешаются динамически через `pathlib.Path` (полная переносимость между Windows и Linux/macOS).
- Честное ограничение агента: драйвер извлекает текст из пикселей через OCR (`tesseract` + `rapidocr` fallback) и формирует манифест картинок (`url`, `alt`, `size`, `file`, `ocr_text`, `conf`).
- Контроль = два режима:
  1. **MCP Server (`stdio`)** — стандартные MCP-инструменты для подключения к любому MCP-клиенту.
  2. **JSON-действия через `stdin` / CLI** — драйвер исполняет команды → пишет артефакты → возвращает JSON-ответ.

## Фаза 0 — подготовка окружения (предподшаги)
Цель: установить и проверить Playwright, браузер, OCR-тулчейн. Обеспечить простую миграцию на другую машину через `uv` и bootstrap-скрипты.
- [x] `playwright` (python) + `playwright install chromium`
- [x] `tesseract` (системный с автопоиском пути на Windows/Linux) + `pytesseract` + `Pillow` + `rapidocr-onnxruntime` (portable fallback)
- [x] зафиксировать корневую директорию проекта, создать структуру артефактов
- Тесты:
  - `test_env_pwd`: проверка рабочей директории и структуры проекта.
  - `test_playwright_launch`: headless-запуск chromium, открыта `about:blank`, скриншот не пустой (>0 байт).
  - `test_tesseract_available`: `tesseract --version` даёт выход; `pytesseract.image_to_string` на синтетическом PNG (PIL, текст «HELLO») возвращает строку с `HELLO`.
  - `test_playwright_screenshot`: скриншот страницы = PNG, размер > порога.
- Acceptance: все 4 теста зелёные; список установленных версий записан в `env.log`.

## Фаза 1 — сессия и артефакты
Цель: стабильная сессия, папки артефактов, именованный снапшот на каждую страницу.
- [ ] структура: `artifacts/<session>/<page>/` (`page.html`, `page.png`, `manifest.json`, `actions.log`)
- [ ] config: `user-agent`, `viewport`, `timeout`, `languages OCR`
- [ ] запуск/закрытие сессии, `cookie`/`storage_state` persistence
- Тесты:
  - `test_open_page_creates_dir`: открыть тестовую страницу → создаётся каталог, в нём `page.html`, `page.png`, `manifest.json`.
  - `test_manifest_fields`: manifest содержит `url`, `title`, `screenshot`, `html_path`, `ts`.
  - `test_screenshot_nonempty`: скриншот декодируется PIL, non-zero size.
  - `test_session_reuse`: две страницы в одной сессии; cookies/заголовок сохранены.
- Acceptance: артефакты всегда на месте; нет «голой» страницы без снапшота.

## Фаза 2 — читатель страницы (текст, ссылки, список картинок)
Цель: из DOM извлечь структурированный контент: заголовки, текст, ссылки, список картинок (URL, alt, role).
- [ ] `read_text()`, `read_links()`, `read_images()`, `read_headings()`
- [ ] accessibility-tree snapshot (roles, labels) — для маппинга элементов
- Тесты:
  - `test_read_links`: на странице с 2 известными ссылками возвращены 2 объекта с `href`+`text`.
  - `test_read_images_inventory`: на странице с `<img>` (`alt="logo"`) inventory содержит URL, alt, natural size.
  - `test_read_headings`: `h1`/`h2` извлечены по порядку.
  - `test_text_blocks`: извлечён непрерывный текст `body` без `script`/`style` шума.
- Acceptance: reader не выдумывает; всё из DOM, ничего «по памяти».

## Фаза 3 — картинки: инвентарь + скачивание + OCR
Цель: каждую картинку страницы → инвентарь → сохранить → OCR → текст в манифесте.
- [ ] download/capture pipeline: захват картинки → save PNG → preprocess (resize, grayscale, binarize/contrast) → tesseract lang
- [ ] OCR-запись: `manifest.images[i] = {url, alt, size, file, ocr_text, conf}`
- [ ] fallback: если OCR пусто → `alt`/подпись; если `alt` пусто → пометка `ocr_failed`
- Тесты:
  - `test_ocr_synthetic`: PIL PNG с текстом «ABC123» → tesseract вернёт строку, содержащую `ABC123` (порог conf).
  - `test_ocr_real_image`: скачанная картинка с известным текстом (fixture) → OCR содержит контрольную строку.
  - `test_inventory_has_all_images`: число картинок в inventory == число `<img>` в DOM.
  - `test_ocr_on_page_images`: после `open_page` `manifest.images` содержит `ocr_text` для каждой картинки.
  - `test_ocr_preprocess`: препроцессинг на низкоконтрастной/мелкой картинке повышает `conf` vs raw.
- Acceptance: каждая картинка = инвентарь + файл + OCR-текст (или честный `ocr_failed`). Ничего не «выдумано».

## Фаза 4 — активные элементы: маппинг selector → роль
Цель: единый реестр интерактивных элементов: `input`, `select`, `checkbox`, `radio`, `button`, `link`, с `label`/`name`/`accessible-name`.
- [ ] `collect_actionables()` → `{id, role, label, value, selector, href}`
- [ ] приоритет selector: `id` > `name` > `aria-label` > текст кнопки > `css-path` (стабильный) + `data-agb-id`
- Тесты:
  - `test_collect_inputs`: на fixture-форме собраны все `<input>` с `label`.
  - `test_button_text`: кнопка «Submit» имеет `text="Submit"`.
  - `test_link_selector`: каждая `<a>` маппится в actionables с `href`.
  - `test_no_dupes`: один DOM-элемент = один actionable id.
- Acceptance: реестр полный и детерминированный; нет «призраков».

## Фаза 5 — заполнение полей
Цель: fill inputs, select options, toggle checkbox/radio; проверка DOM post-fill.
- [ ] `fill(selector, value)`, `select(selector, option)`, `check/uncheck`
- [ ] записать в `actions.log`: `{action, selector, value, before, after}`
- Тесты:
  - `test_fill_text`: `input name="q"` → `value="hello"` → DOM `value == "hello"`.
  - `test_select`: `select` → `value ==` выбранной опции.
  - `test_checkbox`: `checkbox` → `checked == true`; `actions.log`.
  - `test_actions_logged`: `actions.log` содержит запись `fill` с `before`/`after`.
- Acceptance: каждая fill/selection имеет лог с `before`/`after`; нет «заполнено молча».

## Фаза 6 — нажатие/клики/ссылки
Цель: click button/link, press Enter; фиксация state-перехода.
- [ ] `click(selector)`, `press(key)`, `goto(url)`
- [ ] post-action snapshot: screenshot + html diff + url
- Тесты:
  - `test_click_navigates`: клик по ссылке меняет `url`; скриншот и html-диф записаны.
  - `test_click_button_state`: кнопка-переключатель меняет DOM-состояние (`checked`/`text`), зафиксировано в diff.
  - `test_press_enter`: form submit через `Enter` → `url`/state change.
  - `test_action_logged`: `actions.log` содержит `click` с `before`/`after` `url`.
- Acceptance: каждый клик даёт артефакт перехода; нет «клика в пустоту».

## Фаза 7 — протокол управления (stdin JSON + MCP Server)
Цель: агент подаёт действия через `stdin` или вызывает MCP-инструменты; драйвер исполняет, пишет артефакты; агент читает и решает.
- [ ] JSON-schema действий: `{op: open|fill|click|press|read|select|check, target, value, session}`
- [ ] результат: `{ok, artifacts[], state, page}`
- [ ] MCP Server (`stdio`) с тулами `browser_open`, `browser_read`, `browser_fill`, `browser_select`, `browser_check`, `browser_click`, `browser_press`
- [ ] ошибки/таймауты/валидация
- Тесты:
  - `test_protocol_roundtrip`: `open→read→fill→click` pipeline через `stdin` даёт корректную цепочку артефактов.
  - `test_bad_action_rejected`: `{op:"teleport"}` → `{ok:false, error}` без изменения состояния.
  - `test_timeout`: зависший page → timeout-результат, не зависание процесса.
  - `test_artifact_chain`: после `fill+click` `manifest` и `actions.log` связаны через `session`/`page` id.
  - `test_mcp_tools`: вызов инструментов MCP-сервера возвращает валидный результат и создаёт артефакты.
- Acceptance: весь пайплайн `open→read(с OCR)→fill→click` проходит через `stdin` и MCP без ручного кода.

## Фаза 8 — состояние и мульти-страниц
Цель: cookies, storage, логин, навигация между страницами, diff-мониторинг состояния.
- [ ] save/load `storage_state`
- [ ] page-diff: hash html + screenshot, записывать в session-лог
- Тесты:
  - `test_login_persists`: fill login+password → click → `storage_state` сохранён; следующая сессия = авторизована.
  - `test_multi_page_state`: 3 страницы, diff записан для каждой.
  - `test_state_after_click`: html-хеш меняется после клика, зафиксирован.
- Acceptance: состояние трассируется; нет «потерянных» переходов.

## Фаза 9 — безопасность и границы
Цель: не выполнять деструктивных/опасных действий, лимиты, подтверждения.
- [ ] allow-list доменов; лимит действий; запрет destructive submit/click без флага подтверждения
- [ ] таймауты: click/fill/navigate; max screenshots; max downloads
- Тесты:
  - `test_blocked_op`: action с `{danger:true}` или клик по опасной кнопке без подтверждения → `{ok:false}`.
  - `test_limits`: превышение лимита действий → ошибка, не зависание.
  - `test_timeout_cleanup`: таймаут → процесс не виснет, артефакт записан.
- Acceptance: опасные/неподтверждённые действия блокируются; лимиты соблюдены.

## Фаза 10 — упаковка в репозиторий
Цель: layout в целевом repo, конфиг, CLI, MCP-сервер, тесты, документация и скрипты миграции.
- [ ] `src/driver/`, `tests/`, `fixtures/`, `config/`, `artifacts/` (gitignored), `scripts/`
- [ ] CLI: `run --url --session --actions file` и MCP entry point `agenbro-mcp`
- [ ] CI/локальный прогон полного тест-сьюта
- Тесты:
  - `test_repo_layout`: файлы по структуре присутствуют.
  - `test_cli_smoke`: CLI открывает fixture-страницу, пишет артефакты.
  - `test_suite_green`: pytest-набор фаз 0–9 зелёный.
- Acceptance: репозиторий самодостаточен и готов к переносу на другую машину; тесты = контракт; артефакты воспроизводимы.

## Матрица acceptance-тестов (кросс-фазный)
| Сценарий | Фаза | Тест | Ожидаемый результат |
|---|---|---|---|
| Открыть → читал (текст+картинки+OCR) | 1,2,3 | `test_open_read_ocr` | `manifest.images` содержит `ocr_text`; reader вернул `links` |
| Открыть → fill → click → переход | 5,6,7 | `test_fill_click_navigate` | `actions.log`: `fill`+`click`; `url` изменился; скриншот+html diff |
| OCR картинок страницы | 3 | `test_ocr_real_image` | контрольная строка найдена в OCR |
| Заполнение с логом | 5 | `test_actions_logged` | `before`/`after` записаны |
| Клик даёт артефакт перехода | 6 | `test_click_navigates` | `url`+state diff |
| Протокол round-trip | 7 | `test_protocol_roundtrip` | `open→read→fill→click` через `stdin` |
| Опасное действие | 9 | `test_blocked_op` | `{ok:false}` |
