"""Image preprocessing and OCR pipeline (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pytesseract
from PIL import Image, ImageOps

from .config import configure_tesseract

configure_tesseract()

_rapid_ocr = None


def _get_rapid_ocr():
    global _rapid_ocr
    if _rapid_ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _rapid_ocr = RapidOCR()
        except Exception:
            _rapid_ocr = False
    return _rapid_ocr if _rapid_ocr is not False else None


@dataclass
class OCRResult:
    """Structured OCR output for an image."""

    text: str
    conf: float
    status: str  # "ok", "fallback_alt", "ocr_failed"


def preprocess_image(img: Image.Image, binarize: bool = True) -> Image.Image:
    """Preprocess an image (grayscale, autocontrast with outlier cutoff, adaptive binarize, upscale, border)."""
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=3)

    # Check if background is dark (invert so text is dark on white background)
    corners = [
        gray.getpixel((0, 0)),
        gray.getpixel((gray.width - 1, 0)),
        gray.getpixel((0, gray.height - 1)),
        gray.getpixel((gray.width - 1, gray.height - 1)),
    ]
    if (sum(corners) / len(corners)) < 128:
        gray = ImageOps.invert(gray)

    if binarize:
        # Soft-edge binarization: push background (>180) to pure white (255),
        # push dark text (<90) to pure black (0), and linearly scale mid-tones for anti-aliasing
        def _soft_threshold(p: int) -> int:
            if p >= 180:
                return 255
            if p <= 90:
                return 0
            return int((p - 90) * 255 / 90)

        gray = gray.point(_soft_threshold, mode="L")

    width, height = gray.size
    if height < 100 or width < 220:
        scale = 2
        gray = gray.resize(
            (max(1, width * scale), max(1, height * scale)),
            Image.Resampling.BICUBIC,
        )

    # Add clean white border around the image
    padded = ImageOps.expand(gray, border=20, fill=255)
    return padded


def run_tesseract_with_conf(img: Image.Image, lang: str = "eng") -> Tuple[str, float]:
    """Run pytesseract on a PIL image and return (recognized_text, mean_confidence)."""
    configure_tesseract()
    try:
        data = pytesseract.image_to_data(
            img,
            lang=lang,
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        data = pytesseract.image_to_data(
            img,
            lang="eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )

    words = []
    confs = []
    texts = data.get("text", [])
    raw_confs = data.get("conf", [])

    for word, raw_conf in zip(texts, raw_confs):
        cleaned = (word or "").strip()
        try:
            conf_val = float(raw_conf)
        except (TypeError, ValueError):
            conf_val = -1.0
        if cleaned and conf_val >= 0:
            words.append(cleaned)
            confs.append(conf_val)

    full_text = " ".join(words).strip()
    mean_conf = (sum(confs) / len(confs)) if confs else 0.0
    return full_text, round(mean_conf, 2)


def run_rapidocr_with_conf(img: Image.Image) -> Tuple[str, float]:
    """Portable ONNX OCR fallback when Tesseract yields low confidence on stylized/alphanumeric strings."""
    engine = _get_rapid_ocr()
    if engine is None:
        return "", 0.0
    try:
        arr = np.array(img.convert("RGB"))
        result, _ = engine(arr)
        if not result:
            return "", 0.0
        words = []
        confs = []
        for line in result:
            # line format: [box, text, score]
            txt = str(line[1]).strip()
            score = float(line[2]) * 100.0
            if txt:
                words.append(txt)
                confs.append(score)
        if not words:
            return "", 0.0
        return " ".join(words), round(sum(confs) / len(confs), 2)
    except Exception:
        return "", 0.0


def run_ocr_on_image(
    img: Image.Image,
    lang: str = "eng",
    min_conf: float = 50.0,
    alt_text: str = "",
    use_preprocess: bool = True,
) -> OCRResult:
    """Execute OCR (with preprocessing, RapidOCR fallback, and fallback to alt or ocr_failed)."""
    target_img = preprocess_image(img, binarize=True) if use_preprocess else img
    text, conf = run_tesseract_with_conf(target_img, lang=lang)

    if use_preprocess and (not text or conf < min_conf):
        raw_text, raw_conf = run_tesseract_with_conf(img, lang=lang)
        if raw_text and raw_conf > conf:
            text, conf = raw_text, raw_conf

    if not text or conf < min_conf:
        r_text, r_conf = run_rapidocr_with_conf(target_img)
        if r_text and r_conf > conf:
            text, conf = r_text, r_conf

    if text and conf >= min_conf:
        return OCRResult(text=text, conf=conf, status="ok")

    clean_alt = (alt_text or "").strip()
    if clean_alt:
        return OCRResult(text=clean_alt, conf=conf, status="fallback_alt")

    return OCRResult(text="ocr_failed", conf=conf, status="ocr_failed")


def run_ocr_on_file(
    file_path: Path,
    lang: str = "eng",
    min_conf: float = 50.0,
    alt_text: str = "",
    use_preprocess: bool = True,
) -> OCRResult:
    """Open an image file and run the OCR pipeline."""
    with Image.open(file_path) as img:
        return run_ocr_on_image(
            img=img,
            lang=lang,
            min_conf=min_conf,
            alt_text=alt_text,
            use_preprocess=use_preprocess,
        )
