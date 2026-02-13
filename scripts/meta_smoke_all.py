#!/usr/bin/env python3
"""Meta-smoke: run all smokes and generate unified artifact."""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# Define known smokes with their scripts and timeout
SMOKES = {
    "boot_import": {
        "script": "scripts/boot_import_smoke.py",
        "artifact": "artifacts/boot_import_smoke.json",
        "timeout": 30,
        "hard_failure": True,  # Must pass
    },
    "legacy_imports": {
        "script": "scripts/legacy_imports_smoke.py",
        "artifact": "artifacts/legacy_imports_smoke.json",
        "timeout": 10,
        "hard_failure": False,
    },
    "openai_router": {
        "script": "scripts/openai_router_smoke.py",
        "artifact": "artifacts/openai_router_smoke.json",
        "timeout": 30,
        "hard_failure": False,
    },
    "observability": {
        "script": "scripts/observability_smoke.py",
        "artifact": "artifacts/observability_smoke.json",
        "timeout": 30,
        "hard_failure": False,
    },
    "work_compiler": {
        "script": "scripts/work_compiler_smoke.py",
        "artifact": "artifacts/work_compiler_smoke.json",
        "timeout": 15,
        "hard_failure": False,
    },
    "gate_smoke": {
        "script": "scripts/phase10_gate_smoke.py",
        "artifact": "phase10_gate_smoke.json",
        "timeout": 60,
        "hard_failure": False,
    },
    "capabilities_registry": {
        "script": "scripts/phase6_capabilities_registry_smoke.py",
        "artifact": "artifacts/api/phase6_capabilities_registry_smoke.json",
        "timeout": 60,
        "hard_failure": False,
    },
}

def run_smoke(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single smoke test."""
    result = {
        "name": name,
        "ok": False,
        "status": "unknown",
        "reason": None,
        "duration_ms": 0,
        "artifact_exists": False,
    }
    
    start_time = time.time()
    
    try:
        # Run smoke script
        proc = subprocess.run(
            [sys.executable, config["script"], config["artifact"]],
            timeout=config["timeout"],
            capture_output=True,
            text=True,
        )
        
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        result["exit_code"] = proc.returncode
        
        # Check if artifact was created
        artifact_path = Path(config["artifact"])
        if artifact_path.exists():
            result["artifact_exists"] = True
            try:
                with artifact_path.open() as f:
                    artifact_data = json.load(f)
                result["artifact_ok"] = artifact_data.get("ok", False)
                result["artifact_overall_success"] = artifact_data.get("overall_success", False)
            except Exception:
                result["artifact_ok"] = False
                result["artifact_overall_success"] = False
        else:
            result["artifact_ok"] = False
            result["artifact_overall_success"] = False
        
        # Determine status
        if proc.returncode == 0 and result.get("artifact_ok", False):
            result["ok"] = True
            result["status"] = "passed"
        elif proc.returncode != 0:
            result["status"] = "failed"
            result["reason"] = f"Exit code {proc.returncode}: {proc.stderr[:200]}"
        else:
            result["status"] = "failed"
            result["reason"] = "Artifact not ok"
            
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["reason"] = f"Timeout after {config['timeout']}s"
        result["duration_ms"] = int((time.time() - start_time) * 1000)
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
    
    return result

def main():
    """Run all smokes and generate unified artifact."""
    artifact = {
        "ok": False,
        "reason": None,
        "timestamp_utc": time.time(),
        "smokes": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "hard_failures": 0,
        },
        "overall_success": False,
    }
    
    # Run all smokes
    for name, config in SMOKES.items():
        result = run_smoke(name, config)
        artifact["smokes"].append(result)
        
        # Update summary
        artifact["summary"]["total"] += 1
        if result["status"] == "passed":
            artifact["summary"]["passed"] += 1
        elif result["status"] in ["failed", "timeout", "error"]:
            artifact["summary"]["failed"] += 1
            if config["hard_failure"]:
                artifact["summary"]["hard_failures"] += 1
        else:
            artifact["summary"]["skipped"] += 1
    
    # Determine overall success
    if artifact["summary"]["hard_failures"] > 0:
        artifact["ok"] = False
        artifact["reason"] = f"Hard failures: {artifact['summary']['hard_failures']}"
        artifact["overall_success"] = False
    elif artifact["summary"]["failed"] > 0:
        artifact["ok"] = True  # Compilation successful, but some failures
        artifact["reason"] = f"Some failures: {artifact['summary']['failed']}"
        artifact["overall_success"] = False
    else:
        artifact["ok"] = True
        artifact["reason"] = "All smokes passed"
        artifact["overall_success"] = True
    
    # Write artifact
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/smoke_all.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)
    
    print(f"Smoke all completed: {artifact['summary']}")
    print(f"Artifact: {out_path}")
    
    sys.exit(0 if artifact["overall_success"] else 1)

if __name__ == "__main__":
    main()
