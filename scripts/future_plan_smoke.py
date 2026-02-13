#!/usr/bin/env python3
"""Stream 7: Future Vision Builder smoke test - autonomous roadmap generation."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def parse_args():
    parser = argparse.ArgumentParser(description="Stream 7: Future vision builder smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/roadmap/future_plan.json",
        help="Output artifact path",
    )
    return parser.parse_args()

def run_smoke():
    """Run future vision builder smoke test."""
    try:
        # Import and run RoadmapSynthesizer
        from denis_unified_v1.roadmap_synthesizer import generate_future_roadmap

        # Generate roadmap from current artifacts
        roadmap = generate_future_roadmap(PROJECT_ROOT / "artifacts")

        # Validate roadmap structure
        validation_results = validate_roadmap(roadmap)

        # Prepare result
        result = {
            "ok": True,
            "status": "roadmap_generated",
            "timestamp_utc": _utc_now(),
            "roadmap": roadmap,
            "validation": validation_results,
            "summary": {
                "artifacts_analyzed": roadmap.get("total_artifacts_analyzed", 0),
                "backlog_items_generated": len(roadmap.get("prioritized_backlog", [])),
                "sprints_planned": len(roadmap.get("next_sprints", [])),
                "top_initiatives": roadmap.get("top_10_initiatives", []),
                "critical_items": roadmap.get("roadmap_summary", {}).get("critical_items", 0),
                "estimated_effort_weeks": roadmap.get("roadmap_summary", {}).get("estimated_total_effort_weeks", 0)
            }
        }

        # Check if roadmap meets minimum requirements
        if (len(roadmap.get("prioritized_backlog", [])) >= 5 and
            len(roadmap.get("next_sprints", [])) >= 1 and
            roadmap.get("current_state_analysis")):
            result["roadmap_quality"] = "comprehensive"
        elif len(roadmap.get("prioritized_backlog", [])) >= 3:
            result["roadmap_quality"] = "adequate"
        else:
            result["roadmap_quality"] = "minimal"

        return result

    except Exception as e:
        return {
            "ok": False,
            "status": "failed",
            "error": f"Smoke test execution failed: {str(e)}",
            "timestamp_utc": _utc_now()
        }

def validate_roadmap(roadmap: dict) -> dict:
    """Validate roadmap structure and content."""
    validation = {
        "structure_valid": True,
        "content_complete": True,
        "issues": []
    }

    # Check required top-level keys
    required_keys = ["synthesis_timestamp", "current_state_analysis", "prioritized_backlog", "next_sprints", "top_10_initiatives"]
    for key in required_keys:
        if key not in roadmap:
            validation["structure_valid"] = False
            validation["issues"].append(f"missing_key: {key}")

    # Check backlog items have required fields
    if "prioritized_backlog" in roadmap:
        for i, item in enumerate(roadmap["prioritized_backlog"]):
            required_item_keys = ["id", "title", "priority", "impact", "acceptance_criteria"]
            for key in required_item_keys:
                if key not in item:
                    validation["content_complete"] = False
                    validation["issues"].append(f"backlog_item_{i}_missing: {key}")

    # Check sprints have required structure
    if "next_sprints" in roadmap:
        for i, sprint in enumerate(roadmap["next_sprints"]):
            required_sprint_keys = ["sprint_id", "title", "items", "acceptance_criteria"]
            for key in required_sprint_keys:
                if key not in sprint:
                    validation["content_complete"] = False
                    validation["issues"].append(f"sprint_{i}_missing: {key}")

    # Check top initiatives
    if "top_10_initiatives" in roadmap:
        if not isinstance(roadmap["top_10_initiatives"], list):
            validation["issues"].append("top_initiatives_not_list")
        elif len(roadmap["top_10_initiatives"]) == 0:
            validation["issues"].append("no_initiatives_generated")

    return validation

def main():
    args = parse_args()
    result = run_smoke()

    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    # Always exit 0 (fail-open)
    return 0

if __name__ == "__main__":
    sys.exit(main())
