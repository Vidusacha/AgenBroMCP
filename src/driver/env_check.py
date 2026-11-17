"""Environment check and diagnostic logging (Phase 0)."""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import PIL
import playwright
import pytesseract

from .config import configure_tesseract, get_repo_root


def get_tesseract_version() -> str:
    """Return the version string from `tesseract --version`."""
    binary = configure_tesseract() or "tesseract"
    proc = subprocess.run(
        [binary, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    output = (proc.stdout or proc.stderr).strip()
    return output.splitlines()[0] if output else "unknown"


def write_env_log(target_path: Path | None = None) -> Dict[str, str]:
    """Collect versions of OS, Python, Playwright, Pillow, and Tesseract, and write env.log."""
    repo_root = get_repo_root()
    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    tess_ver = "unavailable"
    try:
        tess_ver = get_tesseract_version()
    except Exception as exc:
        tess_ver = f"error: {exc}"

    pw_ver = getattr(playwright, "__version__", "installed")
    try:
        from importlib.metadata import version

        pw_ver = version("playwright")
    except Exception:
        pass

    info = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.split()[0],
        "repo_root": str(repo_root),
        "playwright": pw_ver,
        "pillow": PIL.__version__,
        "pytesseract": getattr(pytesseract, "__version__", "installed"),
        "tesseract_binary": str(configure_tesseract() or "not_found"),
        "tesseract_version": tess_ver,
    }

    log_file = target_path or (repo_root / "env.log")
    lines = [f"{k}={v}" for k, v in info.items()]
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return info
