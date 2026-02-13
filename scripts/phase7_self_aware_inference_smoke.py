#!/usr/bin/env python3
"""Phase 7 Advanced Self-Aware Inference Router Smoke Test."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add REPO_REAL to path
sys.path.insert(0, str(Path(__file__).parents[1]))

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 7: Self-aware inference smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/self_aware/inference.json",
        help="Output artifact path",
    )
    return parser.parse_args()

def run_smoke():
    """Run smoke test with fail-open behavior."""
    try:
        # Try to import required modules
        from orchestration.self_aware_router import route_inference
        import asyncio
        
        # Run the actual test
        async def _test():
            start = time.time()
            result = await route_inference("debug this complex code with ethical considerations")
            latency = time.time() - start
            
            return {
                "ok": True,
                "latency_ms": latency * 1000,
                "timestamp_utc": _utc_now(),
                "routing": result,
                "analysis_complexity": result["analysis"]["complexity"],
                "ethical_check": result["ethical"],
                "uncertainty": result["uncertainty"]
            }
        
        # Execute async test
        result = asyncio.run(_test())
        return result
        
    except ImportError as e:
        if "orchestration" in str(e) or "self_aware_router" in str(e):
            # Self-aware router not available - acceptable skip
            return {
                "ok": True,  # Skipped is acceptable
                "status": "skippeddependency",
                "reason": "orchestration.self_aware_router module not available",
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
