"""Phase 7 tests: Control protocol (stdin JSON stream + MCP Server tools)."""

from __future__ import annotations

import json
from pathlib import Path

from driver.config import DriverConfig
from driver.mcp_server import (
    browser_click,
    browser_close_session,
    browser_fill,
    browser_open,
    browser_read,
    reset_session_pool,
)
from driver.protocol import ProtocolSessionPool, execute_action, execute_stream


def test_protocol_roundtrip(test_server_url: str, temp_config: DriverConfig) -> None:
    """Full pipeline open -> read -> fill -> click via JSON stream produces valid artifact chain."""
    commands = [
        json.dumps({"op": "open", "target": f"{test_server_url}/index.html", "session": "p7_rt"}),
        json.dumps({"op": "read", "session": "p7_rt"}),
        json.dumps({"op": "click", "target": "#link-forms", "session": "p7_rt"}),
        json.dumps({"op": "fill", "target": "#search-input", "value": "protocol_ok", "session": "p7_rt"}),
        json.dumps({"op": "click", "target": "#submit-btn", "session": "p7_rt"}),
    ]
    results = execute_stream(commands, config=temp_config, default_session="p7_rt")
    assert len(results) == 5
    assert all(r["ok"] is True for r in results)
    assert "next.html" in results[-1]["state"]["url"]
    assert "q=protocol_ok" in results[-1]["state"]["url"]
    assert len(results[-1]["artifacts"]) >= 3


def test_bad_action_rejected(test_server_url: str, temp_config: DriverConfig) -> None:
    """Invalid op {'op': 'teleport'} returns {'ok': False, 'error': ...} without changing state."""
    pool = ProtocolSessionPool(default_config=temp_config)
    try:
        res_open = execute_action(
            {"op": "open", "target": f"{test_server_url}/index.html", "session": "p7_bad"},
            pool=pool,
        )
        assert res_open["ok"] is True
        state_before = res_open["state"]

        res_bad = execute_action({"op": "teleport", "session": "p7_bad"}, pool=pool)
        assert res_bad["ok"] is False
        assert "teleport" in res_bad["error"]
        assert res_bad["state"]["url"] == state_before["url"]
        assert res_bad["state"]["html_hash"] == state_before["html_hash"]
    finally:
        pool.close_all()


def test_timeout(test_server_url: str, temp_config: DriverConfig) -> None:
    """Hanging endpoint returns a clean timeout error result instead of hanging the process."""
    temp_config.timeout_ms = 500
    res = execute_action(
        {"op": "open", "target": f"{test_server_url}/hang", "session": "p7_timeout", "timeout_ms": 500},
        pool=None,
    )
    assert res["ok"] is False
    assert "Timeout" in res["error"] or "timeout" in res["error"].lower()


def test_artifact_chain(test_server_url: str, temp_config: DriverConfig) -> None:
    """After fill + click, manifest.json and actions.log are linked by session and page_id."""
    commands = [
        json.dumps({"op": "open", "target": f"{test_server_url}/forms.html", "session": "p7_chain"}),
        json.dumps({"op": "fill", "target": "#search-input", "value": "chain_test", "session": "p7_chain"}),
        json.dumps({"op": "click", "target": "#submit-btn", "session": "p7_chain"}),
    ]
    results = execute_stream(commands, config=temp_config, default_session="p7_chain")
    final_res = results[-1]
    assert final_res["ok"] is True
    page_id = final_res["page"]

    manifest_file = temp_config.artifacts_dir / "p7_chain" / page_id / "manifest.json"
    actions_file = temp_config.artifacts_dir / "p7_chain" / "actions.log"
    assert manifest_file.is_file()
    assert actions_file.is_file()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["session"] == "p7_chain"
    assert manifest["page_id"] == page_id

    logs = [json.loads(line) for line in actions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(l["action"] == "fill" and l["session"] == "p7_chain" for l in logs)
    assert any(l["action"] == "click" and l["page_id"] == page_id for l in logs)


def test_mcp_tools(test_server_url: str, temp_config: DriverConfig) -> None:
    """Verify MCP server tool functions execute open -> read -> fill -> click -> close."""
    reset_session_pool(temp_config)
    try:
        r_open = browser_open(url=f"{test_server_url}/index.html", session="mcp_s1")
        assert r_open["ok"] is True
        assert any("SECRET" in img["ocr_text"].upper() for img in r_open["data"]["images"])

        r_read = browser_read(session="mcp_s1")
        assert r_read["ok"] is True
        assert len(r_read["data"]["links"]) == 2

        r_nav = browser_click(selector="#link-forms", session="mcp_s1")
        assert r_nav["ok"] is True

        r_fill = browser_fill(selector="#search-input", value="mcp_val", session="mcp_s1")
        assert r_fill["ok"] is True
        assert r_fill["data"]["after"] == "mcp_val"
    finally:
        browser_close_session(session="mcp_s1")
