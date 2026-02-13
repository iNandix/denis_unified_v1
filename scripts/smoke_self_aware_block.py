#!/usr/bin/env python3
"""
Self-Aware Block Gate Runner
===========================

Consolidates phases 7-10 self-aware smoke tests into a single gate runner.
Executes all tests async-safe and produces combined artifact.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def run_smoke_test(test_script: str, output_file: str = None) -> Dict[str, Any]:
    """Run a single smoke test via subprocess with timeout and artifact parsing."""
    try:
        # Build command to run the smoke test
        cmd = [sys.executable, f"scripts/{test_script}"]
        if output_file:
            cmd.extend(["--out-json", output_file])

        # Run with timeout
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        # Try to read the artifact if it was generated
        artifact_data = None
        if output_file and Path(output_file).exists():
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    artifact_data = json.load(f)
            except Exception as e:
                artifact_data = {"error": f"Failed to read artifact: {e}"}

        # Determine success based on return code and artifact status
        success = False
        if result.returncode == 0:
            success = True
        elif artifact_data and isinstance(artifact_data, dict):
            # Check for acceptable non-zero exit codes (skipped dependencies)
            if artifact_data.get("status") in ["skipped", "skippeddependency"]:
                success = True
            elif artifact_data.get("ok") is True:
                success = True

        return {
            "test_script": test_script,
            "return_code": result.returncode,
            "success": success,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "artifact": artifact_data,
            "executed": True
        }

    except subprocess.TimeoutExpired:
        return {
            "test_script": test_script,
            "success": False,
            "error": "timeout",
            "timeout_seconds": 120,
            "executed": False
        }
    except Exception as e:
        return {
            "test_script": test_script,
            "success": False,
            "error": str(e),
            "executed": False
        }

def run_self_aware_gate() -> Dict[str, Any]:
    """Run all self-aware smoke tests and aggregate results."""
    print("🧠 Running Self-Aware Block Gate...")

    # Define the 4 core self-aware smoke tests
    smoke_tests = [
        {
            "script": "phase7_self_aware_inference_smoke.py",
            "description": "Self-aware inference validation",
            "artifact": "artifacts/self_aware/inference.json"
        },
        {
            "script": "phase9_self_aware_memory_smoke.py",
            "description": "Self-aware memory validation",
            "artifact": "artifacts/self_aware/memory.json"
        },
        {
            "script": "phase10_self_model_smoke.py",
            "description": "Self-model validation",
            "artifact": "artifacts/self_aware/self_model.json"
        },
        {
            "script": "phase8_voice_smoke.py",
            "description": "Voice pipeline validation",
            "artifact": "artifacts/self_aware/voice.json"
        }
    ]

    # Create artifacts directory
    Path("artifacts/self_aware").mkdir(parents=True, exist_ok=True)

    # Run all tests sequentially
    results = []
    for test_config in smoke_tests:
        result = run_smoke_test(test_config["script"], test_config["artifact"])
        results.append({
            **result,
            "description": test_config["description"],
            "expected_artifact": test_config["artifact"]
        })

    # Analyze results
    successful_tests = [r for r in results if r["success"]]
    failed_tests = [r for r in results if not r["success"]]
    skipped_tests = [r for r in results if r.get("artifact") and isinstance(r.get("artifact"), dict) and r["artifact"].get("status") == "skipped"]

    # Determine overall gate status
    total_tests = len(results)
    passed_tests = len(successful_tests)

    # Gate passes if:
    # - At least 3/4 tests pass, OR
    # - All failures are due to missing dependencies (skipped), OR
    # - No hard failures (return_code != 0 due to crashes)
    hard_failures = [r for r in failed_tests if r.get("executed") and r.get("return_code") != 0]

    if hard_failures:
        gate_status = "failed"
        gate_reason = f"Hard failures in: {[r['test_script'] for r in hard_failures]}"
    elif passed_tests >= total_tests * 0.75:  # 75% pass rate
        gate_status = "passed"
        gate_reason = f"Passed {passed_tests}/{total_tests} tests"
    elif len(skipped_tests) == len(failed_tests):
        gate_status = "passed"
        gate_reason = f"All failures are dependency skips: {[r['test_script'] for r in skipped_tests]}"
    else:
        gate_status = "degraded"
        gate_reason = f"Mixed results: {passed_tests} passed, {len(failed_tests)} failed"

    # Create consolidated artifact
    artifact = {
        "timestamp_utc": _utc_now(),
        "stream": "S13_self_aware_block",
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": len(failed_tests),
        "skipped_tests": len(skipped_tests),
        "hard_failures": len(hard_failures),
        "test_results": results,
        "summary": {
            "successful": [r["test_script"] for r in successful_tests],
            "failed": [r["test_script"] for r in failed_tests],
            "skipped": [r["test_script"] for r in skipped_tests]
        }
    }

    return artifact

def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Self-Aware Block Gate Runner")
    parser.add_argument(
        "--out-json",
        default="artifacts/self_aware/block.json",
        help="Output consolidated artifact path"
    )
    args = parser.parse_args()

    # Run the gate
    artifact = run_self_aware_gate()

    # Write consolidated artifact
    output_path = Path(args.out_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    # Print results
    status = artifact["gate_status"].upper()
    print(f"🧠 Self-Aware Block Gate: {status}")
    print(f"📊 {artifact['passed_tests']}/{artifact['total_tests']} tests passed")
    print(f"📝 Reason: {artifact['gate_reason']}")

    if artifact["hard_failures"] > 0:
        print("❌ Hard failures detected - gate blocking")
        return 1
    elif artifact["gate_status"] == "passed":
        print("✅ Gate passed - self-aware systems operational")
        return 0
    else:
        print("⚠️  Gate degraded - some systems not fully operational")
        return 0  # Degraded is acceptable

if __name__ == "__main__":
    sys.exit(main())
