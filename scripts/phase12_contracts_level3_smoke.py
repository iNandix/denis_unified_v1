#!/usr/bin/env python3
"""Phase 1: Contracts Level 3 smoke test."""

import json
import os
import sys
import time
from pathlib import Path

# Add REPO_REAL to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from denis_unified_v1.contracts.loader import load_contracts

def main():
    artifacts_dir = Path("artifacts/contracts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    result = load_contracts()
    latency = (time.perf_counter() - start) * 1000

    if result["status"] in ["ok", "degraded"]:
        status = "ok"
    else:
        status = result["status"]

    artifact = {
        "status": status,
        "latency_ms": latency,
        "contracts_loaded": len(result["contracts"]),
        "errors": result["errors"],
        "warnings": result["warnings"],
        "skipped": result["skipped"],
        "root": result["root"]
    }

    with open(artifacts_dir / "level3_metacognitive_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    if status not in ["ok", "degraded"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
