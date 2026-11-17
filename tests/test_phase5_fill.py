"""Phase 5 tests: Filling inputs, selecting options, toggling checkboxes, and logging before/after."""

from __future__ import annotations

import json

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_fill_text(test_server_url: str, temp_config: DriverConfig) -> None:
    """Filling input name='q' sets DOM value == 'hello'."""
    with BrowserDriver(session_id="p5_fill", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        res = drv.fill('input[name="q"]', "hello")
        assert res["before"] == ""
        assert res["after"] == "hello"
        dom_val = drv.page.locator('input[name="q"]').input_value()
        assert dom_val == "hello"


def test_select(test_server_url: str, temp_config: DriverConfig) -> None:
    """Selecting option 'admin' updates select DOM value to 'admin'."""
    with BrowserDriver(session_id="p5_select", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        res = drv.select("#role-select", "admin")
        assert res["before"] == "guest"
        assert res["after"] == "admin"
        assert drv.page.locator("#role-select").input_value() == "admin"


def test_checkbox(test_server_url: str, temp_config: DriverConfig) -> None:
    """Checking checkbox updates checked state to True and logs in actions.log."""
    with BrowserDriver(session_id="p5_check", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        res = drv.check("#agree-check")
        assert res["before"] is False
        assert res["after"] is True
        assert drv.page.locator("#agree-check").is_checked() is True


def test_actions_logged(test_server_url: str, temp_config: DriverConfig) -> None:
    """actions.log contains fill record with before and after values."""
    with BrowserDriver(session_id="p5_log", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        drv.fill("#search-input", "first_val")
        drv.fill("#search-input", "second_val")

        log_lines = [
            json.loads(line)
            for line in drv.session_actions_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        fill_logs = [entry for entry in log_lines if entry["action"] == "fill"]
        assert len(fill_logs) == 2
        assert fill_logs[0]["before"] == ""
        assert fill_logs[0]["after"] == "first_val"
        assert fill_logs[1]["before"] == "first_val"
        assert fill_logs[1]["after"] == "second_val"
