"""P1.3 Offline / direct_local Test Coverage.

Verifies that offline scenarios produce correct mode selection,
reason codes in artifacts, and catalog penalization.
"""

import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.telemetry.outcome_recorder import (
    OutcomeRecorder,
    ConfidenceBand,
    ExecutionMode,
    InternetStatus,
    ReasonCode,
    select_mode,
)
from denis_unified_v1.catalog.tool_catalog import ToolCatalog, CatalogContext


# ---------------------------------------------------------------------------
# Test 1: Offline mode writes outcome with offline_mode reason
# ---------------------------------------------------------------------------
def test_offline_mode_writes_outcome_with_offline_reason(tmp_path):
    """Offline request must write outcome with offline_mode in reason_codes."""
    recorder = OutcomeRecorder(reports_dir=tmp_path)

    intent_stub = type(
        "I",
        (),
        {
            "intent": "chat",
            "confidence": 0.9,
            "confidence_band": "high",
            "sources": {},
            "reason_codes": [],
        },
    )()

    outcome = recorder.record(
        request_id="offline_001",
        intent_result=intent_stub,
        internet_status=InternetStatus.DOWN,
        allow_boosters=True,  # should be overridden by offline
    )

    # Verify file written
    files = list(tmp_path.glob("*_outcome.json"))
    assert len(files) == 1

    with open(files[0]) as f:
        data = json.load(f)

    assert "offline_mode" in data["reason_codes"]
    assert data["selected_mode"] in ["direct_local", "direct_degraded_local"]
    assert data["internet_status"] == "DOWN"


# ---------------------------------------------------------------------------
# Test 2: Chat intent offline -> DIRECT_DEGRADED_LOCAL
# ---------------------------------------------------------------------------
def test_offline_direct_degraded_local_chat_intent():
    """Chat intent when offline must select DIRECT_DEGRADED_LOCAL."""
    mode, reasons = select_mode(
        ConfidenceBand.HIGH,
        "chat",
        InternetStatus.DOWN,
        True,  # allow_boosters=True, but offline overrides
    )

    assert mode == ExecutionMode.DIRECT_DEGRADED_LOCAL
    assert ReasonCode.OFFLINE_MODE in reasons


# ---------------------------------------------------------------------------
# Test 3: Core intent offline -> still ACTIONS_PLAN (not degraded)
# ---------------------------------------------------------------------------
def test_offline_core_intent_still_actions_plan():
    """Core-code intents always go to ACTIONS_PLAN regardless of internet."""
    core_intents = [
        "run_tests_ci",
        "debug_repo",
        "implement_feature",
        "ops_health_check",
    ]

    for intent in core_intents:
        mode, reasons = select_mode(
            ConfidenceBand.HIGH,
            intent,
            InternetStatus.DOWN,
            True,
        )
        assert mode == ExecutionMode.ACTIONS_PLAN, (
            f"Core intent '{intent}' should be ACTIONS_PLAN even offline, got {mode}"
        )


# ---------------------------------------------------------------------------
# Test 4: Catalog penalizes internet-required tools when offline
# ---------------------------------------------------------------------------
def test_catalog_lookup_offline_penalizes_internet_tools():
    """Tools requiring internet must be penalized when internet_gate=False."""
    from denis_unified_v1.catalog.schemas_v1 import ToolCapabilityV1

    # Create catalog with one local and one internet-required tool
    catalog = ToolCatalog(
        capabilities=[
            ToolCapabilityV1(
                name="local_tool",
                type="action_tool",
                description="A local tool",
                intents=["test_intent"],
                safety="read_only",
                availability="local",
                requires_internet=False,
            ),
            ToolCapabilityV1(
                name="internet_tool",
                type="booster",
                description="A tool needing internet",
                intents=["test_intent"],
                safety="read_only",
                availability="internet",
                requires_internet=True,
            ),
        ]
    )

    ctx = CatalogContext(
        request_id="offline_004",
        allow_boosters=False,
        internet_gate=False,
        booster_health=False,
        confidence_band="high",
        meta={},
    )

    lookup = catalog.lookup(intent="test_intent", entities={}, ctx=ctx)

    # Both tools should match, but internet_tool should be penalized
    scores = {m.name: m.score for m in lookup.matched_tools}

    assert "local_tool" in scores
    assert "internet_tool" in scores
    assert scores["local_tool"] > scores["internet_tool"], (
        f"Local tool ({scores['local_tool']}) should score higher than "
        f"internet tool ({scores['internet_tool']}) when offline"
    )

    # internet_tool should have blocked_by_internet_gate reason
    internet_match = next(m for m in lookup.matched_tools if m.name == "internet_tool")
    assert "blocked_by_internet_gate" in internet_match.reason_codes
