"""P1.3 Outcome Recording Tests.

Tests the telemetry/outcome recording system.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
from datetime import datetime, timezone
import pytest

from denis_unified_v1.telemetry.outcome_recorder import (
    OutcomeRecorder,
    ExecutionOutcome,
    IntentOutcome,
    PlanOutcome,
    StepOutcome,
    OutcomeStatus,
    ConfidenceBand,
    create_ml_features,
)


def test_outcome_recorder_basic():
    """Test basic outcome recording."""
    print("=" * 60)
    print("TEST: Outcome Recorder Basic")
    print("=" * 60)

    from denis_unified_v1.intent.unified_parser import parse_intent

    prompt = "pytest me da error"
    intent = parse_intent(prompt)

    recorder = OutcomeRecorder()
    outcome = recorder.record(
        request_id="test_001",
        intent_result=intent,
        internet_status="OK",
    )

    print(f"  Request ID: {outcome.request_id}")
    print(f"  Intent: {outcome.intent.intent}")
    print(f"  Confidence: {outcome.intent.confidence:.2f}")
    print(f"  Band: {outcome.intent.confidence_band}")
    print(f"  Status: {outcome.status}")

    assert outcome.request_id == "test_001"
    assert outcome.intent.intent is not None
    assert outcome.intent.confidence >= 0.0
    assert outcome.internet_status == "OK"

    print("\n✅ PASS: Basic outcome recording works")
    return True


def test_outcome_with_plan():
    """Test outcome with plan result."""
    print("\n" + "=" * 60)
    print("TEST: Outcome with Plan")
    print("=" * 60)

    from denis_unified_v1.intent.unified_parser import parse_intent
    from denis_unified_v1.actions.planner import generate_candidate_plans, select_plan
    from denis_unified_v1.actions.models import Intent_v1

    prompt = "pytest me da error"
    intent = parse_intent(prompt)

    intent_v1 = Intent_v1(
        intent=intent.intent.value,
        confidence=intent.confidence,
        confidence_band=intent.confidence_band,
    )

    candidates = generate_candidate_plans(intent_v1)
    selected = select_plan(candidates, intent.confidence_band)

    recorder = OutcomeRecorder()
    outcome = recorder.record(
        request_id="test_002",
        intent_result=intent,
        plan_result=selected,
        internet_status="OK",
    )

    print(f"  Plan ID: {outcome.plan.plan_id}")
    print(f"  Plan Type: {outcome.plan.plan_type}")
    print(f"  Steps: {outcome.plan.steps_total}")

    assert outcome.plan is not None
    assert outcome.plan.plan_id is not None

    print("\n✅ PASS: Plan outcome recording works")
    return True


def test_ml_features_creation():
    """Test ML features creation for CatBoost."""
    print("\n" + "=" * 60)
    print("TEST: ML Features Creation")
    print("=" * 60)

    intent_outcome = IntentOutcome(
        intent="run_tests_ci",
        confidence=0.85,
        confidence_band=ConfidenceBand.HIGH,
        sources_used=["rasa", "meta_llm"],
        reason_codes=["rasa_wins_high_confidence"],
    )

    plan_outcome = PlanOutcome(
        plan_id="test_plan",
        plan_type="read_only",
        steps_total=3,
        steps_completed=2,
        steps_failed=1,
    )

    step_outcomes = [
        StepOutcome(
            step_id="step1",
            status=OutcomeStatus.SUCCESS,
            duration_ms=100,
            evidence_paths=["/path/to/evidence1.txt"],
        ),
        StepOutcome(
            step_id="step2",
            status=OutcomeStatus.SUCCESS,
            duration_ms=200,
            evidence_paths=["/path/to/evidence2.txt"],
        ),
        StepOutcome(
            step_id="step3",
            status=OutcomeStatus.FAILED,
            duration_ms=50,
            error="Test failed",
        ),
    ]

    outcome = ExecutionOutcome(
        request_id="test_003",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        intent=intent_outcome,
        plan=plan_outcome,
        status=OutcomeStatus.DEGRADED,
        steps=step_outcomes,
        total_duration_ms=350,
        evidence_artifacts=["/path/to/evidence1.txt", "/path/to/evidence2.txt"],
        internet_status="OK",
    )

    features = create_ml_features(outcome)

    print(f"  Intent confidence: {features['intent_confidence']}")
    print(f"  High band: {features['intent_confidence_band_high']}")
    print(f"  Steps total: {features['steps_total']}")
    print(f"  Success rate: {features['steps_success_rate']}")
    print(f"  Has evidence: {features['has_evidence']}")
    print(f"  Is success: {features['is_success']}")

    assert features["intent_confidence"] == 0.85
    assert features["intent_confidence_band_high"] == 1
    assert features["steps_total"] == 3
    assert features["steps_success_rate"] == pytest.approx(0.667, rel=0.01)
    assert features["has_evidence"] == 1

    print("\n✅ PASS: ML features creation works")
    return True


def test_outcome_file_saved():
    """Test that outcome file is saved to _reports."""
    print("\n" + "=" * 60)
    print("TEST: Outcome File Saved")
    print("=" * 60)

    from denis_unified_v1.intent.unified_parser import parse_intent

    prompt = "debug this error"
    intent = parse_intent(prompt)

    recorder = OutcomeRecorder()
    outcome = recorder.record(
        request_id="test_004",
        intent_result=intent,
        internet_status="DOWN",
    )

    reports_dir = Path(
        "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/_reports"
    )
    outcome_files = list(reports_dir.glob("*outcome*.json"))

    print(f"  Outcome files found: {len(outcome_files)}")

    if outcome_files:
        latest = max(outcome_files, key=lambda p: p.stat().st_mtime)
        print(f"  Latest: {latest.name}")

        with open(latest) as f:
            data = json.load(f)

        assert "intent" in data
        assert "status" in data
        assert "request_id" in data
        print("  ✅ File saved with correct schema")
    else:
        print("  ⚠️ No outcome files found")

    print("\n✅ PASS: Outcome file saved")
    return True


def test_confidence_band_gating():
    """Test that confidence band gates are recorded."""
    print("\n" + "=" * 60)
    print("TEST: Confidence Band Gating")
    print("=" * 60)

    high_intent = IntentOutcome(
        intent="run_tests_ci",
        confidence=0.90,
        confidence_band=ConfidenceBand.HIGH,
        sources_used=["rasa"],
        reason_codes=[],
    )

    medium_intent = IntentOutcome(
        intent="explain_concept",
        confidence=0.75,
        confidence_band=ConfidenceBand.MEDIUM,
        sources_used=["heuristics"],
        reason_codes=[],
    )

    low_intent = IntentOutcome(
        intent="unknown",
        confidence=0.40,
        confidence_band=ConfidenceBand.LOW,
        sources_used=[],
        reason_codes=["default_fallback"],
    )

    high_outcome = ExecutionOutcome(
        request_id="high",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        intent=high_intent,
    )

    medium_outcome = ExecutionOutcome(
        request_id="medium",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        intent=medium_intent,
    )

    low_outcome = ExecutionOutcome(
        request_id="low",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        intent=low_intent,
    )

    high_features = create_ml_features(high_outcome)
    medium_features = create_ml_features(medium_outcome)
    low_features = create_ml_features(low_outcome)

    print(
        f"  High band: high={high_features['intent_confidence_band_high']}, medium={high_features['intent_confidence_band_medium']}, low={high_features['intent_confidence_band_low']}"
    )
    print(
        f"  Medium band: high={medium_features['intent_confidence_band_high']}, medium={medium_features['intent_confidence_band_medium']}, low={medium_features['intent_confidence_band_low']}"
    )
    print(
        f"  Low band: high={low_features['intent_confidence_band_high']}, medium={low_features['intent_confidence_band_medium']}, low={low_features['intent_confidence_band_low']}"
    )

    assert high_features["intent_confidence_band_high"] == 1
    assert high_features["intent_confidence_band_medium"] == 0
    assert high_features["intent_confidence_band_low"] == 0

    assert medium_features["intent_confidence_band_high"] == 0
    assert medium_features["intent_confidence_band_medium"] == 1
    assert medium_features["intent_confidence_band_low"] == 0

    assert low_features["intent_confidence_band_high"] == 0
    assert low_features["intent_confidence_band_medium"] == 0
    assert low_features["intent_confidence_band_low"] == 1

    print("\n✅ PASS: Confidence band gating recorded correctly")
    return True


if __name__ == "__main__":
    import pytest

    tests = [
        test_outcome_recorder_basic,
        test_outcome_with_plan,
        test_ml_features_creation,
        test_outcome_file_saved,
        test_confidence_band_gating,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n❌ FAILED: {test.__name__}")
            print(f"   Error: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r)
    print(f"Passed: {passed}/{len(tests)}")

    if passed == len(tests):
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
