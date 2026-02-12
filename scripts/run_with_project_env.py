#!/usr/bin/env python3
"""Run a command with environment variables loaded from project .env safely."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        match = _ENV_LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        # Drop inline comments for unquoted values.
        if " #" in value and not value.startswith(("'", '"')):
            value = value.split(" #", 1)[0]
        value = value.strip().strip("'").strip('"')
        data[key] = value
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run command with .env loaded")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file to load",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute, prefix with --",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.command:
        print("error: missing command. usage: run_with_project_env.py -- <cmd>", file=sys.stderr)
        return 2
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("error: empty command after --", file=sys.stderr)
        return 2

    env_file = Path(args.env_file)
    loaded = _load_env_file(env_file)
    env = os.environ.copy()
    env.update(loaded)

    proc = subprocess.run(cmd, env=env)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

