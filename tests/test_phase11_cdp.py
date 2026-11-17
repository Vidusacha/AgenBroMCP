"""Phase 11: connect to an external Chrome over CDP (connect_over_cdp mode).

Launches a real Chromium with --remote-debugging-port, connects the driver to it,
opens a fixture page in the adopted tab, reads it, and verifies artifacts + session.log.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from conftest import ensure_fixtures_created
from driver.config import DriverConfig
from driver.protocol import ProtocolSessionPool, execute_action
from playwright.sync_api import sync_playwright


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _launch_external_chromium(tmp_path: Path, port: int) -> subprocess.Popen:
    with sync_playwright() as pw:
        exe = pw.chromium.executable_path
    user_data = tmp_path / "chrome-profile"
    proc = subprocess.Popen(
        [
            exe,
            f"--user-data-dir={user_data}",
            f"--remote-debugging-port={port}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as resp:
                json.loads(resp.read().decode("utf-8"))
                return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("External Chromium CDP endpoint did not come up")


def test_cdp_connect_open_and_read(tmp_path: Path) -> None:
    fixtures_dir = ensure_fixtures_created()
    fixture_uri = "file:///" + str(fixtures_dir / "index.html").replace("\\", "/")
    port = _free_port()
    proc = _launch_external_chromium(tmp_path, port)

    cfg = DriverConfig(
        artifacts_dir=tmp_path / "artifacts",
        cdp_url=f"http://127.0.0.1:{port}",
        timeout_ms=15000,
    )
    pool = ProtocolSessionPool(default_config=cfg)
    try:
        opened = execute_action({"op": "open", "target": fixture_uri, "session": "cdp1"}, pool=pool)
        assert opened["ok"] is True, opened.get("error")
        assert opened["state"]["url"].endswith("index.html")

        read_res = execute_action({"op": "read", "session": "cdp1"}, pool=pool)
        assert read_res["ok"] is True
        assert read_res["data"]["title"] == "Fixture Index Page"
        heading_texts = [h["text"] for h in read_res["data"]["headings"]]
        assert "Main Welcome Heading" in heading_texts

        session_dir = cfg.artifacts_dir / "cdp1"
        manifests = list(session_dir.glob("page_001_*/manifest.json"))
        assert manifests, "CDP session artifacts were not written"
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert manifest["url"].endswith("index.html")
        assert manifest["session"] == "cdp1"
        assert (session_dir / manifests[0].parent.name / "page.png").is_file()

        entries = [
            json.loads(line)
            for line in (session_dir / "session.log").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        mode_entries = [e for e in entries if e.get("mode") == "cdp"]
        assert mode_entries, "CDP mode connection was not recorded in session.log"
        assert mode_entries[0]["cdp_url"] == cfg.cdp_url
    finally:
        pool.close_all()
        proc.terminate()
        proc.wait(timeout=15)
