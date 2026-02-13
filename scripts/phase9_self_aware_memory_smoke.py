#!/usr/bin/env python3
"""Phase 9 Self-Aware Memory Smoke Test."""

import json
import os
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from memory.self_aware_memory import process_memory


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main():
    os.makedirs("artifacts/memory", exist_ok=True)

    start = time.time()
    memories = [
        {"content": "User asked about AI", "timestamp": time.time() - 3600, "access_count": 5, "last_access": time.time()},
        {"content": "Response was helpful", "timestamp": time.time() - 7200, "access_count": 2, "last_access": time.time() - 86400}
    ]
    result = process_memory(memories)
    latency = time.time() - start

    artifact = {
        "ok": True,
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "memory_processing": result
    }

    with open("artifacts/memory/phase9_self_aware_memory_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)

    print("Smoke passed")

if __name__ == "__main__":
    main()
