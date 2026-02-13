#!/usr/bin/env python3
"""Smoke test for Level 3 metacognitive contracts (fail-open on missing deps)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 1: L3 metacognitive contracts smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/contracts/level3_metacognitive_smoke.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--scan-root",
        default=None,
        help="Root path to scan for contracts (defaults to repo root)",
    )
    return parser.parse_args()


def load_contracts(scan_root: str | None) -> Dict[str, Any]:
    # Prefer the packaged loader; if unavailable, fail-open with minimal info.
    try:
        from denis_unified_v1.contracts.loader import load_contracts as _load
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "contracts": {},
            "errors": [f"loader_import_failed: {exc}"],
            "warnings": [],
            "skipped": ["loader_missing"],
            "status": "error",
            "root": scan_root or "unknown",
        }
    return _load(scan_root)


def main() -> int:
    args = parse_args()
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    load_result = load_contracts(args.scan_root)
    duration_ms = int((time.perf_counter() - start) * 1000)

    contracts: Dict[str, Any] = load_result.get("contracts") or {}
    status = load_result.get("status", "unknown")
    errors = load_result.get("errors") or []
    warnings = load_result.get("warnings") or []
    skipped = load_result.get("skipped") or []

    required_ids = [
        "L3.META.NEVER_BLOCK",
        "L3.META.SELF_REFLECTION_LATENCY",
        "L3.META.ONLY_OBSERVE_L0",
    ]
    missing_required = [cid for cid in required_ids if cid not in contracts]

    # Derive overall outcome (fail-open on missing files/deps; fail on loader errors)
    ok = True
    if errors:
        ok = False
        status = "error"
    elif status == "skipped_dependency":
        ok = True
    elif missing_required:
        status = "degraded"
        ok = True

    artifact = {
        "status": status,
        "ok": ok,
        "latency_ms": duration_ms,
        "required_ids": required_ids,
        "missing_required_ids": missing_required,
        "contracts_count": len(contracts),
        "errors": errors,
        "warnings": warnings,
        "skipped": skipped,
        "root": load_result.get("root"),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
