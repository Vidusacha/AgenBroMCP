"""Phase 10 and Cross-Phase Acceptance Matrix tests."""

from __future__ import annotations

import json
from pathlib import Path

from driver.cli import main as cli_main
from driver.config import DriverConfig, get_repo_root
from driver.session import BrowserDriver


def test_repo_layout() -> None:
    """Verify repository structure matches specification (src/driver, tests, fixtures, config, artifacts)."""
    root = get_repo_root()
    assert (root / "src" / "driver").is_dir()
    assert (root / "tests").is_dir()
    assert (root / "fixtures").is_dir()
    assert (root / "config" / "default.json").is_file()
    assert (root / "artifacts").is_dir()
    assert (root / "pyproject.toml").is_file()
    assert (root / ".gitignore").is_file()
    assert (root / "scripts" / "bootstrap.ps1").is_file()
    assert (root / "scripts" / "bootstrap.sh").is_file()


def test_cli_smoke(test_server_url: str, tmp_path: Path, capsys) -> None:
    """CLI `run --url --session --actions file` opens fixture page, executes actions, and writes artifacts."""
    actions_file = tmp_path / "actions.jsonl"
    actions_file.write_text(
        "\n".join(
            [
                json.dumps({"op": "read"}),
                json.dumps({"op": "click", "target": "#link-forms"}),
                json.dumps({"op": "fill", "target": "#search-input", "value": "cli_smoke_ok"}),
            ]
        ),
        encoding="utf-8",
    )
    art_dir = tmp_path / "cli_artifacts"

    exit_code = cli_main(
        [
            "run",
            "--url",
            f"{test_server_url}/index.html",
            "--session",
            "smoke_sess",
            "--actions",
            str(actions_file),
            "--artifacts-dir",
            str(art_dir),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out.strip().splitlines()
    assert len(captured) == 4
    parsed = [json.loads(line) for line in captured]
    assert all(p["ok"] is True for p in parsed)
    assert (art_dir / "smoke_sess" / "actions.log").is_file()


def test_open_read_ocr(test_server_url: str, temp_config: DriverConfig) -> None:
    """Cross-phase acceptance: Open -> Read (text + images + OCR) returns links and OCR text in manifest."""
    with BrowserDriver(session_id="acc_ocr", config=temp_config) as drv:
        manifest = drv.open_page(f"{test_server_url}/index.html", run_ocr=True)
        read_data = drv.read()
        assert len(read_data["links"]) == 2
        assert len(manifest["images"]) == 2
        assert any("SECRET" in img["ocr_text"].upper() for img in manifest["images"])


def test_fill_click_navigate(test_server_url: str, temp_config: DriverConfig) -> None:
    """Cross-phase acceptance: Open -> Fill -> Click -> Navigate updates URL, logs actions, and saves diff."""
    with BrowserDriver(session_id="acc_nav", config=temp_config) as drv:
        drv.open_page(f"{test_server_url}/forms.html", run_ocr=False)
        drv.fill("#search-input", "matrix_test")
        click_res = drv.click("#submit-btn")

        assert "next.html" in click_res["url_after"]
        assert "q=matrix_test" in click_res["url_after"]
        assert Path(click_res["manifest"]["screenshot"]).is_file()
        assert Path(click_res["manifest"]["diff_path"]).is_file()

        logs = [
            json.loads(line)
            for line in drv.session_actions_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        actions_seq = [l["action"] for l in logs]
        assert "fill" in actions_seq and "click" in actions_seq


def test_suite_green() -> None:
    """Verify all phase test modules exist and are collected in tests/."""
    tests_dir = get_repo_root() / "tests"
    expected = [
        "test_phase0_env.py",
        "test_phase1_session.py",
        "test_phase2_reader.py",
        "test_phase3_ocr.py",
        "test_phase4_actionables.py",
        "test_phase5_fill.py",
        "test_phase6_click.py",
        "test_phase7_protocol.py",
        "test_phase8_state.py",
        "test_phase9_safety.py",
        "test_phase10_packaging.py",
    ]
    for fname in expected:
        assert (tests_dir / fname).is_file(), f"Missing test file: {fname}"
