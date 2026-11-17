"""Phase 9 tests: Safety guards, destructive operation confirmation, action limits, and timeout cleanup."""

from __future__ import annotations

from pathlib import Path

from driver.config import DriverConfig
from driver.protocol import ProtocolSessionPool, execute_action


def test_blocked_op(test_server_url: str, temp_config: DriverConfig) -> None:
    """Action with {danger: True} or clicking destructive button without confirmation returns {ok: False}."""
    pool = ProtocolSessionPool(default_config=temp_config)
    try:
        execute_action({"op": "open", "target": f"{test_server_url}/forms.html", "session": "p9_sec"}, pool=pool)

        # 1. Explicit danger: True without confirm: True
        res_explicit = execute_action(
            {"op": "click", "target": "#toggle-btn", "danger": True, "session": "p9_sec"},
            pool=pool,
        )
        assert res_explicit["ok"] is False

        # 2. Heuristic detection on "Delete Account" button (#danger-btn) without confirm: True
        res_heuristic = execute_action(
            {"op": "click", "target": "#danger-btn", "session": "p9_sec"},
            pool=pool,
        )
        assert res_heuristic["ok"] is False

        # 3. With confirm: True, operation is permitted
        res_confirmed = execute_action(
            {"op": "click", "target": "#danger-btn", "danger": True, "confirm": True, "session": "p9_sec"},
            pool=pool,
        )
        assert res_confirmed["ok"] is True
    finally:
        pool.close_all()


def test_limits(test_server_url: str, temp_config: DriverConfig) -> None:
    """Exceeding max_actions limit returns {ok: False} error without hanging."""
    temp_config.max_actions = 2
    pool = ProtocolSessionPool(default_config=temp_config)
    try:
        r1 = execute_action({"op": "open", "target": f"{test_server_url}/forms.html", "session": "p9_lim"}, pool=pool)
        r2 = execute_action({"op": "fill", "target": "#search-input", "value": "a", "session": "p9_lim"}, pool=pool)
        r3 = execute_action({"op": "fill", "target": "#search-input", "value": "b", "session": "p9_lim"}, pool=pool)

        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r3["ok"] is False
        assert "limit" in r3["error"].lower()
    finally:
        pool.close_all()


def test_timeout_cleanup(test_server_url: str, temp_config: DriverConfig) -> None:
    """Timeout does not hang the process and still writes emergency snapshot artifacts."""
    temp_config.timeout_ms = 500
    pool = ProtocolSessionPool(default_config=temp_config)
    try:
        res = execute_action(
            {"op": "open", "target": f"{test_server_url}/hang", "session": "p9_time", "timeout_ms": 500},
            pool=pool,
        )
        assert res["ok"] is False
        assert len(res["artifacts"]) > 0
        assert all(Path(p).is_file() for p in res["artifacts"])
    finally:
        pool.close_all()
