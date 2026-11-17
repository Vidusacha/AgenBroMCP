"""Phase 1 tests: Session management and artifact generation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_open_page_creates_dir(test_server_url: str, temp_config: DriverConfig) -> None:
    """Opening a page creates the page artifact directory with page.html, page.png, manifest.json."""
    with BrowserDriver(session_id="s1", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html")
        page_dir = drv.current_page_dir
        assert page_dir is not None and page_dir.is_dir()
        assert (page_dir / "page.html").is_file()
        assert (page_dir / "page.png").is_file()
        assert (page_dir / "manifest.json").is_file()
        assert (page_dir / "actions.log").is_file()
        assert manifest["page_id"] == page_dir.name


def test_manifest_fields(test_server_url: str, temp_config: DriverConfig) -> None:
    """Manifest contains required metadata fields: url, title, screenshot, html_path, ts."""
    with BrowserDriver(session_id="s2", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html")
        for key in ("url", "title", "screenshot", "html_path", "ts"):
            assert key in manifest and manifest[key]
        assert manifest["title"] == "Fixture Index Page"
        assert Path(manifest["screenshot"]).is_file()
        assert Path(manifest["html_path"]).is_file()


def test_screenshot_nonempty(test_server_url: str, temp_config: DriverConfig) -> None:
    """Screenshot is decodable by PIL and has non-zero dimensions and file size."""
    with BrowserDriver(session_id="s3", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html")
        png_path = Path(manifest["screenshot"])
        assert png_path.stat().st_size > temp_config.min_screenshot_bytes
        with Image.open(png_path) as img:
            assert img.width > 0 and img.height > 0


def test_session_reuse(test_server_url: str, temp_config: DriverConfig) -> None:
    """Two pages in one session preserve cookies and custom user-agent."""
    temp_config.user_agent = "CustomAgenBroAgent/1.0"
    with BrowserDriver(session_id="s4", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/do_login?username=ev_tester")
        assert "Welcome Authenticated User" in drv.page.content()

        # Open dashboard again in same session and verify cookie and UA persist
        drv.open_page(f"{test_server_url}/dashboard")
        assert "session_user=ev_tester" in drv.page.content()
        ua = drv.page.evaluate("() => navigator.userAgent")
        assert ua == "CustomAgenBroAgent/1.0"
