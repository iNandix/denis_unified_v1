#!/usr/bin/env python3
"""Preflight checks for Chat CP runtime dependencies."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from denis_unified_v1.chat_cp.preflight import format_preflight_lines, run_chat_cp_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat CP preflight")
    parser.add_argument(
        "--provider",
        default="auto",
        choices=["auto", "openai", "anthropic", "local"],
    )
    parser.add_argument("--service", default="denis_chat_cp")
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = run_chat_cp_preflight(
        provider=args.provider,
        service=args.service,
        timeout_seconds=args.timeout_seconds,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        for line in format_preflight_lines(payload):
            print(line)

    if args.strict:
        return 0 if bool(payload.get("ready", False)) else 1
    if args.provider in {"openai", "anthropic"}:
        return 0 if bool(payload.get("ready", False)) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
