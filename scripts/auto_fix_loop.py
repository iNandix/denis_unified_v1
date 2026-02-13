#!/usr/bin/env python3
"""
Auto-Fix Loop - Iteratively fix issues until gate passes.
This is the CORE of the "infallible" system - it doesn't allow shortcuts.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


MAX_ITERATIONS = 10


def run_gate(mode: str = "dev", timeout: int = 180) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/supervisor_gate.py",
            f"--mode={mode}",
            f"--timeout={timeout}",
        ],
        capture_output=True,
        text=True,
        timeout=timeout * 2,
    )

    gate_artifact = Path("artifacts/control_plane/supervisor_gate.json")
    if gate_artifact.exists():
        with open(gate_artifact) as f:
            return json.load(f)
    return {
        "ok": False,
        "error": "No gate artifact",
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def analyze_failures(gate_result: dict) -> list:
    """Analyze what's broken and generate fix instructions."""
    failures = []
    blocked_by = gate_result.get("policy", {}).get("blocked_by", [])
    reasons = gate_result.get("policy", {}).get("reasons", [])

    for block in blocked_by:
        if block == "boot_import":
            failures.append(
                {
                    "check": "boot_import",
                    "issue": "Boot import smoke failed - app cannot start",
                    "fix_action": "Fix import errors in api/ module. Check: missing dependencies, broken imports, syntax errors",
                    "priority": 1,
                }
            )
        elif block == "controlplane_status":
            failures.append(
                {
                    "check": "controlplane_status",
                    "issue": "Control plane status smoke failed - registry/policy broken",
                    "fix_action": "Fix denisunifiedv1/control_plane/ registry or policy. Ensure schema is valid.",
                    "priority": 1,
                }
            )
        elif block == "meta_smoke":
            failures.append(
                {
                    "check": "meta_smoke",
                    "issue": "Meta smoke test has failures",
                    "fix_action": "Run meta_smoke_all.py manually to see specific failures. Fix each failing component.",
                    "priority": 2,
                }
            )
        elif block == "work_compiler":
            failures.append(
                {
                    "check": "work_compiler",
                    "issue": "Work compiler smoke failed",
                    "fix_action": "Fix denisunifiedv1/sprint_orchestrator/work_compiler.py",
                    "priority": 2,
                }
            )
        elif block == "duplicates":
            failures.append(
                {
                    "check": "duplicates",
                    "issue": "Duplicate function/class definitions found",
                    "fix_action": "Find and deduplicate duplicate symbols using grep/ripgrep",
                    "priority": 3,
                }
            )
        elif block == "side_effects":
            failures.append(
                {
                    "check": "side_effects",
                    "issue": "Import-time side effects detected (create_app at top level)",
                    "fix_action": "Remove top-level create_app() calls in api/*.py. Move to if __name__ == '__main__'",
                    "priority": 3,
                }
            )
        elif block == "coherence":
            failures.append(
                {
                    "check": "coherence",
                    "issue": "ok/overall_status mismatch in artifacts",
                    "fix_action": "Fix artifact generation to ensure ok matches overall_status",
                    "priority": 3,
                }
            )

    return failures


def run_smoke(smoke_name: str) -> dict:
    """Run a specific smoke test and get detailed output."""
    smoke_scripts = {
        "boot_import": "scripts/boot_import_smoke.py",
        "controlplane_status": "scripts/controlplane_status_smoke.py",
        "meta_smoke": "scripts/meta_smoke_all.py",
        "work_compiler": "scripts/work_compiler_smoke.py",
    }

    if smoke_name not in smoke_scripts:
        return {"error": f"Unknown smoke: {smoke_name}"}

    result = subprocess.run(
        [sys.executable, smoke_scripts[smoke_name]],
        capture_output=True,
        text=True,
        timeout=120,
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def suggest_fixes(failures: list, gate_result: dict) -> str:
    """Generate detailed fix suggestions based on failures."""
    suggestions = []

    for failure in failures:
        check = failure["check"]
        issue = failure["issue"]

        suggestions.append(f"\n## {check.upper()} - {issue}")
        suggestions.append(f"**Priority**: {failure['priority']}")
        suggestions.append(f"**Action**: {failure['fix_action']}")

        if check in ["boot_import", "controlplane_status"]:
            smoke_result = run_smoke(check)
            suggestions.append(f"\n### Smoke Output:")
            suggestions.append(f"```\n{smoke_result.get('stdout', 'No output')}\n```")
            suggestions.append(f"```\n{smoke_result.get('stderr', 'No stderr')}\n```")

    return "\n".join(suggestions)


def auto_fix_loop(mode: str = "dev", max_iterations: int = MAX_ITERATIONS) -> dict:
    """Main auto-fix loop - iterates until gate passes."""

    print("=" * 60)
    print("AUTO-FIX LOOP STARTING")
    print("=" * 60)

    iteration = 0
    history = []

    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'=' * 60}")
        print(f"ITERATION {iteration}/{max_iterations}")
        print(f"{'=' * 60}")

        gate_result = run_gate(mode)

        artifact = {
            "iteration": iteration,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "gate_result": gate_result,
        }

        if gate_result.get("ok", False):
            print(f"\n✅ GATE PASSED at iteration {iteration}!")
            artifact["passed"] = True
            history.append(artifact)
            break

        print(f"\n❌ GATE FAILED")
        print(f"   blocked_by: {gate_result.get('policy', {}).get('blocked_by', [])}")
        print(f"   reasons: {gate_result.get('policy', {}).get('reasons', [])}")

        failures = analyze_failures(gate_result)
        suggestions = suggest_fixes(failures, gate_result)

        print(f"\n📋 FAILURES DETECTED:")
        for f in failures:
            print(f"  - {f['check']}: {f['issue']}")

        print(f"\n🔧 SUGGESTED FIXES:")
        print(suggestions)

        artifact["failures"] = failures
        artifact["suggestions"] = suggestions
        artifact["passed"] = False
        history.append(artifact)

        print(f"\n⚠️  AUTO-FIX CANNOT AUTOMATICALLY CORRECT CODE")
        print(f"   This requires manual intervention or agent action.")
        print(f"   The gate will block push/merge until fixed.")

        if iteration < max_iterations:
            print(f"\n⏳ Waiting 5s before next check...")
            time.sleep(5)

    if iteration >= max_iterations:
        print(f"\n❌ MAX ITERATIONS REACHED ({max_iterations})")
        print(f"   Gate still failing. Manual intervention required.")

    final_result = {
        "iterations": iteration,
        "max_iterations": max_iterations,
        "passed": gate_result.get("ok", False),
        "history": history,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    output_dir = Path("artifacts/control_plane")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "auto_fix_loop.json"
    with open(output_path, "w") as f:
        json.dump(final_result, f, indent=2)

    print(f"\n📄 Auto-fix history: {output_path}")

    return final_result


def main():
    parser = argparse.ArgumentParser(description="Auto-Fix Loop")
    parser.add_argument("--mode", choices=["dev", "ci"], default="dev")
    parser.add_argument("--max-iterations", type=int, default=MAX_ITERATIONS)
    args = parser.parse_args()

    result = auto_fix_loop(args.mode, args.max_iterations)

    if not result["passed"]:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
