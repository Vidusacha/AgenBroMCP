"""Phase 8 tests: State persistence across sessions, multi-page diffing, and HTML hashes."""

from __future__ import annotations

import json
from pathlib import Path

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_login_persists(test_server_url: str, temp_config: DriverConfig) -> None:
    """Filling login form and clicking submit saves storage_state; next BrowserDriver instance is authenticated."""
    with BrowserDriver(session_id="p8_auth", config=temp_config) as drv1:
        drv1.open_page(f"{test_server_url}/login.html", run_ocr=False)
        drv1.fill("#user-field", "ev_admin")
        drv1.fill("#pass-field", "secret123")
        drv1.click("#login-btn")
        assert "Welcome Authenticated User" in drv1.page.content()
        assert drv1.storage_state_path.is_file()

    # Open a brand new BrowserDriver instance with the same session_id
    with BrowserDriver(session_id="p8_auth", config=temp_config) as drv2:
        drv2.open_page(f"{test_server_url}/dashboard", run_ocr=False)
        content = drv2.page.content()
        assert "Welcome Authenticated User" in content
        assert "session_user=ev_admin" in content


def test_multi_page_state(test_server_url: str, temp_config: DriverConfig) -> None:
    """Navigating across 3 pages records diff and state log for each page."""
    with BrowserDriver(session_id="p8_multi", config=temp_config) as drv:
        m1 = drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        m2 = drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        m3 = drv.open_page(f"{test_server_url}/next.html", run_ocr=False)

        assert Path(m1["diff_path"]).is_file()
        assert Path(m2["diff_path"]).is_file()
        assert Path(m3["diff_path"]).is_file()

        state_lines = [
            json.loads(line)
            for line in drv.session_state_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(state_lines) == 3
        assert state_lines[0]["html_hash"] != state_lines[1]["html_hash"]
        assert state_lines[1]["html_hash"] != state_lines[2]["html_hash"]


def test_state_after_click(test_server_url: str, temp_config: DriverConfig) -> None:
    """HTML hash changes after clicking an interactive button and is recorded in session.log."""
    with BrowserDriver(session_id="p8_click_hash", config=temp_config) as drv:
        m_before = drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        res_click = drv.click("#toggle-btn")
        assert m_before["html_hash"] == res_click["html_hash_before"]
        assert res_click["html_hash_before"] != res_click["html_hash_after"]
