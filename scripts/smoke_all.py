#!/usr/bin/env python3
"""Meta Smoke - Run all critical smoke tests and produce consolidated artifact.

This smoke runs key smoke tests to verify system health:
- boot_import_smoke
- phase6_capabilities_registry_smoke
- phase10_gate_smoke
- legacy_imports_smoke
- route_sanity_smoke

Output: artifacts/smoke_all.json with overall system status.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Meta smoke - run all critical smoke tests"
    )
    parser.add_argument(
        "--out-json", default="artifacts/smoke_all.json", help="Output artifact path"
    )
    return parser.parse_args()


SMOKE_TESTS = [
    {
        "name": "boot_import",
        "script": "scripts/boot_import_smoke.py",
        "artifact": "artifacts/boot_import_smoke.json",
    },
    {
        "name": "capabilities",
        "script": "scripts/phase6_capabilities_registry_smoke.py",
        "artifact": "artifacts/api/phase6_capabilities_registry_smoke.json",
    },
    {
        "name": "gate",
        "script": "scripts/phase10_gate_smoke.py",
        "artifact": "artifacts/phase10_gate_smoke.json",
    },
    {
        "name": "legacy_imports",
        "script": "scripts/legacy_imports_smoke.py",
        "artifact": "artifacts/legacy_imports_smoke.json",
    },
    {
        "name": "routes",
        "script": "scripts/route_sanity_smoke.py",
        "artifact": "artifacts/api/route_sanity_smoke.json",
    },
]


def run_smoke(script: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a single smoke test."""
    script_path = PROJECT_ROOT / script
    if not script_path.exists():
        return {
            "ok": False,
            "status": "skipped",
            "reason": f"script_not_found: {script}",
            "return_code": -1,
        }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )

        return {
            "ok": result.returncode == 0,
            "status": "passed" if result.returncode == 0 else "failed",
            "return_code": result.returncode,
            "stdout": result.stdout.decode()[:500] if result.stdout else "",
            "stderr": result.stderr.decode()[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": "timeout",
            "reason": f"timeout_after_{timeout}s",
            "return_code": -1,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "reason": str(e)[:100],
            "return_code": -1,
        }


def load_artifact(path: str) -> Dict[str, Any]:
    """Load artifact JSON."""
    artifact_path = PROJECT_ROOT / path
    if not artifact_path.exists():
        return {}
    try:
        with open(artifact_path) as f:
            return json.load(f)
    except:
        return {}


def run_meta_smoke() -> Dict[str, Any]:
    """Run all smoke tests and produce consolidated result."""
    results = []
    passed = 0
    failed = 0
    skipped = 0

    for test in SMOKE_TESTS:
        print(f"Running {test['name']}...")

        result = run_smoke(test["script"])
        result["name"] = test["name"]
        result["script"] = test["script"]
        result["artifact"] = test["artifact"]

        # Load artifact for additional context
        artifact_data = load_artifact(test["artifact"])
        if artifact_data:
            result["artifact_data"] = {
                "ok": artifact_data.get("ok", False),
                "overall_success": artifact_data.get(
                    "overall_success", artifact_data.get("ok", False)
                ),
            }

        results.append(result)

        if result["status"] == "passed":
            passed += 1
        elif result["status"] == "skipped":
            skipped += 1
        else:
            failed += 1

    # Determine overall status
    total = len(SMOKE_TESTS)
    all_passed = passed == total
    releaseable = passed >= (total * 0.7)  # 70% threshold

    return {
        "ok": all_passed,
        "status": "all_passed"
        if all_passed
        else ("partial" if releaseable else "failed"),
        "releaseable": releaseable,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": passed / total if total > 0 else 0,
        },
        "tests": results,
        "threshold": "70%",
        "timestamp_utc": _utc_now(),
    }


def main():
    args = parse_args()
    result = run_meta_smoke()

    # Write artifact
    out_path = PROJECT_ROOT / args.out_json
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    print(f"\n{'=' * 50}")
    print(f"Meta Smoke Results:")
    print(f"  Passed: {result['summary']['passed']}/{result['summary']['total']}")
    print(f"  Failed: {result['summary']['failed']}")
    print(f"  Skipped: {result['summary']['skipped']}")
    print(f"  Releaseable: {result['releaseable']}")
    print(f"{'=' * 50}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
