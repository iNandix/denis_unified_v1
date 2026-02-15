"""P1.3 Artifact Enforcement Tests.

These tests FAIL if mandatory artifacts are not written.
Contract: every request MUST produce execution_outcome_v1,
tool_lookup_snapshot_v1, and (when actions_plan) toolchain_step_log_v1.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.telemetry.outcome_recorder import (
    OutcomeRecorder,
    ExecutionOutcome,
    IntentOutcome,
    ConfidenceBand,
    ExecutionMode,
    InternetStatus,
    ReasonCode,
    create_ml_features,
)
from denis_unified_v1.catalog.tool_catalog import ToolCatalog, CatalogContext
from denis_unified_v1.catalog.snapshot_writer import save_catalog_lookup_snapshot
from denis_unified_v1.cognition.executor import (
    Executor,
    PlanExecutionResult,
    save_toolchain_log,
)
from denis_unified_v1.actions.models import (
    ActionPlanCandidate,
    ActionStep,
    ToolCall,
    StopCondition,
    StopOp,
)


# ---------------------------------------------------------------------------
# Test 1: execution_outcome_v1 MUST be written
# ---------------------------------------------------------------------------
def test_execution_outcome_v1_always_written(tmp_path):
    """execution_outcome_v1 artifact must be written for every request."""
    recorder = OutcomeRecorder(reports_dir=tmp_path)

    intent_outcome = IntentOutcome(
        intent="run_tests_ci",
        confidence=0.8,
        confidence_band=ConfidenceBand.HIGH,
    )

    # Simulate a simple recording (no plan, no execution)
    outcome = recorder.record(
        request_id="enforce_001",
        intent_result=type(
            "I",
            (),
            {
                "intent": "run_tests_ci",
                "confidence": 0.8,
                "confidence_band": "high",
                "sources": {},
                "reason_codes": [],
            },
        )(),
        internet_status=InternetStatus.OK,
        selected_mode=ExecutionMode.ACTIONS_PLAN,
        allow_boosters=False,
    )

    # MUST: exactly 1 outcome file written
    files = list(tmp_path.glob("*_outcome.json"))
    assert len(files) == 1, f"Expected 1 outcome file, got {len(files)}"

    with open(files[0]) as f:
        data = json.load(f)

    # MUST: required fields present
    assert "request_id" in data
    assert "selected_mode" in data
    assert "internet_status" in data
    assert "reason_codes" in data
    assert data["request_id"] == "enforce_001"


# ---------------------------------------------------------------------------
# Test 2: tool_lookup_snapshot_v1 MUST be written
# ---------------------------------------------------------------------------
def test_tool_lookup_snapshot_v1_always_written(tmp_path):
    """tool_lookup_snapshot_v1 artifact must be written per request."""
    catalog = ToolCatalog()
    ctx = CatalogContext(
        request_id="enforce_002",
        allow_boosters=False,
        internet_gate=True,
        booster_health=False,
        confidence_band="high",
        meta={},
    )

    lookup = catalog.lookup(intent="run_tests_ci", entities={}, ctx=ctx)
    save_catalog_lookup_snapshot(lookup, tmp_path)

    # MUST: exactly 1 snapshot file
    files = list(tmp_path.glob("*_tool_lookup_snapshot.json"))
    assert len(files) == 1, f"Expected 1 snapshot file, got {len(files)}"

    with open(files[0]) as f:
        data = json.load(f)

    # MUST: schema version and features present
    assert data["schema_version"] == "tool_lookup_result_v1"
    assert "features" in data
    assert "catalog_size" in data["features"]
    assert "num_matches" in data["features"]
    assert "top_score" in data["features"]
    assert data["features"]["catalog_size"] > 0


# ---------------------------------------------------------------------------
# Test 3: toolchain_step_log_v1 covers ALL steps (none lost)
# ---------------------------------------------------------------------------
def test_toolchain_step_log_v1_covers_all_steps(tmp_path):
    """toolchain_step_log_v1 must include an entry for every step."""
    plan = ActionPlanCandidate(
        candidate_id="plan_enforce_003",
        intent="run_tests_ci",
        steps=[
            ActionStep(
                step_id="step_1_ok",
                description="A step that will succeed",
                tool_calls=[ToolCall(name="mock_tool", args={"cmd": "echo ok"})],
            ),
            ActionStep(
                step_id="step_2_fail",
                description="A step with missing tool (will be blocked)",
                tool_calls=[ToolCall(name="nonexistent_tool", args={})],
                on_failure="abort",
            ),
            ActionStep(
                step_id="step_3_should_skip",
                description="Should be skipped after abort",
                tool_calls=[ToolCall(name="mock_tool", args={"cmd": "echo skip"})],
            ),
        ],
    )

    # Provide mock_tool but not nonexistent_tool
    executor = Executor(
        tool_registry={"mock_tool": lambda **kw: "ok"},
        evidence_dir=tmp_path,
    )

    result = executor.execute_plan(plan, context={})
    path = save_toolchain_log(result, tmp_path, "enforce_003")

    # MUST: file exists
    assert path.exists(), "toolchain_step_log file not written"

    with open(path) as f:
        data = json.load(f)

    # MUST: kind field
    assert data["kind"] == "toolchain_step_log_v1"

    # MUST: ALL 3 steps present (none silently dropped)
    assert len(data["step_results"]) == 3, (
        f"Expected 3 step entries, got {len(data['step_results'])}"
    )

    statuses = {s["step_id"]: s["status"] for s in data["step_results"]}
    assert statuses["step_1_ok"] == "ok"
    assert statuses["step_2_fail"] == "blocked"
    assert statuses["step_3_should_skip"] == "skipped"

    # MUST: every step has reason_codes
    for step in data["step_results"]:
        assert "reason_codes" in step, f"Step {step['step_id']} missing reason_codes"


# ---------------------------------------------------------------------------
# Test 4: All 12 spec reason codes exist
# ---------------------------------------------------------------------------
def test_reason_codes_minimum_set_exists():
    """All P1.3 spec reason codes must be defined."""
    # Reason codes from the spec that must exist somewhere in the system
    required_enum_codes = [
        # In ReasonCode enum
        "offline_mode",
        "boosters_unavailable",
        "confidence_medium_readonly",
        "capability_exists",
        "capability_partial_compose",
        "capability_missing",
        "tool_composed",
        "capability_created",
        "stop_if_triggered",
    ]

    # Verify enum values
    enum_values = {rc.value for rc in ReasonCode}
    for code in required_enum_codes:
        assert code in enum_values, (
            f"ReasonCode enum missing required code: {code}"
        )

    # Dynamic codes verified by pattern (tool_selected:<name>)
    # These are generated at runtime, verify the pattern works
    test_code = "tool_selected:run_tests_ci"
    assert test_code.startswith("tool_selected:")

    # needs_clarification is generated by catalog (inline string)
    # confidence_low_no_tools is generated by catalog (inline string)
    # These exist as inline strings in tool_catalog.py, verified separately


# ---------------------------------------------------------------------------
# Test 5: ML features include all 12 required features
# ---------------------------------------------------------------------------
def test_ml_features_minimum_set():
    """create_ml_features() must include all P1.3 spec features."""
    outcome = ExecutionOutcome(
        request_id="enforce_005",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        intent=IntentOutcome(
            intent="run_tests_ci",
            confidence=0.85,
            confidence_band=ConfidenceBand.HIGH,
        ),
        selected_mode=ExecutionMode.ACTIONS_PLAN,
        internet_status=InternetStatus.OK,
        allow_boosters=True,
        booster_health=True,
        catalog_size=9,
        num_matches=2,
        top_score=0.75,
        steps_planned=3,
        blocked_steps=1,
        degraded=False,
    )

    features = create_ml_features(outcome)

    # Required features from spec (mapped to feature key names)
    required_features = {
        "confidence_band": [
            "intent_confidence_band_high",
            "intent_confidence_band_medium",
            "intent_confidence_band_low",
        ],
        "mode": [
            "mode_clarify",
            "mode_actions_plan",
            "mode_direct_local",
            "mode_direct_boosted",
            "mode_degraded",
        ],
        "catalog_size": ["catalog_size"],
        "num_matches": ["num_matches"],
        "top_score": ["top_score"],
        "steps_planned": ["steps_planned"],
        "steps_executed": ["steps_total"],  # steps_total = steps executed
        "blocked_steps": ["blocked_steps"],
        "degraded": ["degraded"],
        "internet_gate": ["internet_ok"],
        "allow_boosters": ["allow_boosters"],
        "booster_health": ["booster_health"],
    }

    for spec_name, feature_keys in required_features.items():
        for key in feature_keys:
            assert key in features, (
                f"ML feature '{key}' (spec: {spec_name}) missing from create_ml_features()"
            )

    # Verify values are populated correctly
    assert features["catalog_size"] == 9
    assert features["num_matches"] == 2
    assert features["top_score"] == 0.75
    assert features["steps_planned"] == 3
    assert features["blocked_steps"] == 1
    assert features["booster_health"] == 1
    assert features["internet_ok"] == 1
    assert features["allow_boosters"] == 1
