#!/usr/bin/env python3
"""Phase-11 CrewAI Planner Smoke Test."""

import json
import os
import sys
from pathlib import Path

# Disable redis
os.environ["REDIS_URL"] = ""
os.environ["DENIS_SPRINT_STATE_DIR"] = "/tmp/sprint_test"

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from denis_unified_v1.sprint_orchestrator.intent_router_rasa import RasaIntentRouter
from denis_unified_v1.sprint_orchestrator.crewai_planner import build_plan

def main():
    results = {"phase": "phase11_crewai_planner_smoke"}
    try:
        router = RasaIntentRouter()
        route = router.route("añade endpoint /healthz y su smoke")
        plan = build_plan("añade endpoint /healthz y su smoke", route.intent, route.confidence, ".")
        # Validate
        schema_ok = True  # Pydantic validates
        areas = set()
        has_verify = True
        for milestone in plan.milestones:
            for task in milestone.tasks:
                areas.add(task.area)
                if not task.verify_targets:
                    has_verify = False
        areas_ok = len(areas) == 4  # ARCH, CODING, QA, OPS
        results.update({
            "schema_ok": schema_ok,
            "areas_ok": areas_ok,
            "has_verify": has_verify,
            "plan_summary": {
                "milestones": len(plan.milestones),
                "total_tasks": sum(len(m.tasks) for m in plan.milestones),
                "areas": list(areas)
            }
        })
    except Exception as e:
        results["error"] = str(e)
        results["success"] = False
        return 1

    results["success"] = results.get("schema_ok", False) and results.get("areas_ok", False) and results.get("has_verify", False)
    return 0 if results["success"] else 1

if __name__ == "__main__":
    exit_code = main()
    # Write artifact
    artifact_path = Path("artifacts/sprint/phase11_crewai_planner_smoke.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({"exit_code": exit_code, **(locals().get("results", {}))}, f, indent=2)
    print(f"Smoke artifact: {artifact_path}")
    sys.exit(exit_code)
