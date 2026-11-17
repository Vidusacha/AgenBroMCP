"""CLI and stdin runner for AgenBroMCP (Phases 7 and 10)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DriverConfig
from .protocol import ProtocolSessionPool, execute_action, execute_stream


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgenBroMCP Browser Driver CLI")
    parser.add_argument("command", nargs="?", default="run", help="Command to execute (default: run)")
    parser.add_argument("--url", type=str, default=None, help="Initial URL to open")
    parser.add_argument("--session", type=str, default="default", help="Session identifier")
    parser.add_argument("--actions", type=str, default=None, help="Path to JSON or JSONL actions file")
    parser.add_argument("--artifacts-dir", type=str, default=None, help="Override artifacts output directory")
    parser.add_argument("--config", type=str, default=None, help="Path to config JSON file")
    parser.add_argument(
        "--cdp",
        type=str,
        default=None,
        help="Connect to an external Chrome started with --remote-debugging-port (CDP URL, e.g. http://127.0.0.1:9222)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = DriverConfig.from_file(Path(args.config) if args.config else None)
    if args.artifacts_dir:
        cfg.artifacts_dir = Path(args.artifacts_dir).resolve()
    if args.cdp:
        cfg.cdp_url = args.cdp

    commands: List[Dict[str, Any]] = []
    if args.url:
        commands.append({"op": "open", "target": args.url, "session": args.session})

    if args.actions:
        actions_path = Path(args.actions)
        raw_content = actions_path.read_text(encoding="utf-8").strip()
        if raw_content.startswith("["):
            loaded = json.loads(raw_content)
            commands.extend(loaded)
        else:
            for line in raw_content.splitlines():
                if line.strip():
                    commands.append(json.loads(line.strip()))

    if commands:
        pool = ProtocolSessionPool(default_config=cfg)
        try:
            for cmd in commands:
                if "session" not in cmd or not cmd["session"]:
                    cmd["session"] = args.session
                res = execute_action(cmd, pool=pool)
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        finally:
            pool.close_all()
        return 0

    # Fallback to reading JSON / NDJSON commands from stdin
    stdin_lines = sys.stdin.read().splitlines()
    results = execute_stream(stdin_lines, config=cfg, default_session=args.session)
    for res in results:
        sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
