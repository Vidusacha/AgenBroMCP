"""Safety policies, destructive operation guards, and limits (Phase 9)."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse


class SafetyError(Exception):
    """Raised when an action violates safety policy or lacks confirmation."""


class ActionLimitError(SafetyError):
    """Raised when session action/screenshot/download limits are exceeded."""


DESTRUCTIVE_KEYWORDS = re.compile(
    r"\b(delete|remove|destroy|drop|pay|purchase|buy\s+now|checkout|wipe|удалить|оплатить|купить)\b",
    re.IGNORECASE,
)


def check_url_allowed(url: str, allowed_domains: Optional[List[str]] = None) -> None:
    """Validate URL scheme and optional domain allowlist."""
    if url in ("about:blank", ""):
        return
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https", "file", "data", "about"):
        raise SafetyError(f"Blocked unsupported URL scheme: {parsed.scheme}")

    if allowed_domains:
        host = (parsed.hostname or "").lower()
        allowed_set = {d.lower() for d in allowed_domains}
        if host and not any(host == d or host.endswith("." + d) for d in allowed_set):
            raise SafetyError(f"Domain '{host}' is not in allowed_domains: {allowed_domains}")


def check_destructive_action(
    danger_flag: bool = False,
    confirm_flag: bool = False,
    element_text: str = "",
    selector: str = "",
) -> None:
    """Block explicitly flagged or heuristically detected destructive operations without confirmation."""
    if danger_flag and not confirm_flag:
        raise SafetyError("Blocked dangerous operation: 'danger=True' requires 'confirm=True'.")

    combined = f"{element_text} {selector}".strip()
    if combined and DESTRUCTIVE_KEYWORDS.search(combined) and not confirm_flag:
        raise SafetyError(
            f"Blocked potentially destructive action on '{combined}' without 'confirm=True'."
        )
