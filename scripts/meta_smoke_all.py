#!/usr/bin/env python3
"""
Meta-smoke: run all smokes and generate unified artifact.

HARDENED VERSION - Anti-agent cheat:
- py_compile check before running any smoke
- Emergency artifact if smoke crashes
- Proper env override
"""

import argparse
import glob
import json
import os
import py_compile
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Any


# Compile check - fail fast if any script has syntax errors
def check_all_scripts_compile():
    """Compile all smoke scripts before running - fail fast on syntax errors."""
    scripts = glob.glob("scripts/*smoke*.py")
    scripts.extend(glob.glob("scripts/meta_smoke*.py"))
    scripts.extend(glob.glob("scripts/supervisor*.py"))
    scripts.extend(glob.glob("scripts/denis*.py"))

    errors = []
    for script in scripts:
        try:
            py_compile.compile(script, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{script}: {e}")

    if errors:
        print("=== COMPILE ERRORS ===")
        for err in errors:
            print(f"  - {err}")
        return False
    return True


# Define known smokes with their scripts and timeout
SMOKES = {
    "boot_import": {
        "script": "scripts/boot_import_smoke.py",
        "artifact": "artifacts/boot_import_smoke.json",
        "timeout": 30,
        "severity": "critical",
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


def write_emergency_artifact(path: Path, reason: str, details: str = ""):
    """Write emergency artifact if smoke crashes."""
    artifact = {
        "ok": False,
        "status": "crashed",
        "reason": reason,
        "details": details[:1000] if details else "",
        "timestamp_utc": time.time(),
        "overall_success": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(artifact, f, indent=2)
    return artifact


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
        # Build command
        cmd = [sys.executable, config["script"]]
        if config.get("use_out_json_flag"):
            cmd.extend(["--out-json", config["artifact"]])
        else:
            cmd.append(config["artifact"])

        # CRITICAL: Proper env override - os.environ comes first, then our values
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": ".",
                "DISABLE_OBSERVABILITY": "1",
                "DENIS_API_BEARER_TOKEN": "",
            }
        )

        proc = subprocess.run(
            cmd,
            timeout=config["timeout"],
            capture_output=True,
            text=True,
            env=env,
        )

        result["duration_ms"] = int((time.time() - start_time) * 1000)
        result["exit_code"] = proc.returncode
        result["stdout_tail"] = proc.stdout[-500:] if proc.stdout else ""
        result["stderr_tail"] = proc.stderr[-500:] if proc.stderr else ""

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
            except Exception as e:
                result["artifact_ok"] = False
                result["artifact_read_error"] = str(e)
        else:
            result["artifact_ok"] = False
            result["artifact_missing"] = True

        # Determine status based on exit code AND artifact
        if proc.returncode == 0 and result.get("artifact_ok", False):
            result["ok"] = True
            result["status"] = "passed"
        elif proc.returncode != 0:
            result["status"] = "failed"
            result["reason"] = (
                f"Exit code {proc.returncode}: {proc.stderr[:200] if proc.stderr else 'no stderr'}"
            )
        elif not result.get("artifact_ok", True):
            result["status"] = "failed"
            result["reason"] = "Artifact exists but ok=false"
        else:
            result["status"] = "failed"
            result["reason"] = "Unknown failure"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["reason"] = f"Timeout after {config['timeout']}s"
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        # Write emergency artifact
        write_emergency_artifact(
            Path(config["artifact"]),
            "timeout",
            f"Smoke timed out after {config['timeout']}s",
        )
    except Exception as e:
        result["status"] = "crashed"
        result["reason"] = f"Exception: {str(e)[:200]}"
        result["traceback"] = traceback.format_exc()[:500]
        # Write emergency artifact
        write_emergency_artifact(
            Path(config["artifact"]),
            f"crash: {type(e).__name__}",
            traceback.format_exc()[:1000],
        )

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
        "extra_arg", nargs="?", default=None, help="Legacy positional arg"
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

    # STEP 1: Compile check - fail fast on syntax errors
    print("=== STEP 1: Compiling all scripts ===")
    if not check_all_scripts_compile():
        print("COMPILE FAILURE - Cannot proceed")
        # Write emergency artifact
        artifact = {
            "ok": False,
            "status": "compile_failed",
            "releaseable": False,
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
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        with tmp_path.open("w") as f:
            json.dump(artifact, f, indent=2, ensure_ascii=False)
        tmp_path.replace(out_path)
        print(f"Artifact written to: {out_path}")
        sys.exit(1)

    print("Compile check PASSED")

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
        elif result["status"] in ["failed", "timeout", "crashed"]:
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
        # LENIENT MODE: allow some failures
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
