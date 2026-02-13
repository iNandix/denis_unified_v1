#!/usr/bin/env python3
"""
DENIS Maintainer CLI - Fix one issue at a time with strict discipline.

Usage:
    denis fix --one        # Fix exactly one failure
    denis doctor           # Diagnose without fixing
    denis status           # Show current status
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS_DIR = Path("scripts")
ARTIFACTS_DIR = Path("artifacts")
ATTEMPTS_DIR = ARTIFACTS_DIR / "attempts"


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default


def run_command(cmd: list, timeout: int = 120, check: bool = False) -> dict:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path.cwd(),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "returncode": -1}
    except Exception as e:
        return {"success": False, "error": str(e), "returncode": -1}


def run_meta_smoke_strict() -> dict:
    """Run meta-smoke with strict 100% requirement."""
    print("\n[1/5] Running meta-smoke (strict-100)...")

    cmd = [
        sys.executable,
        "scripts/meta_smoke_all.py",
        "--strict-100",
        "--out-json",
        "artifacts/smoke_all.json",
    ]

    result = run_command(cmd, timeout=300)

    artifact = load_json(ARTIFACTS_DIR / "smoke_all.json", {})
    return {
        "result": result,
        "artifact": artifact,
        "passed": artifact.get("summary", {}).get("passed", 0),
        "total": artifact.get("summary", {}).get("total", 0),
        "passed_ratio": artifact.get("summary", {}).get("pass_rate", 0),
    }


def select_best_failure(artifact: dict) -> dict:
    """Select best failure to fix using deterministic rules."""
    tests = artifact.get("tests", [])
    failures = [t for t in tests if not t.get("ok", True)]

    if not failures:
        return None

    priority_rules = [
        ("syntax_error", ["SyntaxError", "py_compile", "can't compile"]),
        ("server_fails", ["server", "start", "boot"]),
        ("cli_args", ["unrecognized", "argument", "args"]),
        ("timeout", ["timeout", "Timeout"]),
        ("import_error", ["ImportError", "ModuleNotFoundError", "import"]),
        ("openai_endpoints", ["models_endpoint", "chat_endpoint", "router"]),
    ]

    selected = None
    selected_rule = None

    for rule_name, keywords in priority_rules:
        for failure in failures:
            reason = failure.get("reason", "").lower()
            name = failure.get("name", "").lower()

            if any(kw.lower() in reason or kw.lower() in name for kw in keywords):
                selected = failure
                selected_rule = rule_name
                break

        if selected:
            break

    if not selected and failures:
        selected = failures[0]
        selected_rule = "first_by_order"

    return {
        "failure": selected,
        "rule": selected_rule,
        "total_failures": len(failures),
    }


def analyze_failure(failure: dict) -> dict:
    """Analyze a specific failure and generate fix plan."""
    name = failure.get("name", "unknown")
    reason = failure.get("reason", "no reason")
    status = failure.get("status", "unknown")

    analysis = {
        "name": name,
        "reason": reason,
        "status": status,
        "fix_suggestions": [],
    }

    if "unrecognized" in reason.lower() or "argument" in reason.lower():
        analysis["fix_suggestions"].append(
            "Check CLI args in smoke script - remove invalid arguments"
        )
        analysis["fix_suggestions"].append(
            "Ensure smoke accepts --out-json and --help without errors"
        )

    if "timeout" in reason.lower():
        analysis["fix_suggestions"].append(
            "Increase timeout or fix deadlock in the component"
        )
        analysis["fix_suggestions"].append("Check for infinite loops or blocking I/O")

    if "import" in reason.lower() or "ModuleNotFoundError" in reason:
        analysis["fix_suggestions"].append("Fix missing dependency or import path")
        analysis["fix_suggestions"].append("Check PYTHONPATH and module structure")

    if "models_endpoint" in name or "chat_endpoint" in name:
        analysis["fix_suggestions"].append(
            "Fix OpenAI router endpoints - return valid 200 responses"
        )
        analysis["fix_suggestions"].append(
            "If degraded, return 200 with degraded=true in payload"
        )

    if not analysis["fix_suggestions"]:
        analysis["fix_suggestions"].append(f"Investigate: {reason}")
        analysis["fix_suggestions"].append("Run smoke individually to see full error")

    return analysis


def run_single_smoke(smoke_name: str) -> dict:
    """Run a single smoke test."""
    smoke_map = {
        "boot_import": "scripts/boot_import_smoke.py",
        "controlplane_status": "scripts/controlplane_status_smoke.py",
        "openai_router": "scripts/openai_router_smoke.py",
        "legacy_imports": "scripts/legacy_imports_smoke.py",
        "capabilities_registry": "scripts/phase6_capabilities_registry_smoke.py",
    }

    if smoke_name not in smoke_map:
        return {"success": False, "error": f"Unknown smoke: {smoke_name}"}

    script = smoke_map[smoke_name]
    out_json = f"artifacts/{smoke_name}_smoke.json"

    cmd = [sys.executable, script, "--out-json", out_json]
    result = run_command(cmd, timeout=120)

    artifact = load_json(Path(out_json), {})
    return {"result": result, "artifact": artifact}


def revert_changes():
    """Revert all changes."""
    print("\n[!] Reverting changes...")
    run_command(["git", "checkout", "."], timeout=30)


def commit_if_green(passed: int, total: int) -> bool:
    """Commit only if 100% green."""
    if passed == total and passed > 0:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        run_command(["git", "add", "-A"], timeout=30)

        msg = f"fix(smoke): strict-100 green ({passed}/{total})"
        result = run_command(["git", "commit", "-m", msg], timeout=30)

        if result["success"]:
            print(f"\n✅ COMMITTED: {msg}")
            return True
        else:
            print(f"\n❌ Commit failed: {result.get('stderr', 'unknown')}")
            return False
    return False


def save_attempt_record(selection: dict, analysis: dict, before: dict, after: dict):
    """Save attempt record for evidence."""
    ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selection": selection,
        "analysis": analysis,
        "before": before,
        "after": after,
    }

    path = ATTEMPTS_DIR / f"fix_one_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(record, f, indent=2)

    print(f"\n📄 Attempt record: {path}")
    return path


def denis_doctor():
    """Diagnose without fixing."""
    print("=" * 60)
    print("🔍 DENIS DOCTOR - Diagnosis Mode")
    print("=" * 60)

    result = run_meta_smoke_strict()

    artifact = result["artifact"]
    passed = result["passed"]
    total = result["total"]

    print(f"\n📊 Result: {passed}/{total} passed")

    if passed == total:
        print("\n✅ ALL GREEN - No issues found!")
        return 0

    selection = select_best_failure(artifact)
    failure = selection.get("failure", {})

    print(f"\n❌ FAILURES: {selection.get('total_failures', 0)}")
    print(f"   Selected: {failure.get('name')} ({selection.get('rule')})")
    print(f"   Reason: {failure.get('reason')}")

    analysis = analyze_failure(failure)
    print(f"\n🔧 SUGGESTED FIX:")
    for i, suggestion in enumerate(analysis["fix_suggestions"], 1):
        print(f"   {i}. {suggestion}")

    return 1


def denis_fix_one():
    """Fix exactly one failure."""
    print("=" * 60)
    print("🔧 DENIS FIX --ONE - Strict Mode")
    print("=" * 60)

    result = run_meta_smoke_strict()

    artifact = result["artifact"]
    passed = result["passed"]
    total = result["total"]

    before_state = {
        "passed": passed,
        "total": total,
        "passed_ratio": result["passed_ratio"],
    }

    if passed == total:
        print(f"\n✅ Already green ({passed}/{total}) - Nothing to fix!")
        return 0

    selection = select_best_failure(artifact)
    failure = selection.get("failure", {})

    print(f"\n❌ Selecting failure: {failure.get('name')}")
    print(f"   Rule: {selection.get('rule')}")
    print(f"   Reason: {failure.get('reason')}")

    analysis = analyze_failure(failure)

    print(f"\n🔧 ANALYSIS:")
    for i, suggestion in enumerate(analysis["fix_suggestions"], 1):
        print(f"   {i}. {suggestion}")

    print(f"\n⚠️  MANUAL INTERVENTION REQUIRED")
    print(f"   DENIS cannot auto-fix. Please:")
    print(f"   1. Run the failing smoke manually to see full error")
    print(f"   2. Apply the fix")
    print(f"   3. Run: denis fix --one again")

    save_attempt_record(
        selection, analysis, before_state, {"status": "manual_required"}
    )

    return 1


def denis_status():
    """Show current status."""
    print("=" * 60)
    print("📊 DENIS STATUS")
    print("=" * 60)

    artifact = load_json(ARTIFACTS_DIR / "smoke_all.json", {})
    summary = artifact.get("summary", {})

    print(f"\nSmoke Results:")
    print(f"  Passed: {summary.get('passed', 0)}/{summary.get('total', 0)}")
    print(f"  Failed: {summary.get('failed', 0)}")
    print(f"  Pass Rate: {(summary.get('pass_rate', 0) * 100):.1f}%")

    gate = load_json(ARTIFACTS_DIR / "control_plane/supervisor_gate.json", {})
    print(f"\nGate Status:")
    print(f"  Releaseable: {gate.get('ok', False)}")
    print(f"  Blocked by: {gate.get('policy', {}).get('blocked_by', [])}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="DENIS Maintainer CLI")
    parser.add_argument(
        "command", choices=["doctor", "fix", "status"], help="Command to run"
    )
    parser.add_argument(
        "--one", action="store_true", help="Fix exactly one (for fix command)"
    )

    args = parser.parse_args()

    if args.command == "doctor":
        return denis_doctor()
    elif args.command == "fix":
        return denis_fix_one() if args.one else denis_fix_one()
    elif args.command == "status":
        return denis_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
