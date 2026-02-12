#!/usr/bin/env python3
"""Phase-10 gate preflight: valida readiness del sandbox gate (fail-closed)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.autopoiesis.self_extension_engine import (  # noqa: E402
    create_self_extension_engine,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-10 gate preflight")
    parser.add_argument(
        "--out-json",
        default="phase10_gate_preflight.json",
        help="Output JSON path",
    )
    return parser.parse_args()


def _check_module(python_bin: str, module: str) -> bool:
    cmd = [python_bin, "-c", f"import importlib.util as u; raise SystemExit(0 if u.find_spec('{module}') else 1)"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    return result.returncode == 0


def main() -> int:
    args = parse_args()
    engine = create_self_extension_engine()

    requested_raw = os.getenv("DENIS_SELF_EXTENSION_SANDBOX_PYTHON")
    requested = Path(requested_raw).as_posix() if requested_raw else None
    effective_python = str(engine._sandbox_python)  # noqa: SLF001 - preflight operativo
    timeout_seconds = int(engine._sandbox_timeout_seconds)  # noqa: SLF001
    strict_mode = bool(engine._strict_tooling)  # noqa: SLF001

    required_tools = ["ruff", "mypy", "pytest", "bandit"]
    tools = {tool: _check_module(effective_python, tool) for tool in required_tools}
    missing_tools = [tool for tool, ok in tools.items() if not ok]

    errors: list[str] = []
    if timeout_seconds <= 0:
        errors.append("invalid_timeout")
    if not strict_mode:
        errors.append("strict_mode_disabled")
    if missing_tools:
        errors.append("missing_tools")

    status = "ok" if not errors else "error"
    payload: dict[str, Any] = {
        "status": status,
        "requested_sandbox_python": requested,
        "effective_sandbox_python": effective_python,
        "timeout_seconds": timeout_seconds,
        "strict_mode": strict_mode,
        "tools": tools,
        "missing_tools": missing_tools,
        "errors": errors,
    }

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
