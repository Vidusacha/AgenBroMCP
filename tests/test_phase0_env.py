"""Phase 0 tests: Environment preparation, Playwright launch, and OCR toolchain."""

from __future__ import annotations

import io
from pathlib import Path

import pytesseract
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from driver.config import configure_tesseract, get_repo_root
from driver.env_check import get_tesseract_version, write_env_log


def test_env_pwd() -> None:
    """Verify repository root and artifacts directory exist and write env.log."""
    repo_root = get_repo_root()
    assert repo_root.is_dir()
    assert (repo_root / "pyproject.toml").is_file()

    env_info = write_env_log()
    assert (repo_root / "env.log").is_file()
    assert Path(env_info["repo_root"]) == repo_root
    assert (repo_root / "artifacts").is_dir()


def test_playwright_launch() -> None:
    """Verify headless Chromium launches, opens about:blank, and takes a non-empty screenshot."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto("about:blank")
            png_bytes = page.screenshot(type="png")
            assert len(png_bytes) > 0
        finally:
            browser.close()


def test_tesseract_available() -> None:
    """Verify tesseract --version works and pytesseract recognizes 'HELLO' on a synthetic PNG."""
    configure_tesseract()
    version_str = get_tesseract_version()
    assert "tesseract" in version_str.lower()

    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=36)
    except TypeError:
        font = ImageFont.load_default()
    draw.text((30, 30), "HELLO", fill=(0, 0, 0), font=font)

    recognized = pytesseract.image_to_string(img, lang="eng")
    assert "HELLO" in recognized.upper()


def test_playwright_screenshot() -> None:
    """Verify page screenshot is a valid PNG and exceeds minimum threshold bytes."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.set_content("<html><body><h1>AgenBro Test Page</h1></body></html>")
            png_bytes = page.screenshot(type="png")
            assert len(png_bytes) > 500
            img = Image.open(io.BytesIO(png_bytes))
            assert img.format == "PNG"
            assert img.size == (800, 600)
        finally:
            browser.close()
