"""Phase 6 tests: Clicking links/buttons, pressing Enter, and recording transition artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_click_navigates(test_server_url: str, temp_config: DriverConfig) -> None:
    """Clicking a navigation link changes URL and records screenshot and HTML diff."""
    with BrowserDriver(session_id="p6_nav", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        res = drv.click("#link-next")
        assert res["url_before"].endswith("/index.html")
        assert res["url_after"].endswith("/next.html")
        assert res["html_changed"] is True

        manifest = res["manifest"]
        assert Path(manifest["screenshot"]).is_file()
        assert Path(manifest["diff_path"]).is_file()
        assert Path(manifest["diff_path"]).stat().st_size > 0


def test_click_button_state(test_server_url: str, temp_config: DriverConfig) -> None:
    """Clicking a toggle button changes DOM state (text) and records it in HTML diff/hash."""
    with BrowserDriver(session_id="p6_toggle", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        res = drv.click("#toggle-btn")
        assert res["html_changed"] is True
        assert res["html_hash_before"] != res["html_hash_after"]
        assert drv.page.locator("#toggle-status").inner_text() == "STATE_ON"
        diff_content = Path(res["manifest"]["diff_path"]).read_text(encoding="utf-8")
        assert "STATE_ON" in diff_content


def test_press_enter(test_server_url: str, temp_config: DriverConfig) -> None:
    """Submitting a form via pressing Enter on an input changes URL/state."""
    with BrowserDriver(session_id="p6_enter", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        drv.fill("#search-input", "agenbro_query")
        res = drv.press("Enter", selector="#search-input")
        assert "next.html" in res["url_after"]
        assert "q=agenbro_query" in res["url_after"]


def test_action_logged(test_server_url: str, temp_config: DriverConfig) -> None:
    """actions.log contains click record with before and after URLs."""
    with BrowserDriver(session_id="p6_log", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        drv.click("#nav-next")

        entries = [
            json.loads(line)
            for line in drv.session_actions_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        click_entries = [e for e in entries if e["action"] == "click"]
        assert len(click_entries) == 1
        assert click_entries[0]["before"].endswith("/forms.html")
        assert click_entries[0]["after"].endswith("/next.html")
