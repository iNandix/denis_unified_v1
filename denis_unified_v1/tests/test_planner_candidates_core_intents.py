import pytest

from denis_unified_v1.actions.planner import generate_candidate_plans

from denis_unified_v1.actions.models import Intent_v1

def test_generate_candidate_plans_returns_two_for_core_intents():
    for intent in ["run_tests_ci", "debug_repo", "ops_health_check", "implement_feature"]:
        intent_v1 = Intent_v1(intent=intent, confidence=0.8, confidence_band="high")
        candidates = generate_candidate_plans(intent_v1)
        assert len(candidates) == 2
        assert all(c.intent == intent for c in candidates)
        assert any(not c.is_mutating for c in candidates)
        assert any(c.is_mutating for c in candidates)

def test_candidate_a_is_read_only_candidate_b_is_mutating():
    for intent in ["run_tests_ci", "debug_repo", "ops_health_check", "implement_feature"]:
        intent_v1 = Intent_v1(intent=intent, confidence=0.8, confidence_band="high")
        candidates = generate_candidate_plans(intent_v1)
        assert len(candidates) == 2
        # Assume first is read-only, second is mutating
        assert not candidates[0].is_mutating
        assert candidates[1].is_mutating
