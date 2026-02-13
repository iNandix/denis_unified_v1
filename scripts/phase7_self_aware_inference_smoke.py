#!/usr/bin/env python3
"""Phase 7 Advanced Self-Aware Inference Router Smoke Test."""

import json
import os
import asyncio
import time
from pathlib import Path

# Add REPO_REAL to path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from orchestration.self_aware_router import route_inference


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def main():
    os.makedirs("artifacts/inference", exist_ok=True)

    start = time.time()
    result = await route_inference("debug this complex code with ethical considerations")
    latency = time.time() - start

    artifact = {
        "ok": True,
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "routing": result,
        "analysis_complexity": result["analysis"]["complexity"],
        "ethical_check": result["ethical"],
        "uncertainty": result["uncertainty"]
    }

    with open("artifacts/inference/phase7_self_aware_inference_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    print("Smoke passed")

if __name__ == "__main__":
    asyncio.run(main())
