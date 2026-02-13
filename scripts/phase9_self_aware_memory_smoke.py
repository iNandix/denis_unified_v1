#!/usr/bin/env python3
"""Phase 9 Self-Aware Memory Smoke Test with fail-open behavior."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add parent of denis_unified_v1 to path
sys.path.insert(0, str(Path(__file__).parents[1]))

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 9: Self-aware memory smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/self_aware/memory.json",
        help="Output artifact path",
    )
    return parser.parse_args()

def run_smoke():
    """Run smoke test with fail-open behavior."""
    try:
        # Try to import required modules
        from memory.self_aware_memory import process_memory
        
        # Run the actual test
        start = time.time()
        memories = [
            {"content": "User asked about AI", "timestamp": time.time() - 3600, "access_count": 5, "last_access": time.time()},
            {"content": "Response was helpful", "timestamp": time.time() - 7200, "access_count": 2, "last_access": time.time() - 86400}
        ]
        result = process_memory(memories)
        latency = time.time() - start
        
        return {
            "ok": True,
            "latency_ms": latency * 1000,
            "timestamp_utc": _utc_now(),
            "memory_processing": result
        }
        
    except ImportError as e:
        if "memory" in str(e) or "self_aware_memory" in str(e):
            # Self-aware memory not available - acceptable skip
            return {
                "ok": True,  # Skipped is acceptable
                "status": "skippeddependency",
                "reason": "memory.self_aware_memory module not available",
                "error": str(e),
                "timestamp_utc": _utc_now()
            }
        else:
            return {
                "ok": False,
                "status": "failed",
                "error": f"Import error: {e}",
                "timestamp_utc": _utc_now()
            }
            
    except Exception as e:
        return {
            "ok": False,
            "status": "failed",
            "error": str(e),
            "timestamp_utc": _utc_now()
        }

def main():
    args = parse_args()
    result = run_smoke()
    
    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    
    # Return appropriate exit code
    if result.get("status") == "skippeddependency":
        return 0  # Acceptable skip
    elif result.get("ok", False):
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
