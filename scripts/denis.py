#!/usr/bin/env python3
"""
DENIS Maintainer CLI - Fix one issue at a time with strict discipline + AI analysis.

Usage:
    denis fix --one        # Fix exactly one failure with AI analysis
    denis fix --auto      # Auto-fix loop (iterate until 100% green)
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


# Load .env variables
def load_env():
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key and value and os.environ.get(key) is None:
                        os.environ[key] = value


load_env()

SCRIPTS_DIR = Path("scripts")
ARTIFACTS_DIR = Path("artifacts")
ATTEMPTS_DIR = ARTIFACTS_DIR / "attempts"

# AI Configuration
AI_ENABLED = os.getenv("AI_ANALYSIS_ENABLED", "true").lower() == "true"
AI_MAX_ITERATIONS = int(os.getenv("AI_MAX_ITERATIONS", "5"))
AI_PROVIDER = os.getenv("AI_ANALYSIS_PROVIDER", "perplexity")


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


def get_smoke_output(smoke_name: str) -> str:
    """Get the output from a specific smoke artifact."""
    smoke_map = {
        "boot_import": "artifacts/boot_import_smoke.json",
        "controlplane_status": "artifacts/control_plane/controlplane_status_smoke.json",
        "openai_router": "artifacts/openai_router_smoke.json",
        "legacy_imports": "artifacts/legacy_imports_smoke.json",
        "capabilities_registry": "artifacts/api/phase6_capabilities_registry_smoke.json",
        "gate_smoke": "artifacts/phase10_gate_smoke.json",
    }

    path = smoke_map.get(smoke_name)
    if path:
        return load_json(Path(path), {})
    return {}


def get_controlplane_status() -> dict:
    """Get control plane status."""
    return load_json(ARTIFACTS_DIR / "control_plane" / "status.json", {})


def call_ai_analysis(failure: dict) -> dict:
    """Call AI to analyze the failure."""
    if not AI_ENABLED:
        return {
            "success": False,
            "error": "AI analysis disabled",
            "root_cause": "AI_ANALYSIS_ENABLED=false",
            "fix_suggestions": [],
            "files_to_check": [],
            "confidence": 0.0,
        }

    # Build the analysis script call
    failure_json = json.dumps(failure)

    cmd = [
        sys.executable,
        "scripts/denis_ai_analysis.py",
        "--failure",
        failure_json,
    ]

    result = run_command(cmd, timeout=60)

    if result["success"] and result.get("stdout"):
        try:
            return json.loads(result["stdout"])
        except:
            pass

    return {
        "success": False,
        "error": result.get("stderr", "AI call failed"),
        "root_cause": "Could not get AI analysis",
        "fix_suggestions": ["Manual intervention required"],
        "files_to_check": [],
        "confidence": 0.0,
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


def run_single_smoke(smoke_name: str) -> dict:
    """Run a single smoke test."""
    smoke_map = {
        "boot_import": "scripts/boot_import_smoke.py",
        "controlplane_status": "scripts/controlplane_status_smoke.py",
        "openai_router": "scripts/openai_router_smoke.py",
        "legacy_imports": "scripts/legacy_imports_smoke.py",
        "capabilities_registry": "scripts/phase6_capabilities_registry_smoke.py",
        "gate_smoke": "scripts/phase10_gate_smoke.py",
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
    run_command(["git", "checkout", "."], timeout=30)


def commit_if_green(passed: int, total: int) -> bool:
    """Commit only if 100% green."""
    if passed == total and passed > 0:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        run_command(["git", "add", "-A"], timeout=30)

        msg = f"fix(smoke): strict-100 green ({passed}/{total})"
        result = run_command(["git", "commit", "-m", msg], timeout=30)

        if result["success"]:
            return True
    return False


def save_attempt_record(
    selection: dict, analysis: dict, before: dict, after: dict, iteration: int
):
    """Save attempt record for evidence."""
    ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "iteration": iteration,
        "selection": selection,
        "ai_analysis": analysis,
        "before": before,
        "after": after,
    }

    path = ATTEMPTS_DIR / f"fix_one_{timestamp}_iter{iteration}.json"
    with open(path, "w") as f:
        json.dump(record, f, indent=2)

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

    # AI Analysis
    if AI_ENABLED:
        print(f"\n🤖 Running AI Analysis...")
        smoke_data = get_smoke_output(failure.get("name", ""))
        controlplane = get_controlplane_status()

        ai_result = call_ai_analysis(failure)

        if ai_result.get("success"):
            print(f"\n📋 AI ANALYSIS:")
            print(f"   Root Cause: {ai_result.get('root_cause', 'N/A')}")
            print(f"   Confidence: {ai_result.get('confidence', 0):.0%}")
            print(f"\n🔧 SUGGESTED FIXES:")
            for i, suggestion in enumerate(ai_result.get("fix_suggestions", [])[:5], 1):
                print(f"   {i}. {suggestion}")
            print(f"\n📁 FILES TO CHECK:")
            for f in ai_result.get("files_to_check", [])[:5]:
                print(f"   - {f}")
        else:
            print(f"\n⚠️ AI Analysis failed: {ai_result.get('error')}")

    return 1


def denis_fix_one():
    """Fix exactly one failure with AI analysis."""
    print("=" * 60)
    print("🔧 DENIS FIX --ONE - With AI Analysis")
    print("=" * 60)

    result = run_meta_smoke_strict()

    artifact = result["artifact"]
    passed = result["passed"]
    total = result["total"]

    if passed == total:
        print(f"\n✅ Already green ({passed}/{total}) - Nothing to fix!")
        return 0

    selection = select_best_failure(artifact)
    failure = selection.get("failure", {})

    print(f"\n❌ Selecting failure: {failure.get('name')}")
    print(f"   Rule: {selection.get('rule')}")
    print(f"   Reason: {failure.get('reason')}")

    # Get smoke output and controlplane status
    smoke_data = get_smoke_output(failure.get("name", ""))
    controlplane = get_controlplane_status()

    # AI Analysis
    if AI_ENABLED:
        print(f"\n🤖 Running AI Analysis...")
        ai_result = call_ai_analysis(failure)

        if ai_result.get("success"):
            print(f"\n📋 AI ANALYSIS:")
            print(f"   Root Cause: {ai_result.get('root_cause', 'N/A')}")
            print(f"   Confidence: {ai_result.get('confidence', 0):.0%}")
            print(f"\n🔧 SUGGESTED FIXES:")
            for i, suggestion in enumerate(ai_result.get("fix_suggestions", [])[:5], 1):
                print(f"   {i}. {suggestion}")
            print(f"\n📁 FILES TO CHECK:")
            for f in ai_result.get("files_to_check", [])[:5]:
                print(f"   - {f}")
        else:
            print(f"\n⚠️ AI Analysis failed: {ai_result.get('error')}")

    print(f"\n⚠️  MANUAL INTERVENTION REQUIRED")
    print(f"   DENIS provides analysis but needs human to apply fix.")
    print(f"   After applying fix, run: denis fix --auto")

    return 1


def denis_fix_auto():
    """Auto-fix loop - iterate until 100% green or max iterations."""
    print("=" * 60)
    print("🔧 DENIS FIX --AUTO - Iterating until 100% green")
    print("=" * 60)
    print(f"   AI Enabled: {AI_ENABLED}")
    print(f"   Max Iterations: {AI_MAX_ITERATIONS}")
    print(f"   Provider: {AI_PROVIDER}")

    iteration = 0
    last_ai_analysis = None

    while iteration < AI_MAX_ITERATIONS:
        iteration += 1
        print(f"\n{'=' * 60}")
        print(f"ITERATION {iteration}/{AI_MAX_ITERATIONS}")
        print(f"{'=' * 60}")

        result = run_meta_smoke_strict()

        artifact = result["artifact"]
        passed = result["passed"]
        total = result["total"]

        print(f"\n📊 Result: {passed}/{total} passed")

        if passed == total:
            print(f"\n✅ 100% GREEN! Attempting commit...")

            if commit_if_green(passed, total):
                print(f"\n✅ COMMITTED!")
                return 0
            else:
                print(f"\n⚠️ Could not commit (no changes or already committed)")
                return 0

        selection = select_best_failure(artifact)
        failure = selection.get("failure", {})

        print(f"\n❌ Failure: {failure.get('name')}")
        print(f"   Reason: {failure.get('reason')}")

        # AI Analysis
        if AI_ENABLED:
            print(f"\n🤖 AI Analysis...")
            ai_result = call_ai_analysis(failure)
            last_ai_analysis = ai_result

            if ai_result.get("success"):
                print(f"   Root Cause: {ai_result.get('root_cause', 'N/A')}")
                print(f"   Confidence: {ai_result.get('confidence', 0):.0%}")
                print(f"\n   Suggestions:")
                for s in ai_result.get("fix_suggestions", [])[:3]:
                    print(f"   - {s}")
            else:
                print(f"   Analysis failed: {ai_result.get('error')}")

        before_state = {
            "passed": passed,
            "total": total,
            "passed_ratio": result["passed_ratio"],
        }

        # Save attempt
        path = save_attempt_record(
            selection,
            last_ai_analysis or {},
            before_state,
            {"status": "iterating"},
            iteration,
        )
        print(f"\n📄 Attempt saved: {path.name}")

        print(f"\n⚠️  Please apply the fix and run: denis fix --auto")
        print(f"   Or manually fix and commit, then DENIS will verify.")

        return 1

    print(f"\n❌ MAX ITERATIONS REACHED ({AI_MAX_ITERATIONS})")
    print(f"   Manual intervention required!")

    return 1


def denis_status():
    """Show current status."""
    print("=" * 60)
    print("📊 DENIS STATUS")
    print("=" * 60)

    print(f"\nAI Configuration:")
    print(f"   Enabled: {AI_ENABLED}")
    print(f"   Provider: {AI_PROVIDER}")
    print(f"   Max Iterations: {AI_MAX_ITERATIONS}")

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
    parser.add_argument(
        "--auto", action="store_true", help="Auto-fix loop (iterate until 100% green)"
    )

    args = parser.parse_args()

    if args.command == "doctor":
        return denis_doctor()
    elif args.command == "fix":
        if args.auto:
            return denis_fix_auto()
        else:
            return denis_fix_one()
    elif args.command == "status":
        return denis_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
