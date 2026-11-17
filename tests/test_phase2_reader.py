"""Phase 2 tests: DOM reader (links, images inventory, headings, clean text blocks)."""

from __future__ import annotations

from driver.config import DriverConfig
from driver.session import BrowserDriver


def test_read_links(test_server_url: str, temp_config: DriverConfig) -> None:
    """Page with 2 known links returns 2 link objects with href and text."""
    with BrowserDriver(session_id="p2_links", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        links = drv.read_links()
        assert len(links) == 2
        texts = [lnk["text"] for lnk in links]
        assert "Go to Forms" in texts
        assert "Next Page" in texts
        assert all(lnk["href"].startswith("http") for lnk in links)


def test_read_images_inventory(test_server_url: str, temp_config: DriverConfig) -> None:
    """Page with <img alt='logo'> returns inventory with URL, alt, and natural size."""
    with BrowserDriver(session_id="p2_imgs", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        imgs = drv.read_images()
        assert len(imgs) >= 1
        logo = next(i for i in imgs if i["alt"] == "logo")
        assert logo["url"].endswith("/logo.png")
        assert logo["size"]["width"] == 320
        assert logo["size"]["height"] == 100


def test_read_headings(test_server_url: str, temp_config: DriverConfig) -> None:
    """Headings h1 and h2 are extracted in DOM order."""
    with BrowserDriver(session_id="p2_headings", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        headings = drv.read_headings()
        assert len(headings) == 2
        assert headings[0]["tag"] == "h1"
        assert headings[0]["text"] == "Main Welcome Heading"
        assert headings[1]["tag"] == "h2"
        assert headings[1]["text"] == "Secondary Section Heading"


def test_text_blocks(test_server_url: str, temp_config: DriverConfig) -> None:
    """Continuous body text is extracted without <script> or <style> noise."""
    with BrowserDriver(session_id="p2_text", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/index.html", run_ocr=False)
        blocks = drv.read_text()
        joined = "\n".join(blocks)
        assert "First paragraph of clean body text" in joined
        assert "SHOULD_NOT_APPEAR_IN_TEXT_BLOCKS" not in joined
        assert "font-family" not in joined
