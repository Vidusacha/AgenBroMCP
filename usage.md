# AgenBroMCP — Usage Guide

Detailed guide for the CLI, the JSON action protocol, the MCP server, artifacts, configuration, and safety model. Overview and setup: see [readme.md](readme.md).

---

## 1. Installation

```powershell
# Windows
./scripts/bootstrap.ps1        # uv + Tesseract-OCR (eng+rus) + venv + Playwright Chromium
uv run pytest -v               # 45 tests, phases 0–10 + cross-phase
```

```bash
# Linux / macOS
./scripts/bootstrap.sh
uv run pytest -v
```

The bootstrap script installs `uv` (if missing), portable Tesseract-OCR with `rus.traineddata`, syncs `.venv` from `pyproject.toml`/`uv.lock`, and installs the Playwright Chromium browser. Tesseract is optional at runtime: the driver falls back to `rapidocr-onnxruntime` (pure-Python, works right after `uv sync`).

Entry points (installed by `uv sync` as console scripts):
- `agenbro-cli` — CLI / JSON-stdin runner
- `agenbro-mcp` — MCP stdio server

---

## 2. CLI

### Batch mode (actions file)
```powershell
uv run agenbro-cli run --url "https://www.google.com" --session "demo" --actions actions.jsonl
```
- `--url` adds a leading `open` command; `--actions` accepts a **JSON array** file (`[{...}, {...}]`) or **JSONL** (one JSON object per line).
- `--session` sets the default session id for commands without an explicit `session`.
- Every command prints one JSON response line to stdout, in execution order.
- `--artifacts-dir <path>` overrides the artifacts output directory; `--config <path>` loads an alternative config.
- `--cdp <url>` drives an **external Chrome** over CDP (see below).

### External Chrome (CDP connect mode)
Start Chrome with a debug port and a persistent profile — its cookies, logins and extensions are used by the driver, and the profile stays across runs (login once, it is kept):
```powershell
# one-time setup: log in to everything you use inside this profile
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\ChromeAgenBro'

uv run agenbro-cli run --cdp http://127.0.0.1:9222 --session chrome --actions actions.jsonl
```
The session adopts the first existing tab of that Chrome. In connect mode `headless`, `user_agent` and `viewport` are ignored (real browser fingerprint), `storage_state` export is skipped (the profile itself is the persistent store), and closing the session disconnects from Chrome without closing it. Config-file key `cdp_url` is equivalent to `--cdp`. URL allowlist and action limits apply as usual.

### Stream mode (stdin)
```powershell
'{"op":"open","target":"https://example.com","session":"demo"}' | uv run agenbro-cli
```
When no `--url` / `--actions` are given, commands are read from stdin (JSON array, JSONL, or a JSON object per line) and executed against a shared session pool.

### Typical search-flow example (google.com)
`actions.jsonl`:
```jsonl
{"op":"open","target":"https://www.google.com","session":"googletest"}
{"op":"fill","target":"input[name=\"q\"]","value":"what is going on?","session":"googletest"}
{"op":"press","target":"input[name=\"q\"]","value":"Enter","session":"googletest"}
{"op":"read","session":"googletest"}
```
```powershell
uv run agenbro-cli run --actions actions.jsonl
```
Real run (Nov 17, 2026): `open` → Google homepage, `fill` → input value recorded (`before:""`, `after:"what is going on?"`), `press Enter` → navigation, `read` → structured content of the new page. All artifacts were written. Note: headless automation from datacenter/automated IPs hits anti-bot walls — Google redirected to `google.com/sorry` (CAPTCHA), DDG `html` endpoint returns its own error page. Bing (`https://www.bing.com/search?q=...`) returned full extracted search results. This is a property of the target site's bot defenses, not a driver failure: the driver captured every transition with artifacts. To reduce blocking use `headless: false`, a realistic `user_agent`, and a residential IP.

---

## 3. JSON action protocol

### Command format
```json
{"op": "<op>", "target": "<url|selector>", "value": "<value|key>",
 "session": "demo", "danger": false, "confirm": false, "timeout_ms": 10000}
```

| Field | Meaning |
|---|---|
| `op` | Operation: `open`, `goto`, `read`, `fill`, `select`, `check`, `uncheck`, `click`, `press` |
| `target` | URL for `open`/`goto`; CSS selector for `fill`/`select`/`check`/`uncheck`/`click`/`press` (aliases: `selector`, `url`) |
| `value` | Text for `fill`/`select`; checked state for `check`; key for `press` (`target`+`value` = press key on focused element, `value` alone = press key on page) |
| `session` | Session id; state, cookies, artifacts are per session (`storage_state.json` is reused across runs) |
| `danger` / `confirm` | Safety flags (see §6) |
| `timeout_ms` | Optional per-command Playwright timeout override |

### Operations

| op | target | value | Effect |
|---|---|---|---|
| `open` | URL | — | Navigate, snapshot page (`page.html`, `page.png`), run OCR on page images |
| `goto` | URL | — | Same as `open` |
| `read` | — | — | Structured extraction of the current page |
| `fill` | selector | text | Fill input/textarea, log `before`/`after` |
| `select` | selector | option | Pick a `<select>` option |
| `check` | selector | bool | Check (default true) a checkbox/radio |
| `uncheck` | selector | — | Uncheck |
| `click` | selector | — | Click, record transition diff (`page.diff`, new `page_id`) |
| `press` | selector | key | Focus the element and press `key`; key alone presses on the focused element |

### Response format
Every command returns one JSON object:
```json
{
  "ok": true,
  "op": "fill",
  "session": "googletest",
  "artifacts": ["...page.html", "...page.png", "...manifest.json", "...actions.log", "...page.diff"],
  "state": {"session": "googletest", "url": "https://...", "page_id": "page_002_...", "html_hash": "sha256...", "action_count": 3},
  "page": "page_002_www_google_com",
  "data": { ... },
  "error": null
}
```

`data` for `read`:
```json
{
  "url": "...", "title": "...",
  "screenshot": "...page.png", "html_path": "...page.html", "diff_path": "...page.diff",
  "html_hash": "...", "html_changed": true,
  "headings":    [{"tag": "h2", "level": 2, "text": "..."}],
  "text_blocks": ["..."],          // cleaned text, script/style removed
  "links":       [{"text": "...", "href": "..."}],
  "images":      [{"url": "...", "alt": "...", "size": [w,h], "file": "images/img_1.png", "ocr_text": "...", "conf": 85.0, "status": "ok"}],
  "actionables": [{"id": "act_1", "role": "textbox", "label": "Search", "value": "...", "selector": "input[name=\"q\"]", "href": null}]
}
```

`data` for actions (`fill`/`click`/`press`/...): `action`, `selector`, `value`, `before`/`after` (value for fill; URL before/after for navigation), `html_changed`, `html_hash_after`.

### Selectors
`read` returns ready-to-use `actionables[].selector` ordered by stability: element `id` > `name` attribute > `aria-label` > visible button text > generated CSS path (plus a `data-agb-id` marker). Use those selectors verbatim in `fill`/`click` commands.

---

## 4. MCP server

Start via stdio from any MCP client (`mcp_config.json`):
```json
{
  "mcpServers": {
    "agenbro": {
      "command": "uv",
      "args": ["--directory", "D:/Workarea/AgenBroMCP", "run", "agenbro-mcp"]
    }
  }
}
```

Tools:
| Tool | Args | Maps to op |
|---|---|---|
| `browser_open` | `url`, `session` | `open` |
| `browser_read` | `session` | `read` |
| `browser_fill` | `selector`, `value`, `session` | `fill` |
| `browser_select` | `selector`, `option`, `session` | `select` |
| `browser_check` | `selector`, `checked`, `session` | `check` |
| `browser_click` | `selector`, `session`, `danger`, `confirm` | `click` |
| `browser_press` | `key`, `selector`, `session` | `press` |
| `browser_close_session` | `session` | saves `storage_state.json`, closes context |

---

## 5. Artifacts layout

```
artifacts/<session>/
  actions.log              # session-wide action log (JSONL)
  session.log              # state transition log
  storage_state.json       # cookies + localStorage, reused on next start
  page_001_<url-slug>/
    page.html              # captured DOM
    page.png               # viewport screenshot
    manifest.json          # url, title, hashes, screenshot_hash, images[] inventory + OCR
    page.diff              # unified HTML diff vs. previous page snapshot
    actions.log            # actions recorded on this page
    images/img_N.png       # extracted page images (OCR sources)
```
`page_id` = `page_NNN_<domain+path slug>`, numbering is sequential per session. Every action appends to the log, and the response `artifacts[]` lists the exact files written.

---

## 6. Safety model

- **Destructive guard:** a command with `danger: true` is blocked unless `confirm: true`. Clicks on elements whose text/selector matches destructive keywords (EN: `delete`, `remove`, `destroy`, `drop`, `pay`, `purchase`, `buy now`, `checkout`, `wipe`; RU: `удалить`, `оплатить`, `купить`) are blocked without `confirm: true`.
- **URL scheme allowlist:** only `http`, `https`, `file`, `data`, `about` schemes.
- **Domain allowlist:** set `allowed_domains` in `config/default.json` (empty = all domains allowed).
- **Limits:** `max_actions`, `max_screenshots`, `max_downloads` per session; exceeding them raises an action-limit error.
- Timeouts: `timeout_ms` globally, per command via `timeout_ms`.

---

## 7. Configuration (`config/default.json`)

```json
{
  "user_agent": "AgenBroMCP/0.1.0 (Playwright; Chromium)",
  "viewport_width": 1280, "viewport_height": 800,
  "timeout_ms": 10000,
  "ocr_langs": "eng+rus", "ocr_min_conf": 50.0,
  "min_screenshot_bytes": 500,
  "max_actions": 50, "max_screenshots": 100, "max_downloads": 100,
  "headless": true,
  "allowed_domains": []
}
```
- `headless: false` shows the browser window (recommended for interactive work and to reduce anti-bot blocking).
- Tesseract binary is auto-detected: `TESSERACT_CMD` env var → PATH → standard Windows/Linux/macOS install locations; `TESSDATA_PREFIX` is set automatically. If Tesseract is unavailable the driver falls back to RapidOCR.
- `--config <path>` (CLI) loads an alternative config file.
- `"cdp_url": "http://127.0.0.1:9222"` in the config file connects to an external Chrome (equivalent to `--cdp`); `null` keeps the default managed-Chromium mode.

---

## 8. Sessions & persistence

- Sessions are keyed by `session` name; each has its own artifacts folder and `storage_state.json`.
- On start, a session loads its stored `storage_state.json` (cookies, localStorage) → authenticated state persists between CLI runs and MCP server restarts.
- In CDP connect mode the persistent store is the Chrome `--user-data-dir` profile itself: log in once inside it, the login is kept for all future AgenBroMCP runs; `storage_state.json` export is skipped.
- `browser_close_session` / CLI pool shutdown saves the state automatically.

---

## 9. Testing

```powershell
uv run pytest -v
```
45 tests cover phases 0–10 (env, session/artifacts, DOM reader, image+OCR pipeline, actionables mapping, fill, click/press/navigate, JSON protocol + MCP tools, storage state, safety limits, packaging + CLI smoke + cross-phase acceptance) against offline fixtures (`fixtures/*.html`, `*.png`), fully deterministic and offline.
