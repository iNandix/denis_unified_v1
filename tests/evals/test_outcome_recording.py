"""P1.3 Outcome Recording Tests.

Tests the telemetry/outcome recording system with P1.3 mode selection.
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
    ExecutionMode,
    InternetStatus,
    ReasonCode,
    select_mode,
    get_internet_status,
    get_allow_boosters,
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
        internet_status=InternetStatus.OK,
    )

    print(f"  Request ID: {outcome.request_id}")
    print(f"  Intent: {outcome.intent.intent}")
    print(f"  Confidence: {outcome.intent.confidence:.2f}")
    print(f"  Band: {outcome.intent.confidence_band}")
    print(f"  Selected Mode: {outcome.selected_mode}")
    print(f"  Status: {outcome.status}")

    assert outcome.request_id == "test_001"
    assert outcome.intent.intent is not None
    assert outcome.intent.confidence >= 0.0
    assert outcome.internet_status == InternetStatus.OK
    assert outcome.selected_mode in ExecutionMode

    print("\n✅ PASS: Basic outcome recording works")
    return True


def test_mode_selection_offline():
    """Test: When internet DOWN, mode should be DIRECT_LOCAL or DEGRADED."""
    print("\n" + "=" * 60)
    print("TEST: Mode Selection - Offline")
    print("=" * 60)

    mode, reasons = select_mode(
        ConfidenceBand.HIGH,
        "chat",
        InternetStatus.DOWN,
        True,  # allow_boosters=True but should be ignored
    )

    print(f"  Mode: {mode}")
    print(f"  Reasons: {reasons}")

    assert mode in [ExecutionMode.DIRECT_LOCAL, ExecutionMode.DIRECT_DEGRADED_LOCAL]
    assert ReasonCode.OFFLINE_MODE in reasons

    print("\n✅ PASS: Offline mode selection works")
    return True


def test_mode_selection_boosters_disabled():
    """Test: When boosters disabled, mode should be DIRECT_LOCAL."""
    print("\n" + "=" * 60)
    print("TEST: Mode Selection - Boosters Disabled")
    print("=" * 60)

    mode, reasons = select_mode(
        ConfidenceBand.HIGH,
        "chat",
        InternetStatus.OK,
        False,  # allow_boosters=False
    )

    print(f"  Mode: {mode}")
    print(f"  Reasons: {reasons}")

    assert mode in [ExecutionMode.DIRECT_LOCAL, ExecutionMode.DIRECT_DEGRADED_LOCAL]
    assert ReasonCode.BOOSTERS_DISABLED in reasons

    print("\n✅ PASS: Boosters disabled mode works")
    return True


def test_mode_selection_clarify_low_confidence():
    """Test: Low confidence always -> CLARIFY."""
    print("\n" + "=" * 60)
    print("TEST: Mode Selection - Low Confidence")
    print("=" * 60)

    mode, reasons = select_mode(
        ConfidenceBand.LOW,
        "anything",
        InternetStatus.OK,
        True,
    )

    print(f"  Mode: {mode}")
    print(f"  Reasons: {reasons}")

    assert mode == ExecutionMode.CLARIFY
    assert ReasonCode.CLARIFY_LOW_CONFIDENCE in reasons

    print("\n✅ PASS: Low confidence clarification works")
    return True


def test_mode_selection_core_intent():
    """Test: Core-code intents -> ACTIONS_PLAN."""
    print("\n" + "=" * 60)
    print("TEST: Mode Selection - Core Intent")
    print("=" * 60)

    for intent in [
        "run_tests_ci",
        "debug_repo",
        "refactor_migration",
        "implement_feature",
    ]:
        mode, reasons = select_mode(
            ConfidenceBand.HIGH,
            intent,
            InternetStatus.OK,
            True,
        )
        print(f"  {intent} -> {mode}")
        assert mode == ExecutionMode.ACTIONS_PLAN

    print("\n✅ PASS: Core intent mode works")
    return True


def test_mode_selection_boosted():
    """Test: Normal case -> DIRECT_BOOSTED."""
    print("\n" + "=" * 60)
    print("TEST: Mode Selection - Boosted")
    print("=" * 60)

    mode, reasons = select_mode(
        ConfidenceBand.HIGH,
        "chat",
        InternetStatus.OK,
        True,
    )

    print(f"  Mode: {mode}")
    print(f"  Reasons: {reasons}")

    assert mode == ExecutionMode.DIRECT_BOOSTED

    print("\n✅ PASS: Boosted mode works")
    return True


def test_ml_features_p1_3():
    """Test ML features creation with P1.3 fields."""
    print("\n" + "=" * 60)
    print("TEST: ML Features P1.3")
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
        selected_mode=ExecutionMode.ACTIONS_PLAN,
        allow_boosters=False,
        internet_status=InternetStatus.DOWN,
        plan=plan_outcome,
        status=OutcomeStatus.DEGRADED,
        steps=step_outcomes,
        total_duration_ms=350,
        evidence_artifacts=["/path/to/evidence1.txt", "/path/to/evidence2.txt"],
        degraded=True,
        reason_codes=[ReasonCode.OFFLINE_MODE, ReasonCode.STEP_FAILED],
    )

    features = create_ml_features(outcome)

    print(f"  Intent confidence: {features['intent_confidence']}")
    print(f"  Mode actions_plan: {features['mode_actions_plan']}")
    print(f"  Degraded: {features['degraded']}")
    print(f"  Internet OK: {features['internet_ok']}")
    print(f"  Reason offline: {features['reason_offline']}")
    print(f"  Is success: {features['is_success']}")

    assert features["intent_confidence"] == 0.85
    assert features["mode_actions_plan"] == 1
    assert features["degraded"] == 1
    assert features["internet_ok"] == 0
    assert features["reason_offline"] == 1

    print("\n✅ PASS: ML features P1.3 works")
    return True


def test_reason_codes():
    """Test P1.3 reason codes."""
    print("\n" + "=" * 60)
    print("TEST: Reason Codes")
    print("=" * 60)

    codes = [
        ReasonCode.SUCCESS,
        ReasonCode.OFFLINE_MODE,
        ReasonCode.BOOSTERS_DISABLED,
        ReasonCode.LOW_CONFIDENCE,
        ReasonCode.CLARIFY_LOW_CONFIDENCE,
    ]

    for code in codes:
        print(f"  {code.value}")

    assert len(codes) > 0

    print("\n✅ PASS: Reason codes work")
    return True


if __name__ == "__main__":
    tests = [
        test_outcome_recorder_basic,
        test_mode_selection_offline,
        test_mode_selection_boosters_disabled,
        test_mode_selection_clarify_low_confidence,
        test_mode_selection_core_intent,
        test_mode_selection_boosted,
        test_ml_features_p1_3,
        test_reason_codes,
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
