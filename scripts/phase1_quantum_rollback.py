#!/usr/bin/env python3
"""CLI for Phase-1 rollback (remove quantum properties)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.quantum.entity_augmentation import emit_result, run_rollback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rollback Phase-1 quantum augmentation")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute rollback writes against Neo4j. Default is dry-run.",
    )
    parser.add_argument(
        "--out-json",
        default="",
        help="Optional output JSON path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_rollback(execute=args.execute)
    emit_result(result)

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote json: {out}")

    if result.get("status") == "error":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

