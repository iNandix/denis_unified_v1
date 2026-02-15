import pytest

from denis_unified_v1.actions.models import ActionPlanCandidate, ActionPlanSet, Intent_v1, ActionStep, ToolCall, StopCondition, StopOp

def test_action_plan_candidate_validate():
    candidate = ActionPlanCandidate(
        candidate_id="test",
        intent="test",
        steps=[ActionStep(step_id="s1", description="desc", read_only=True)]
    )
    assert candidate.is_mutating == False

    # Add mutating step
    candidate.steps.append(ActionStep(step_id="s2", description="desc", read_only=False))
    # Re-validate
    candidate = ActionPlanCandidate(**candidate.model_dump())
    assert candidate.is_mutating == True

def test_action_plan_set_validate_selected():
    candidates = [{"candidate_id": "a"}, {"candidate_id": "b"}]
    plan_set = ActionPlanSet(
        ts_utc="2023-01-01T00:00:00Z",
        request_id="req1",
        intent={"intent": "test", "confidence": 0.8, "confidence_band": "high"},
        candidates=candidates,
        selected_candidate_id="a"
    )
    assert plan_set.selected_candidate_id == "a"

    # Invalid selected
    with pytest.raises(ValueError):
        ActionPlanSet(
            ts_utc="2023-01-01T00:00:00Z",
            request_id="req1",
            intent={"intent": "test", "confidence": 0.8, "confidence_band": "high"},
            candidates=candidates,
            selected_candidate_id="c"
        )
