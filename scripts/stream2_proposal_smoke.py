#!/usr/bin/env python3
"""Phase Stream 2 Proposal System Smoke Test."""

import json
import os
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from proposal_engine.advanced_proposals import process_proposal

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def main():
    os.makedirs("artifacts/proposals", exist_ok=True)
    
    start = time.time()
    code_diff = "add logging to function"
    result = process_proposal(code_diff)
    latency = time.time() - start
    
    artifact = {
        "ok": True,
        "latency_ms": latency * 1000,
        "timestamp_utc": _utc_now(),
        "code_diff": code_diff,
        "proposal_processing": result
    }
    
    with open("artifacts/proposals/stream2_proposal_smoke.json", "w") as f:
        json.dump(artifact, f, indent=2)
    
    print("Smoke passed")

if __name__ == "__main__":
    main()
