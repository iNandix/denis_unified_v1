#!/usr/bin/env python3
"""Auditor Report - Post-run analysis with zero code changes."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def find_duplicates() -> list:
    result = []
    try:
        proc = subprocess.run(
            ["rg", "^def\\s+(\\w+)", "--type", "py", "-o", "--no-heading"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        counts = {}
        for line in proc.stdout.splitlines():
            if ":" in line:
                name = line.split(":")[-1].strip()
                counts[name] = counts.get(name, 0) + 1

        for k, v in counts.items():
            if v > 1:
                result.append({"symbol": k, "count": v})
    except Exception:
        pass
    return result


def find_import_side_effects() -> list:
    result = []
    for pattern in ["api/**/*.py", "denisunifiedv1/**/*.py"]:
        for f in Path(".").glob(pattern):
            if f.is_file() and f.name.startswith("__"):
                continue
            try:
                content = f.read_text()
                lines = content.splitlines()
                for i, line in enumerate(lines[:15]):
                    if "create_app()" in line or "app = " in line:
                        if "if __name__" not in "\n".join(lines[max(0, i - 2) : i + 3]):
                            result.append(
                                {
                                    "file": str(f),
                                    "line": i + 1,
                                    "content": line.strip()[:80],
                                }
                            )
            except Exception:
                pass
    return result


def analyze_gate(gate_data: dict) -> dict:
    if not gate_data:
        return {"analyzed": False}

    policy = gate_data.get("policy", {})
    checks = gate_data.get("checks", {})

    root_causes = []
    evidence_paths = []
    suggested_remediations = []

    blocked_by = policy.get("blocked_by", [])
    for block in blocked_by:
        if block == "boot_import":
            root_causes.append("boot_import_smoke failed")
            suggested_remediations.append("fix_import_errors")
        elif block == "controlplane_status":
            root_causes.append("controlplane_status_smoke failed")
            suggested_remediations.append("fix_controlplane_schema")
        elif block == "meta_smoke":
            root_causes.append("meta_smoke_all has failures")
            suggested_remediations.append("review_failed_smokes")
        elif block == "work_compiler":
            root_causes.append("work_compiler_smoke failed")
            suggested_remediations.append("fix_work_compiler")
        elif block == "duplicates":
            root_causes.append("duplicate function/class definitions found")
            suggested_remediations.append("deduplicate_symbols")
        elif block == "side_effects":
            root_causes.append("import-time side effects detected")
            suggested_remediations.append("remove_top_level_create_app")
        elif block == "coherence":
            root_causes.append("ok/overall_status mismatch detected")
            suggested_remediations.append("fix_artifact_coherence")

    if gate_data.get("checks"):
        for name, data in gate_data["checks"].items():
            if isinstance(data, dict) and not data.get("ok", True):
                evidence_paths.append(
                    f"artifacts/control_plane/supervisor_gate.json -> {name}"
                )

    return {
        "analyzed": True,
        "root_causes": root_causes,
        "evidence_paths": evidence_paths,
        "suggested_remediations": suggested_remediations,
        "blocked_by": blocked_by,
    }


def analyze_sprint(sprint_data: dict) -> dict:
    if not sprint_data:
        return {"analyzed": False}

    items = sprint_data.get("executed_items", [])
    failed_items = [i for i in items if not i.get("success", True)]

    root_causes = []
    evidence_paths = []

    for item in failed_items:
        reasons = item.get("failure_reasons", [])
        for reason in reasons:
            if "timeout" in reason:
                root_causes.append(f"timeout in {item.get('item_id')}")
            elif "returncode" in reason:
                root_causes.append(f"command failed in {item.get('item_id')}")
            elif "missing_artifacts" in reason:
                root_causes.append(f"missing artifacts in {item.get('item_id')}")

    return {
        "analyzed": True,
        "total_executed": len(items),
        "total_failed": len(failed_items),
        "root_causes": root_causes,
        "evidence_paths": evidence_paths,
    }


def main():
    parser = argparse.ArgumentParser(description="Auditor Report")
    parser.add_argument(
        "output",
        nargs="?",
        default="artifacts/control_plane/auditor_report.json",
        help="Output path",
    )
    args = parser.parse_args()

    print("=== Auditor Report ===")

    artifact = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "duplicate_symbols": find_duplicates(),
        "import_time_side_effects": find_import_side_effects(),
        "gate_analysis": {},
        "sprint_analysis": {},
    }

    gate_path = Path("artifacts/control_plane/supervisor_gate.json")
    if gate_path.exists():
        gate_data = load_json(gate_path)
        artifact["gate_analysis"] = analyze_gate(gate_data)
        print(
            f"  gate_analysis: {len(artifact['gate_analysis'].get('root_causes', []))} root causes"
        )

    sprint_path = Path("artifacts/control_plane/supervisor_run.json")
    if sprint_path.exists():
        sprint_data = load_json(sprint_path)
        artifact["sprint_analysis"] = analyze_sprint(
            sprint_data.get("sprint_result", {})
        )
        print(
            f"  sprint_analysis: {len(artifact['sprint_analysis'].get('root_causes', []))} root causes"
        )

    print(f"  duplicate_symbols: {len(artifact['duplicate_symbols'])}")
    print(f"  import_time_side_effects: {len(artifact['import_time_side_effects'])}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print(f"\n  artifact: {output_path}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
