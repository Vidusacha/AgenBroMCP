"""JSON action protocol processor (Phase 7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from .config import DriverConfig
from .safety import ActionLimitError, SafetyError, check_destructive_action
from .session import BrowserDriver

SUPPORTED_OPS = {"open", "goto", "read", "fill", "select", "check", "uncheck", "click", "press"}


class ProtocolSessionPool:
    """Manages active BrowserDriver instances by session ID across protocol commands."""

    def __init__(self, default_config: Optional[DriverConfig] = None) -> None:
        self.default_config = default_config or DriverConfig.from_file()
        self.drivers: Dict[str, BrowserDriver] = {}

    def get(self, session_id: str = "default") -> BrowserDriver:
        if session_id not in self.drivers:
            drv = BrowserDriver(session_id=session_id, config=self.default_config.model_copy())
            drv.start()
            self.drivers[session_id] = drv
        return self.drivers[session_id]

    def close_all(self) -> None:
        for drv in list(self.drivers.values()):
            drv.close()
        self.drivers.clear()


def _collect_current_artifacts(driver: BrowserDriver) -> List[str]:
    artifacts: List[str] = []
    if driver.current_page_dir and driver.current_page_dir.is_dir():
        for name in ("page.html", "page.png", "manifest.json", "actions.log", "page.diff"):
            candidate = driver.current_page_dir / name
            if candidate.is_file():
                artifacts.append(str(candidate))
    if driver.session_actions_log.is_file():
        artifacts.append(str(driver.session_actions_log))
    return artifacts


def _build_state_summary(driver: BrowserDriver) -> Dict[str, Any]:
    url = driver.page.url if driver._page is not None else "about:blank"
    return {
        "session": driver.session_id,
        "url": url,
        "page_id": driver.current_page_id,
        "html_hash": driver.last_html_hash or None,
        "action_count": driver.action_count,
    }


def execute_action(
    cmd: Dict[str, Any],
    driver: Optional[BrowserDriver] = None,
    pool: Optional[ProtocolSessionPool] = None,
) -> Dict[str, Any]:
    """Execute a single JSON command dictionary and return a structured protocol response."""
    op = str(cmd.get("op") or "").strip().lower()
    session_id = str(cmd.get("session") or (driver.session_id if driver else "default"))
    target = cmd.get("target") or cmd.get("selector") or cmd.get("url")
    value = cmd.get("value")
    danger = bool(cmd.get("danger", False))
    confirm = bool(cmd.get("confirm", False))

    if op not in SUPPORTED_OPS:
        existing_drv = driver or (pool.drivers.get(session_id) if pool else None)
        state = _build_state_summary(existing_drv) if existing_drv else {"session": session_id}
        return {
            "ok": False,
            "op": op,
            "session": session_id,
            "error": f"Unsupported operation: '{op}'",
            "artifacts": _collect_current_artifacts(existing_drv) if existing_drv else [],
            "state": state,
            "page": existing_drv.current_page_id if existing_drv else None,
        }

    active_driver = driver or (pool.get(session_id) if pool else BrowserDriver(session_id=session_id))
    own_driver = driver is None and pool is None

    try:
        # Global explicit danger check on any operation before execution
        check_destructive_action(
            danger_flag=danger,
            confirm_flag=confirm,
            element_text="",
            selector=str(target or ""),
        )

        if "timeout_ms" in cmd and cmd["timeout_ms"] is not None:
            active_driver.config.timeout_ms = int(cmd["timeout_ms"])
            if active_driver._context is not None:
                active_driver._context.set_default_timeout(active_driver.config.timeout_ms)

        result_data: Dict[str, Any] = {}

        if op in ("open", "goto"):
            url_str = str(target or value or "")
            if not url_str:
                raise ValueError("Operation 'open' requires 'target' or 'value' URL.")
            result_data = active_driver.open_page(url_str, run_ocr=True)

        elif op == "read":
            result_data = active_driver.read()

        elif op == "fill":
            if not target:
                raise ValueError("Operation 'fill' requires 'target' selector.")
            result_data = active_driver.fill(str(target), str(value if value is not None else ""))

        elif op == "select":
            if not target:
                raise ValueError("Operation 'select' requires 'target' selector.")
            result_data = active_driver.select(str(target), str(value if value is not None else ""))

        elif op == "check":
            if not target:
                raise ValueError("Operation 'check' requires 'target' selector.")
            checked_val = True if value is None else bool(value)
            result_data = active_driver.check(str(target), checked=checked_val)

        elif op == "uncheck":
            if not target:
                raise ValueError("Operation 'uncheck' requires 'target' selector.")
            result_data = active_driver.uncheck(str(target))

        elif op == "click":
            if not target:
                raise ValueError("Operation 'click' requires 'target' selector.")
            result_data = active_driver.click(str(target), danger=danger, confirm=confirm)

        elif op == "press":
            key_str = str(value or target or "Enter")
            sel_str = str(target) if (target and value) else None
            result_data = active_driver.press(key=key_str, selector=sel_str)

        return {
            "ok": True,
            "op": op,
            "session": active_driver.session_id,
            "artifacts": _collect_current_artifacts(active_driver),
            "state": _build_state_summary(active_driver),
            "page": active_driver.current_page_id,
            "data": result_data,
        }

    except (SafetyError, ActionLimitError) as exc:
        return {
            "ok": False,
            "op": op,
            "session": active_driver.session_id,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "artifacts": _collect_current_artifacts(active_driver),
            "state": _build_state_summary(active_driver),
            "page": active_driver.current_page_id,
        }
    except (TimeoutError, PlaywrightTimeoutError) as exc:
        # Ensure emergency artifact is captured if not already captured
        try:
            if active_driver._page is not None:
                active_driver.capture_snapshot(label="timeout_cleanup", run_ocr=False)
        except Exception:
            pass
        return {
            "ok": False,
            "op": op,
            "session": active_driver.session_id,
            "error": f"Timeout: {exc}",
            "error_type": "TimeoutError",
            "artifacts": _collect_current_artifacts(active_driver),
            "state": _build_state_summary(active_driver),
            "page": active_driver.current_page_id,
        }
    except (PlaywrightError, ValueError, Exception) as exc:
        return {
            "ok": False,
            "op": op,
            "session": active_driver.session_id,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "artifacts": _collect_current_artifacts(active_driver),
            "state": _build_state_summary(active_driver),
            "page": active_driver.current_page_id,
        }
    finally:
        if own_driver:
            active_driver.close()


def execute_stream(
    lines: Iterable[str],
    config: Optional[DriverConfig] = None,
    default_session: str = "default",
) -> List[Dict[str, Any]]:
    """Process a sequence of JSON/NDJSON lines (or a JSON array string) and return responses."""
    pool = ProtocolSessionPool(default_config=config)
    responses: List[Dict[str, Any]] = []
    raw_text = "\n".join(lines).strip()
    if not raw_text:
        return responses

    try:
        # Check if entire input is a single JSON array or object
        parsed_Commands: List[Dict[str, Any]] = []
        if raw_text.startswith("["):
            parsed_Commands = json.loads(raw_text)
        else:
            for line in raw_text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                parsed_Commands.append(json.loads(stripped))

        for cmd in parsed_Commands:
            if "session" not in cmd or not cmd["session"]:
                cmd["session"] = default_session
            res = execute_action(cmd, pool=pool)
            responses.append(res)
    finally:
        pool.close_all()

    return responses
