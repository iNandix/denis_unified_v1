#!/usr/bin/env python3
"""Legacy imports smoke: verify orchestration/memory/voice shims work."""

import json
import sys
import time
from pathlib import Path

def main():
    artifact = {
        "ok": False,
        "reason": None,
        "imports": {},
        "timestamp_utc": time.time(),
        "overall_success": False,
    }

    modules = ["orchestration", "memory", "voice"]
    for mod in modules:
        try:
            __import__(mod)
            artifact["imports"][mod] = "ok"
        except Exception as e:
            artifact["imports"][mod] = f"failed: {str(e)}"

    artifact["overall_success"] = all(v == "ok" for v in artifact["imports"].values())
    artifact["ok"] = artifact["overall_success"]
    artifact["reason"] = "legacy imports ok" if artifact["ok"] else "some legacy imports failed"

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/legacy_imports_smoke.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    sys.exit(0 if artifact["ok"] else 1)

if __name__ == "__main__":
    main()
