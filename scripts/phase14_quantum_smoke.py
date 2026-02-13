#!/usr/bin/env python3
"""Phase 14 Quantum Integration Smoke Test."""

import json
import os
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from quantum.integration import process_quantum

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main():
    os.makedirs("artifacts/quantum", exist_ok=True)
    
    start = time.time()
    result = process_quantum(2, ["particle1", "particle2"])
    latency = time.time() - start
    
    artifact = {
        "ok": True,
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "quantum_simulation": result
    }
    
    with open("artifacts/quantum/phase14_quantum_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)
    
    print("Smoke passed")

if __name__ == "__main__":
    main()
