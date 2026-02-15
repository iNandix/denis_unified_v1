from denis_unified_v1.actions.planner import select_plan

from denis_unified_v1.actions.models import ActionPlanCandidate

def test_select_plan_low_confidence_never_mutating():
    candidates = [
        ActionPlanCandidate(candidate_id="a", intent="test", is_mutating=False),
        ActionPlanCandidate(candidate_id="b", intent="test", is_mutating=True)
    ]
    selected = select_plan(candidates, "low")
    assert selected is not None
    assert not selected.is_mutating

def test_select_plan_medium_confidence_selects_read_only():
    candidates = [
        ActionPlanCandidate(candidate_id="a", intent="test", is_mutating=False),
        ActionPlanCandidate(candidate_id="b", intent="test", is_mutating=True)
    ]
    selected = select_plan(candidates, "medium")
    assert selected is not None
    assert not selected.is_mutating

def test_select_plan_high_confidence_allows_mutating_when_safe():
    candidates = [
        ActionPlanCandidate(candidate_id="a", intent="test", is_mutating=False),
        ActionPlanCandidate(candidate_id="b", intent="test", is_mutating=True)
    ]
    selected = select_plan(candidates, "high")
    assert selected is not None
    assert selected.is_mutating

def test_low_and_medium_never_select_mutating_even_if_candidate_exists():
    candidates = [
        ActionPlanCandidate(candidate_id="a", intent="test", is_mutating=False),
        ActionPlanCandidate(candidate_id="b", intent="test", is_mutating=True)
    ]
    for band in ["low", "medium"]:
        selected = select_plan(candidates, band)
        assert selected is not None
        assert not selected.is_mutating
