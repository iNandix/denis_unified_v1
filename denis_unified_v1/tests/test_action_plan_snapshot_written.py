import json

from pathlib import Path

from denis_unified_v1.actions.planner import save_action_plan_snapshot

from denis_unified_v1.actions.models import ActionPlanSet

def test_action_plan_snapshot_written_and_schema_valid(tmp_path):
    plan_set = ActionPlanSet(
        ts_utc="2023-01-01T00:00:00Z",
        request_id="req1",
        intent={"intent": "test", "confidence": 0.8, "confidence_band": "high"},
        candidates=[{"candidate_id": "a", "risk_level": "low", "estimated_tokens": 100, "is_mutating": False, "requires_internet": False, "num_steps": 1, "num_read_only": 1, "num_mutating": 0}],
        selected_candidate_id="a",
        selection_reason_codes=["test"]
    )
    save_action_plan_snapshot(plan_set, tmp_path)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    with open(files[0]) as f:
        data = json.load(f)
    assert data["kind"] == "action_plan_snapshot"
    assert data["selected_candidate_id"] == "a"
    assert "intent" in data
    assert "candidates" in data
