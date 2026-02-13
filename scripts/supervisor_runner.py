#!/usr/bin/env python3
"""Supervisor Runner - Execute streams and run gate."""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from denisunifiedv1.agents.denisagent import DENISAgent


def run_command(cmd: str, timeout: int = 60) -> dict:
    result = {
        "cmd": cmd,
        "returncode": -1,
        "stdout_tail": "",
        "stderr_tail": "",
        "duration_sec": 0,
    }
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path.cwd(),
        )
        result["returncode"] = proc.returncode
        result["stdout_tail"] = "\n".join(proc.stdout.splitlines()[-20:])
        result["stderr_tail"] = "\n".join(proc.stderr.splitlines()[-20:])
    except subprocess.TimeoutExpired:
        result["stderr_tail"] = "TIMEOUT"
    except Exception as e:
        result["stderr_tail"] = str(e)
    result["duration_sec"] = time.time() - start
    return result


async def run_denis_sprint(plan_path: str, max_items: int = 3) -> dict:
    agent = DENISAgent()
    return await agent.run_sprint(plan_path, max_items=max_items)


def run_supervisor_gate(mode: str = "dev") -> dict:
    result = run_command(
        f"{sys.executable} scripts/supervisor_gate.py --mode={mode}", timeout=180
    )
    gate_artifact = Path("artifacts/control_plane/supervisor_gate.json")
    if gate_artifact.exists():
        with open(gate_artifact) as f:
            return json.load(f)
    return {"ok": False, "error": "No gate artifact", "run_result": result}


def main():
    parser = argparse.ArgumentParser(description="Supervisor Runner")
    parser.add_argument(
        "--plan",
        default="artifacts/orchestration/work_plan.json",
        help="Path to work plan",
    )
    parser.add_argument("--max-items", type=int, default=3, help="Max items to execute")
    parser.add_argument(
        "--gate-mode", choices=["dev", "ci"], default="dev", help="Gate mode"
    )
    parser.add_argument(
        "--skip-sprint",
        action="store_true",
        help="Skip sprint execution, only run gate",
    )
    args = parser.parse_args()

    print(f"=== Supervisor Runner ===")
    print(f"  plan: {args.plan}")
    print(f"  max_items: {args.max_items}")
    print(f"  gate_mode: {args.gate_mode}")

    artifact = {
        "plan_path": args.plan,
        "max_items": args.max_items,
        "gate_mode": args.gate_mode,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "sprint_result": None,
        "gate_result": None,
        "overall_status": "pending",
    }

    if not args.skip_sprint:
        print("\n[1/2] Running DENIS sprint...")
        if Path(args.plan).exists():
            sprint_result = asyncio.run(run_denis_sprint(args.plan, args.max_items))
            artifact["sprint_result"] = sprint_result
            print(f"  -> overall_status: {sprint_result.get('overall_status')}")
            print(
                f"  -> executed_items: {len(sprint_result.get('executed_items', []))}"
            )
            print(f"  -> blocked_items: {len(sprint_result.get('blocked_items', []))}")
        else:
            print(f"  -> Plan not found: {args.plan}, skipping sprint")

    print("\n[2/2] Running Supervisor Gate...")
    gate_result = run_supervisor_gate(args.gate_mode)
    artifact["gate_result"] = gate_result
    print(f"  -> releaseable: {gate_result.get('ok')}")
    print(f"  -> blocked_by: {gate_result.get('policy', {}).get('blocked_by', [])}")

    sprint_ok = (
        artifact.get("sprint_result", {}).get("ok", True)
        if not args.skip_sprint
        else True
    )
    gate_ok = gate_result.get("ok", False)

    if args.skip_sprint:
        artifact["overall_status"] = "green" if gate_ok else "failed"
    else:
        if sprint_ok and gate_ok:
            artifact["overall_status"] = "green"
        elif sprint_ok or gate_ok:
            artifact["overall_status"] = "partial"
        else:
            artifact["overall_status"] = "failed"

    artifact["finished_utc"] = datetime.now(timezone.utc).isoformat()
    artifact["ok"] = artifact["overall_status"] != "failed"

    output_dir = Path("artifacts/control_plane")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "supervisor_run.json"
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print(f"\n=== Supervisor Runner Result ===")
    print(f"  overall_status: {artifact['overall_status']}")
    print(f"  artifact: {output_path}")

    if artifact["overall_status"] == "failed":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
