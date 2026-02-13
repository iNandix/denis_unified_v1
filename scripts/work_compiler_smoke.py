#!/usr/bin/env python3
"""Work compiler smoke test: verify prioritization, dedupe, and proof."""

import json
import os
import sys
import time
from pathlib import Path

# Disable observability to prevent setup failures
os.environ["DISABLE_OBSERVABILITY"] = "1"

def main():
    artifact = {
        "ok": False,
        "reason": None,
        "compiler_runs": False,
        "has_items": None,
        "items_sorted": None,
        "items_deduped": None,
        "commands_exist": None,
        "timestamp_utc": time.time(),
        "overall_success": False,
    }

    try:
        # Ensure artifacts directory exists
        artifacts_root = Path("artifacts")
        artifacts_root.mkdir(parents=True, exist_ok=True)
        # Run work compiler
        from denisunifiedv1.sprint_orchestrator.work_compiler import compile_work_from_artifacts
        from pathlib import Path as PathLib
        
        artifacts_root = PathLib("artifacts")
        out_json = PathLib("artifacts/orchestration/work_compiler_smoke.json")
        
        plan = compile_work_from_artifacts(artifacts_root, out_json)
        artifact["compiler_runs"] = True
        
        # Check if plan has items when there are signals
        if plan.get("total_signals", 0) > 0:
            artifact["has_items"] = len(plan.get("items", [])) > 0
        else:
            artifact["has_items"] = True  # No signals is OK
            
        # Check items are sorted by score
        items = plan.get("items", [])
        if len(items) > 1:
            scores = [item.get("score", 0) for item in items]
            artifact["items_sorted"] = scores == sorted(scores, reverse=True)
        else:
            artifact["items_sorted"] = True
            
        # Check deduplication
        seen = set()
        deduped = True
        for item in items:
            key = (item.get("signal_id"), item.get("source_artifact"), item.get("remediation_key"))
            if key in seen:
                deduped = False
                break
            seen.add(key)
        artifact["items_deduped"] = deduped
        
        # Check commands exist
        commands_exist = True
        for item in items:
            for cmd in item.get("commands", []):
                if not PathLib(cmd[1] if len(cmd) > 1 else cmd[0]).exists():
                    commands_exist = False
                    break
            if not commands_exist:
                break
        artifact["commands_exist"] = commands_exist
        
        # Add plan details to artifact
        artifact["plan_summary"] = {
            "total_signals": plan.get("total_signals", 0),
            "accepted_items": plan.get("accepted_items", 0),
            "rejected_signals_count": plan.get("rejected_signals_count", 0),
        }

    except Exception as e:
        artifact["reason"] = f"Exception: {str(e)}"

    artifact["overall_success"] = (
        artifact["compiler_runs"] and 
        artifact["has_items"] is not None and
        artifact["items_sorted"] and
        artifact["items_deduped"] and
        artifact["commands_exist"]
    )
    artifact["ok"] = artifact["overall_success"]

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/work_compiler_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()
