"""Configuration and cross-platform path resolution for AgenBroMCP."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

import pytesseract
from pydantic import BaseModel, Field


def get_repo_root() -> Path:
    """Return the root directory of the repository."""
    return Path(__file__).resolve().parents[2]


def find_tesseract_binary() -> Optional[str]:
    """Locate the Tesseract executable across Windows, Linux, and macOS."""
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and Path(env_cmd).is_file():
        return str(Path(env_cmd).resolve())

    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return str(Path(which_cmd).resolve())

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        Path("/usr/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
        Path("/opt/homebrew/bin/tesseract"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())

    return None


def configure_tesseract() -> Optional[str]:
    """Configure pytesseract to use the discovered Tesseract binary and tessdata directory."""
    binary = find_tesseract_binary()
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary
        tess_dir = Path(binary).parent
        tessdata = tess_dir / "tessdata"
        if tessdata.is_dir() and "TESSDATA_PREFIX" not in os.environ:
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
    return binary


# Configure on import so any module using pytesseract works out of the box
configure_tesseract()


class DriverConfig(BaseModel):
    """Runtime configuration for the BrowserDriver."""

    repo_root: Path = Field(default_factory=get_repo_root)
    artifacts_dir: Path = Field(default_factory=lambda: get_repo_root() / "artifacts")
    user_agent: str = "AgenBroMCP/0.1.0 (Playwright; Chromium)"
    viewport_width: int = 1280
    viewport_height: int = 800
    timeout_ms: int = 10000
    ocr_langs: str = "eng"
    ocr_min_conf: float = 50.0
    min_screenshot_bytes: int = 500
    max_actions: int = 50
    max_screenshots: int = 100
    max_downloads: int = 100
    headless: bool = True
    allowed_domains: List[str] = Field(default_factory=list)
    cdp_url: Optional[str] = None

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> "DriverConfig":
        """Load configuration from JSON file, falling back to defaults."""
        target = path or (get_repo_root() / "config" / "default.json")
        if target.is_file():
            data = json.loads(target.read_text(encoding="utf-8"))
            return cls(**data)
        return cls()
