#!/usr/bin/env python3
"""Meta-smoke: run all smokes and generate unified artifact."""

import argparse
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
        "severity": "critical",  # Must pass
    },
    "legacy_imports": {
        "script": "scripts/legacy_imports_smoke.py",
        "artifact": "artifacts/legacy_imports_smoke.json",
        "timeout": 10,
        "severity": "optional",
    },
    "openai_router": {
        "script": "scripts/openai_router_smoke.py",
        "artifact": "artifacts/openai_router_smoke.json",
        "timeout": 30,
        "severity": "optional",
    },
    "observability": {
        "script": "scripts/observability_smoke.py",
        "artifact": "artifacts/observability_smoke.json",
        "timeout": 30,
        "severity": "optional",
    },
    "work_compiler": {
        "script": "scripts/work_compiler_smoke.py",
        "artifact": "artifacts/work_compiler_smoke.json",
        "timeout": 15,
        "severity": "optional",
    },
    "gate_smoke": {
        "script": "scripts/phase10_gate_smoke.py",
        "artifact": "phase10_gate_smoke.json",
        "timeout": 60,
        "severity": "optional",
    },
    "capabilities_registry": {
        "script": "scripts/phase6_capabilities_registry_smoke.py",
        "artifact": "artifacts/api/phase6_capabilities_registry_smoke.json",
        "timeout": 60,
        "severity": "optional",
        "use_out_json_flag": True,
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
        cmd = [sys.executable, config["script"]]
        if config.get("use_out_json_flag"):
            cmd.extend(["--out-json", config["artifact"]])
        else:
            cmd.append(config["artifact"])
        env = {"PYTHONPATH": ".", "DISABLE_OBSERVABILITY": "1", **os.environ}
        proc = subprocess.run(
            cmd,
            timeout=config["timeout"],
            capture_output=True,
            text=True,
            env=env,
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
                result["artifact_overall_success"] = artifact_data.get(
                    "overall_success", False
                )
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
    parser = argparse.ArgumentParser(description="Meta Smoke - Run all smoke tests")
    parser.add_argument(
        "--strict-100",
        action="store_true",
        help="Require 100% pass rate - no partial success",
    )
    parser.add_argument("--out-json", type=str, default=None, help="Output JSON path")
    parser.add_argument(
        "extra_arg",
        nargs="?",
        default=None,
        help="Legacy positional arg (artifact path)",
    )
    args = parser.parse_args()

    # Determine output path
    if args.out_json:
        out_path = Path(args.out_json)
    elif args.extra_arg:
        out_path = Path(args.extra_arg)
    else:
        out_path = Path("artifacts/smoke_all.json")

    strict_100 = args.strict_100

    artifact = {
        "ok": False,
        "status": "partial",
        "releaseable": True,
        "strict_100": strict_100,
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "pass_rate": 0.0,
            "hard_failures": 0,
        },
        "tests": [],
        "timestamp_utc": time.time(),
        "overall_success": False,
    }

    # Run all smokes
    for name, config in SMOKES.items():
        result = run_smoke(name, config)
        artifact["tests"].append(result)

        # Update summary
        artifact["summary"]["total"] += 1
        if result["status"] == "passed":
            artifact["summary"]["passed"] += 1
        elif result["status"] in ["failed", "timeout", "error"]:
            artifact["summary"]["failed"] += 1
            if config.get("severity") == "critical":
                artifact["summary"]["hard_failures"] += 1
        else:
            artifact["summary"]["skipped"] += 1

    # Calculate pass rate
    total = artifact["summary"]["total"]
    passed = artifact["summary"]["passed"]
    artifact["summary"]["pass_rate"] = passed / total if total > 0 else 0.0

    # Determine overall success and releaseable
    hard_failures = artifact["summary"]["hard_failures"]
    pass_rate = artifact["summary"]["pass_rate"]

    if strict_100:
        # STRICT MODE: 100% required - no exceptions
        artifact["overall_success"] = passed == total
        artifact["releaseable"] = passed == total
    else:
        # LENIENT MODE: allow some failures (legacy)
        artifact["overall_success"] = passed == total
        artifact["releaseable"] = hard_failures == 0 and pass_rate >= 0.7

    # Set ok based on releaseable
    artifact["ok"] = artifact["releaseable"]

    # Update status
    if artifact["overall_success"]:
        artifact["status"] = "ok"
    elif artifact["releaseable"]:
        artifact["status"] = "degraded"
    else:
        artifact["status"] = "failed"

    # Write artifact
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(artifact, f, indent=2)

    print(f"Smoke all completed: {artifact['summary']}")
    print(f"Artifact: {out_path}")
    print(f"Strict 100%: {strict_100}")

    # Exit code: 0 only if 100% green in strict mode
    exit_code = (
        0
        if (strict_100 and passed == total)
        else (0 if artifact["overall_success"] else 1)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
