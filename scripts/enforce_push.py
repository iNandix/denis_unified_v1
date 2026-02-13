#!/usr/bin/env python3
"""
Enforce & Push - The INFALLIBLE system.
This script ensures ALL changes pass the gate before pushing.
If the gate fails, it blocks the push and requires fixes.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def get_current_branch():
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    return result.stdout.strip()


def get_changes():
    """Get list of changed files."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True
    )
    return [line[3:] for line in result.stdout.strip().split("\n") if line]


def run_gate_check(mode: str = "dev") -> dict:
    """Run the supervisor gate and return result."""
    result = subprocess.run(
        [sys.executable, "scripts/supervisor_gate.py", f"--mode={mode}"],
        capture_output=True,
        text=True,
        timeout=300,
    )

    gate_artifact = Path("artifacts/control_plane/supervisor_gate.json")
    if gate_artifact.exists():
        with open(gate_artifact) as f:
            data = json.load(f)
            data["exit_code"] = result.returncode
            return data

    return {"ok": False, "error": "No gate artifact", "exit_code": result.returncode}


def run_auto_fix(mode: str = "dev", max_iterations: int = 10) -> dict:
    """Run the auto-fix loop."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/auto_fix_loop.py",
            f"--mode={mode}",
            f"--max-iterations={max_iterations}",
        ],
        capture_output=True,
        text=True,
        timeout=3600,
    )

    auto_fix_artifact = Path("artifacts/control_plane/auto_fix_loop.json")
    if auto_fix_artifact.exists():
        with open(auto_fix_artifact) as f:
            data = json.load(f)
            data["exit_code"] = result.returncode
            return data

    return {"iterations": 0, "passed": False, "exit_code": result.returncode}


def stage_and_commit(message: str) -> bool:
    """Stage all changes and commit."""
    subprocess.run(["git", "add", "-A"], check=True)
    result = subprocess.run(
        ["git", "commit", "-m", message], capture_output=True, text=True
    )
    return result.returncode == 0


def push_to_remote(remote: str = "origin") -> bool:
    """Push to remote, respecting pre-push hook."""
    result = subprocess.run(
        ["git", "push", remote, get_current_branch()], capture_output=True, text=True
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Enforce & Push - Infallible system")
    parser.add_argument(
        "--message", "-m", default="Auto-commit via enforce", help="Commit message"
    )
    parser.add_argument(
        "--mode", choices=["dev", "ci"], default="dev", help="Gate mode"
    )
    parser.add_argument(
        "--auto-fix", action="store_true", help="Run auto-fix loop if gate fails"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=10, help="Max auto-fix iterations"
    )
    parser.add_argument("--no-push", action="store_true", help="Don't push, just check")
    args = parser.parse_args()

    print("=" * 70)
    print("🚨 ENFORCE & PUSH - INFALLIBLE SYSTEM")
    print("=" * 70)

    branch = get_current_branch()
    print(f"\n📂 Branch: {branch}")

    changes = get_changes()
    print(f"\n📝 Changed files ({len(changes)}):")
    for f in changes[:10]:
        print(f"   - {f}")
    if len(changes) > 10:
        print(f"   ... and {len(changes) - 10} more")

    print("\n" + "=" * 70)
    print("STEP 1: Running Supervisor Gate")
    print("=" * 70)

    gate_result = run_gate_check(args.mode)

    artifact = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "changes_count": len(changes),
        "mode": args.mode,
        "gate_result": gate_result,
    }

    if gate_result.get("ok", False):
        print("\n✅ GATE PASSED!")
        print(f"   Releaseable: {gate_result.get('ok')}")
        print(f"   Blocked by: {gate_result.get('policy', {}).get('blocked_by', [])}")
    else:
        print("\n❌ GATE FAILED!")
        print(f"   Releaseable: {gate_result.get('ok')}")
        print(f"   Blocked by: {gate_result.get('policy', {}).get('blocked_by', [])}")
        print(f"   Reasons: {gate_result.get('policy', {}).get('reasons', [])}")

        if args.auto_fix:
            print("\n" + "=" * 70)
            print("STEP 2: Running Auto-Fix Loop")
            print("=" * 70)

            auto_fix_result = run_auto_fix(args.mode, args.max_iterations)
            artifact["auto_fix_result"] = auto_fix_result

            if auto_fix_result.get("passed", False):
                print(
                    f"\n✅ AUTO-FIX SUCCESS! Passed after {auto_fix_result.get('iterations')} iterations"
                )
                gate_result = run_gate_check(args.mode)
                artifact["gate_result"] = gate_result
            else:
                print(
                    f"\n❌ AUTO-FIX FAILED after {auto_fix_result.get('iterations')} iterations"
                )
                print("   Manual intervention required!")
        else:
            print("\n⚠️  Use --auto-fix to attempt automatic remediation")

    artifact["finished_utc"] = datetime.now(timezone.utc).isoformat()
    artifact["success"] = gate_result.get("ok", False)

    output_dir = Path("artifacts/control_plane")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "enforce_push.json"
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print("\n" + "=" * 70)
    if gate_result.get("ok", False):
        if args.no_push:
            print("✅ CHECK PASSED (--no-push specified)")
        else:
            print("STEP 3: Pushing to Remote")
            print("=" * 70)

            if stage_and_commit(args.message):
                print("✅ Committed")

                if push_to_remote():
                    print("✅ Pushed to origin/{branch}".format(branch=branch))
                else:
                    print("❌ Push failed!")
                    print("   (This might be the pre-push hook blocking)")
                    artifact["push_success"] = False
                    with open(output_path, "w") as f:
                        json.dump(artifact, f, indent=2)
                    sys.exit(1)
            else:
                print("❌ Commit failed!")
                sys.exit(1)
    else:
        print("❌ BLOCKED: Gate still failing")
        print("   Fix the issues and try again")
        sys.exit(1)

    artifact["push_success"] = True
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print("\n" + "=" * 70)
    print("✅ ENFORCE & PUSH COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
