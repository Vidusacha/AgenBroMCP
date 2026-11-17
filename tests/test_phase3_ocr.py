"""Phase 3 tests: Image inventory, download/capture, preprocessing, and OCR."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from driver.config import DriverConfig
from driver.ocr import preprocess_image, run_ocr_on_file, run_ocr_on_image, run_tesseract_with_conf
from driver.session import BrowserDriver


def _font(size: int = 36):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def test_ocr_synthetic() -> None:
    """Synthetic PIL PNG with 'ABC123' returns string containing 'ABC123' above confidence threshold."""
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((25, 25), "ABC123", fill=(0, 0, 0), font=_font(40))

    res = run_ocr_on_image(img, lang="eng", min_conf=50.0)
    assert "ABC123" in res.text.replace(" ", "")
    assert res.conf >= 50.0
    assert res.status == "ok"


def test_ocr_real_image(fixtures_dir: Path) -> None:
    """Fixture image ocr_fixture.png contains control string 'SECRET CODE 987'."""
    img_path = fixtures_dir / "ocr_fixture.png"
    res = run_ocr_on_file(img_path, lang="eng", min_conf=50.0)
    assert "SECRET" in res.text.upper()
    assert "987" in res.text
    assert res.conf >= 50.0


def test_inventory_has_all_images(test_server_url: str, temp_config: DriverConfig) -> None:
    """Number of images in manifest inventory matches number of <img> tags in DOM."""
    with BrowserDriver(session_id="p3_inv", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html", run_ocr=True)
        dom_img_count = drv.page.locator("img").count()
        assert len(manifest["images"]) == dom_img_count
        assert dom_img_count == 2


def test_ocr_on_page_images(test_server_url: str, temp_config: DriverConfig) -> None:
    """After open_page, manifest.images contains ocr_text and downloaded file for each image."""
    with BrowserDriver(session_id="p3_page_ocr", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html", run_ocr=True)
        images = manifest["images"]
        assert len(images) == 2
        for img_entry in images:
            assert img_entry["file"] and Path(img_entry["file"]).is_file()
            assert img_entry["ocr_text"]
        ocr_texts = " ".join(i["ocr_text"].upper() for i in images)
        assert "LOGO" in ocr_texts
        assert "SECRET" in ocr_texts


def test_ocr_preprocess() -> None:
    """Preprocessing (upscale + autocontrast + binarize + margin) improves OCR confidence on low-contrast UI button."""
    # Dark gray button (55) with dark text (35) and a 1px bright highlight line (255) that fools raw Otsu thresholding
    raw_img = Image.new("L", (160, 44), color=55)
    draw = ImageDraw.Draw(raw_img)
    draw.line([(0, 0), (159, 0)], fill=255, width=1)
    draw.text((12, 8), "TEST 99", fill=35, font=_font(24))

    _, raw_conf = run_tesseract_with_conf(raw_img, lang="eng")
    pre_img = preprocess_image(raw_img, binarize=True)
    pre_text, pre_conf = run_tesseract_with_conf(pre_img, lang="eng")

    assert "TEST" in pre_text.upper() and "99" in pre_text
    assert pre_conf > raw_conf
