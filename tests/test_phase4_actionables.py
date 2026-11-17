"""Phase 4 tests: Actionable elements mapping (selector -> role, label, text, href)."""

from __future__ import annotations

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_collect_inputs(test_server_url: str, temp_config: DriverConfig) -> None:
    """All <input> and <select> elements on the fixture form are collected with their labels."""
    with BrowserDriver(session_id="p4_inputs", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        actionables = drv.collect_actionables()
        by_selector = {a["selector"]: a for a in actionables}

        assert "#search-input" in by_selector
        assert by_selector["#search-input"]["label"] == "Search Query"

        assert "#role-select" in by_selector
        assert by_selector["#role-select"]["label"] == "User Role"

        assert "#agree-check" in by_selector
        assert by_selector["#agree-check"]["label"] == "Agree to Terms"


def test_button_text(test_server_url: str, temp_config: DriverConfig) -> None:
    """Button 'Submit' has text='Submit' and role='button'."""
    with BrowserDriver(session_id="p4_btn", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        actionables = drv.collect_actionables()
        submit_btn = next(a for a in actionables if a["selector"] == "#submit-btn")
        assert submit_btn["text"] == "Submit"
        assert submit_btn["role"] == "button"


def test_link_selector(test_server_url: str, temp_config: DriverConfig) -> None:
    """Every <a> element maps into actionables with a valid href and selector."""
    with BrowserDriver(session_id="p4_links", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        actionables = drv.collect_actionables()
        links = [a for a in actionables if a["role"] == "link"]
        assert len(links) == 2
        assert all(lnk["href"] and lnk["href"].startswith("http") for lnk in links)


def test_no_dupes(test_server_url: str, temp_config: DriverConfig) -> None:
    """Each DOM element receives a unique actionable ID and selector without duplicates."""
    with BrowserDriver(session_id="p4_nodupes", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        actionables = drv.collect_actionables()
        ids = [a["id"] for a in actionables]
        selectors = [a["selector"] for a in actionables]
        assert len(ids) == len(set(ids))
        assert len(selectors) == len(set(selectors))
