# AgenBroMCP — Portable Browser Driver & MCP Server

Browser automation driver and Model Context Protocol (MCP) server built on **Playwright (Chromium)** and **Tesseract OCR**.
Opens pages, extracts structured DOM content, captures/downloads images and runs OCR, maps interactive elements, fills forms, executes clicks/transitions, and writes deterministic audit artifacts (`page.html`, `page.png`, `page.diff`, `manifest.json`, `actions.log`, `storage_state.json`).

**Status:** Phases 0–11 complete — 46 tests green (`uv run pytest`). Full usage guide: [usage.md](usage.md).

---

## Quick Migration & Setup on Any Machine

### Windows (PowerShell)
```powershell
./scripts/bootstrap.ps1
uv run pytest -v
```

### Linux / macOS (Bash)
```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
uv run pytest -v
```

The bootstrap script automatically verifies/installs `uv`, portable `Tesseract-OCR` (including `eng` and `rus` language packs), syncs `.venv` from `pyproject.toml` / `uv.lock`, and installs Playwright Chromium.

---

## Running as an MCP Server

Entry point: `agenbro-mcp` (or `uv run python -m driver.mcp_server`).

Example MCP client configuration (`mcp_config.json`):
```json
{
  "mcpServers": {
    "agenbro": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Workarea/AgenBroMCP",
        "run",
        "agenbro-mcp"
      ]
    }
  }
}
```

### Exposed MCP Tools
- `browser_open(url, session="default")` — Open URL, capture HTML/PNG/OCR artifacts, return `manifest.json`.
- `browser_read(session="default")` — Extract headings, clean text blocks, links, image OCR inventory, and actionable elements.
- `browser_fill(selector, value, session="default")` — Fill input/textarea and log `before`/`after` values.
- `browser_select(selector, option, session="default")` — Select dropdown option.
- `browser_check(selector, checked=True, session="default")` — Check or uncheck checkbox/radio.
- `browser_click(selector, session="default", danger=False, confirm=False)` — Click button/link and record transition diff.
- `browser_press(key="Enter", selector=None, session="default")` — Press keyboard key and capture state transition.
- `browser_close_session(session="default")` — Save `storage_state.json` and close browser context.

---

## Running via CLI or JSON-stdin

Full command reference, action protocol schema, response format, and safety flags: see [usage.md](usage.md).

### CLI Batch Mode
```powershell
uv run agenbro-cli run --url "https://example.com" --session "demo" --actions actions.jsonl
```

### External Chrome (CDP Connect Mode)
```powershell
# Chrome with a debug port and a persistent profile (log in once — the login is kept)
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\ChromeAgenBro'

uv run agenbro-cli run --cdp http://127.0.0.1:9222 --session chrome --actions actions.jsonl
```

### Interactive / Stdin Stream Mode
```powershell
'{"op":"open","target":"https://example.com","session":"demo"}' | uv run agenbro-cli
```

---

## Live Smoke Test (google.com, Nov 17, 2026)

`open https://www.google.com` → `fill input[name="q"] = "what is going on?"` → `press Enter` → `read`: the driver recorded the fill (`before=""` / `after="what is going on?"`), captured the transition to a second page snapshot, and read the structured content. Google redirected headless automation to its anti-bot `google.com/sorry` CAPTCHA wall (DDG `html` endpoint likewise serves its own error page); the same pipeline against Bing returned the full extracted search results. The wall is the site's bot defense, faithfully logged in the artifacts. Use `headless: false` + realistic `user_agent` to reduce blocking.

---

## Repository Structure
- `src/driver/` — Core library (`config.py`, `env_check.py`, `ocr.py`, `reader.py`, `safety.py`, `session.py`, `protocol.py`, `cli.py`, `mcp_server.py`)
- `config/default.json` — Default driver and safety parameters
- `usage.md` — Full usage guide (CLI, JSON protocol, MCP, artifacts, config, safety)
- `fixtures/` — Offline HTML and PNG fixtures for deterministic testing
- `tests/` — Phase 0–10 + Cross-Phase Acceptance test suite
- `scripts/` — Cross-platform bootstrap scripts (`bootstrap.ps1`, `bootstrap.sh`)
- `artifacts/` — Runtime session snapshots and logs (gitignored)
