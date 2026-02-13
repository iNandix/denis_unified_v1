#!/usr/bin/env python3
"""Supervisor Gate - Enforcement hard block for releases."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SMOKE_SCRIPTS = {
    "boot_import": "scripts/boot_import_smoke.py",
    "controlplane_status": "scripts/controlplane_status_smoke.py",
    "meta_smoke": "scripts/meta_smoke_all.py",
    "work_compiler": "scripts/work_compiler_smoke.py",
}


def run_smoke(script_path: str, timeout: int = 60) -> dict:
    result = {
        "script": script_path,
        "ok": False,
        "returncode": -1,
        "stdout_tail": "",
        "stderr_tail": "",
        "artifact": {},
        "duration_sec": 0,
    }
    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path.cwd(),
        )
        result["returncode"] = proc.returncode
        result["stdout_tail"] = "\n".join(proc.stdout.splitlines()[-20:])
        result["stderr_tail"] = "\n".join(proc.stderr.splitlines()[-20:])

        artifact_path = (
            Path("artifacts")
            / Path(script_path).stem.replace("_smoke", "")
            / "smoke.json"
        )
        if not artifact_path.exists():
            artifact_path = Path("artifacts") / f"{Path(script_path).stem}.json"

        if artifact_path.exists():
            with open(artifact_path) as f:
                result["artifact"] = json.load(f)
                result["ok"] = result["artifact"].get("ok", proc.returncode == 0)
        else:
            result["ok"] = proc.returncode == 0
    except subprocess.TimeoutExpired:
        result["stderr_tail"] = "TIMEOUT"
    except Exception as e:
        result["stderr_tail"] = str(e)

    result["duration_sec"] = time.time() - start
    return result


def check_duplicate_definitions() -> dict:
    result = {"duplicates": [], "ok": True}
    try:
        proc = subprocess.run(
            ["rg", "^-def\\s+(\\w+)", "--type", "py", "-o", "--no-heading"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        counts = {}
        for line in proc.stdout.splitlines():
            if ":" in line:
                name = line.split(":")[-1].strip()
                counts[name] = counts.get(name, 0) + 1

        duplicates = {k: v for k, v in counts.items() if v > 1}
        result["duplicates"] = [{"name": k, "count": v} for k, v in duplicates.items()]
        result["ok"] = len(duplicates) == 0
    except Exception as e:
        result["error"] = str(e)
    return result


def check_import_side_effects() -> dict:
    result = {"violations": [], "ok": True}
    api_files = list(Path("api").glob("*.py"))
    for f in api_files:
        try:
            content = f.read_text()
            lines = content.splitlines()
            for i, line in enumerate(lines[:10]):
                if "create_app()" in line and not line.strip().startswith("#"):
                    if "if __name__" not in "\n".join(lines[max(0, i - 2) : i + 3]):
                        result["violations"].append(
                            {"file": str(f), "line": i + 1, "content": line.strip()}
                        )
                        result["ok"] = False
        except Exception:
            pass
    return result


def check_ok_coherence(artifacts: dict) -> dict:
    result = {"violations": [], "ok": True}
    for name, data in artifacts.items():
        artifact_ok = data.get("ok")
        if artifact_ok is None:
            continue
        overall_status = data.get("overall_status")
        if overall_status:
            if overall_status == "failed" and artifact_ok:
                result["violations"].append(
                    {"artifact": name, "issue": "ok=true but overall_status=failed"}
                )
                result["ok"] = False
            elif overall_status == "green" and not artifact_ok:
                result["violations"].append(
                    {"artifact": name, "issue": "ok=false but overall_status=green"}
                )
                result["ok"] = False
    return result


def evaluate_policy(results: dict, mode: str) -> dict:
    policy = {
        "mode": mode,
        "checks": {},
        "releaseable": True,
        "blocked_by": [],
        "reasons": [],
    }

    for name, data in results.items():
        if name in ["duplicates", "side_effects", "coherence"]:
            policy["checks"][name] = data
            if not data.get("ok", True):
                policy["releaseable"] = False
                policy["blocked_by"].append(name)
                policy["reasons"].append(
                    f"{name}: {data.get('violations', data.get('duplicates', []))}"
                )
            continue

        smoke_ok = data.get("ok", False)
        policy["checks"][name] = data

        if mode == "ci":
            if not smoke_ok:
                policy["releaseable"] = False
                policy["blocked_by"].append(name)
                policy["reasons"].append(f"{name}_failed")
        else:
            if not smoke_ok and name in ["boot_import", "controlplane_status"]:
                policy["releaseable"] = False
                policy["blocked_by"].append(name)
                policy["reasons"].append(f"{name}_failed_critical")

    smoke_results = {k: v for k, v in results.items() if k in SMOKE_SCRIPTS}
    coherence = check_ok_coherence(
        {k: v.get("artifact", {}) for k, v in smoke_results.items()}
    )
    policy["checks"]["coherence"] = coherence
    if not coherence.get("ok", True):
        policy["releaseable"] = False
        policy["blocked_by"].append("coherence")
        policy["reasons"].append("ok_mismatch")

    return policy


def main():
    parser = argparse.ArgumentParser(description="Supervisor Gate - CI enforcement")
    parser.add_argument(
        "--mode", choices=["dev", "ci"], default="dev", help="dev=lenient, ci=strict"
    )
    parser.add_argument(
        "--timeout", type=int, default=60, help="Timeout per smoke test"
    )
    args = parser.parse_args()

    print(f"=== Supervisor Gate ({args.mode.upper()}) ===")

    results = {}

    print("\n[1/6] Running boot_import_smoke...")
    results["boot_import"] = run_smoke(SMOKE_SCRIPTS["boot_import"], args.timeout)
    print(
        f"  -> ok: {results['boot_import']['ok']}, returncode: {results['boot_import']['returncode']}"
    )

    print("\n[2/6] Running controlplane_status_smoke...")
    results["controlplane_status"] = run_smoke(
        SMOKE_SCRIPTS["controlplane_status"], args.timeout
    )
    print(
        f"  -> ok: {results['controlplane_status']['ok']}, returncode: {results['controlplane_status']['returncode']}"
    )

    print("\n[3/6] Running meta_smoke_all...")
    results["meta_smoke"] = run_smoke(SMOKE_SCRIPTS["meta_smoke"], args.timeout * 2)
    print(
        f"  -> ok: {results['meta_smoke']['ok']}, returncode: {results['meta_smoke']['returncode']}"
    )

    print("\n[4/6] Running work_compiler_smoke...")
    results["work_compiler"] = run_smoke(SMOKE_SCRIPTS["work_compiler"], args.timeout)
    print(
        f"  -> ok: {results['work_compiler']['ok']}, returncode: {results['work_compiler']['returncode']}"
    )

    print("\n[5/6] Checking duplicate definitions...")
    results["duplicates"] = check_duplicate_definitions()
    print(
        f"  -> ok: {results['duplicates']['ok']}, duplicates: {len(results['duplicates'].get('duplicates', []))}"
    )

    print("\n[6/6] Checking import side-effects...")
    results["side_effects"] = check_import_side_effects()
    print(
        f"  -> ok: {results['side_effects']['ok']}, violations: {len(results['side_effects'].get('violations', []))}"
    )

    policy = evaluate_policy(results, args.mode)

    artifact = {
        "ok": policy["releaseable"],
        "overall_status": "green" if policy["releaseable"] else "failed",
        "mode": args.mode,
        "policy": policy,
        "checks": results,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    output_dir = Path("artifacts/control_plane")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "supervisor_gate.json"
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print(f"\n=== Supervisor Gate Result ===")
    print(f"  releaseable: {policy['releaseable']}")
    print(f"  blocked_by: {policy['blocked_by']}")
    print(f"  reasons: {policy['reasons']}")
    print(f"  artifact: {output_path}")

    if not policy["releaseable"]:
        print(f"\n🚫 GATE BLOCKED: {policy['blocked_by']}")
        sys.exit(1)

    print("\n✅ GATE PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
