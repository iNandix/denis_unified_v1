from __future__ import annotations

from denis_unified_v1.actions.models import *
from denis_unified_v1.actions.stop_eval import eval_stop_condition
from pathlib import Path
import uuid
import logging
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_candidate_plans(intent_v1: Intent_v1) -> list[ActionPlanCandidate]:
    """Generate candidate plans. Uses Neo4j graph first, falls back to hardcoded."""
    # Try grafocentric resolution first
    try:
        from denis_unified_v1.actions.graph_intent_resolver import (
            generate_candidate_plans_from_graph,
        )
        candidates = generate_candidate_plans_from_graph(intent_v1)
        if candidates:
            return candidates
    except Exception as e:
        logger.debug(f"Graph resolver unavailable, using legacy: {e}")

    # Legacy hardcoded fallback
    return _generate_candidate_plans_legacy(intent_v1)


def _generate_candidate_plans_legacy(intent_v1: Intent_v1) -> list[ActionPlanCandidate]:
    """Legacy hardcoded plan generation (fallback when graph is unavailable)."""
    if intent_v1.intent == "run_tests_ci":
        return _generate_run_tests_ci_candidates()
    elif intent_v1.intent == "debug_repo":
        return _generate_debug_repo_candidates()
    elif intent_v1.intent == "ops_health_check":
        return _generate_ops_health_check_candidates()
    elif intent_v1.intent == "implement_feature":
        return _generate_implement_feature_candidates()
    return []


def select_plan(candidates: list[ActionPlanCandidate], confidence_band: str, constraints: dict = None) -> ActionPlanCandidate | None:
    constraints = constraints or {}
    read_only = [c for c in candidates if not c.is_mutating]
    mutating = [c for c in candidates if c.is_mutating]

    if confidence_band == "low":
        if read_only:
            return read_only[0]
    elif confidence_band == "medium":
        if read_only:
            return read_only[0]
    elif confidence_band == "high":
        if "read_only" in constraints or "offline_strict" in constraints:
            if read_only:
                return read_only[0]
        else:
            if mutating:
                return mutating[0]
        if read_only:
            return read_only[0]
    return None


def save_action_plan_snapshot(plan_set: ActionPlanSet, reports_dir: Path):
    data = plan_set.model_dump()
    ts_clean = plan_set.ts_utc.replace(':', '').replace('-', '').replace('T', '_').replace('Z', '')
    filename = f"{ts_clean}_{plan_set.request_id}_action_plan_snapshot.json"
    path = reports_dir / filename
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def create_and_save_action_plan_snapshot(intent_v1: Intent_v1, candidates: list[ActionPlanCandidate], selected: ActionPlanCandidate, reports_dir: Path):
    plan_set = ActionPlanSet(
        ts_utc=_utc_now(),
        request_id="req_" + uuid.uuid4().hex[:8],
        intent=intent_v1.model_dump(),
        candidates=[{
            "candidate_id": c.candidate_id,
            "risk_level": c.risk_level.value,
            "estimated_tokens": c.estimated_tokens,
            "is_mutating": c.is_mutating,
            "requires_internet": c.requires_internet,
            "num_steps": len(c.steps),
            "num_read_only": sum(1 for s in c.steps if s.read_only),
            "num_mutating": sum(1 for s in c.steps if not s.read_only)
        } for c in candidates],
        selected_candidate_id=selected.candidate_id,
        selection_reason_codes=["band_" + intent_v1.confidence_band + "_forces_read_only" if not selected.is_mutating else "high_confidence_allows_mutating"]
    )
    save_action_plan_snapshot(plan_set, reports_dir)


def _generate_run_tests_ci_candidates() -> list[ActionPlanCandidate]:
    plan_a = ActionPlanCandidate(
        candidate_id="run_tests_ci_fast_triage",
        intent="run_tests_ci",
        risk_level=RiskLevel.low,
        estimated_tokens=120,
        is_mutating=False,
        steps=[
            ActionStep(
                step_id="collect_test_context",
                description="Gather test files and config",
                read_only=True,
                tool_calls=[ToolCall(name="list_files", args={"pattern": "*test*.py"})],
                evidence_required=["test_files_found"],
                stop_if=[StopCondition(key="no_test_files_found", op=StopOp.is_true)]
            ),
            ActionStep(
                step_id="run_quick_test",
                description="Run pytest with minimal output",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "pytest -q --tb=no"})],
                evidence_required=["exit_code", "summary_line"],
                stop_if=[StopCondition(key="exit_code", op=StopOp.eq, value=0)]
            )
        ]
    )
    plan_b = ActionPlanCandidate(
        candidate_id="run_tests_ci_deep_fix",
        intent="run_tests_ci",
        risk_level=RiskLevel.medium,
        estimated_tokens=520,
        is_mutating=True,
        steps=[
            ActionStep(
                step_id="run_full_test",
                description="Run pytest with full output",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "pytest -v"})],
                evidence_required=["full_output", "exit_code"],
                stop_if=[StopCondition(key="exit_code", op=StopOp.eq, value=0)]
            ),
            ActionStep(
                step_id="apply_fixes",
                description="Apply automatic fixes to failing tests",
                read_only=False,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo 'Fixes applied'"})],
                evidence_required=["fixes_applied"],
                stop_if=[]
            )
        ]
    )
    return [plan_a, plan_b]


def _generate_debug_repo_candidates() -> list[ActionPlanCandidate]:
    plan_a = ActionPlanCandidate(
        candidate_id="debug_repo_context_gather",
        intent="debug_repo",
        risk_level=RiskLevel.low,
        estimated_tokens=150,
        is_mutating=False,
        steps=[
            ActionStep(
                step_id="collect_error_logs",
                description="Find recent error logs or traces",
                read_only=True,
                tool_calls=[ToolCall(name="grep_search", args={"pattern": "ERROR|Exception"})],
                evidence_required=["error_lines_found", "file_paths"],
                stop_if=[StopCondition(key="no_errors_found", op=StopOp.is_true)]
            ),
            ActionStep(
                step_id="analyze_recent_changes",
                description="Check git log for recent changes",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "git log --oneline -10"})],
                evidence_required=["commits_list", "changed_files"],
                stop_if=[]
            )
        ]
    )
    plan_b = ActionPlanCandidate(
        candidate_id="debug_repo_reproduce_and_fix",
        intent="debug_repo",
        risk_level=RiskLevel.high,
        estimated_tokens=800,
        is_mutating=True,
        steps=[
            ActionStep(
                step_id="check_error_presence",
                description="Check if there are recent errors or logs",
                read_only=True,
                tool_calls=[ToolCall(name="grep_search", args={"pattern": "ERROR|Exception"})],
                evidence_required=["error_lines_found"],
                stop_if=[StopCondition(key="no_error_found", op=StopOp.is_true)]
            ),
            ActionStep(
                step_id="reproduce_issue",
                description="Attempt to reproduce the issue",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo 'Reproduce attempt'"})],
                evidence_required=["reproduce_attempted"],
                stop_if=[]
            )
        ]
    )
    return [plan_a, plan_b]


def _generate_ops_health_check_candidates() -> list[ActionPlanCandidate]:
    plan_a = ActionPlanCandidate(
        candidate_id="ops_health_check_quick_health",
        intent="ops_health_check",
        risk_level=RiskLevel.low,
        estimated_tokens=50,
        is_mutating=False,
        steps=[
            ActionStep(
                step_id="check_services",
                description="Ping key services/endpoints",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "curl -s http://localhost:3001/healthz"})],
                evidence_required=["health_response", "status_codes"],
                stop_if=[StopCondition(key="services_down", op=StopOp.is_true)]
            ),
            ActionStep(
                step_id="disk_space",
                description="Check disk usage",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "df -h"})],
                evidence_required=["disk_usage_pct", "warnings"],
                stop_if=[StopCondition(key="disk_usage_pct", op=StopOp.gte, value=95)]
            )
        ]
    )
    plan_b = ActionPlanCandidate(
        candidate_id="ops_health_check_deep_diagnostics",
        intent="ops_health_check",
        risk_level=RiskLevel.medium,
        estimated_tokens=300,
        is_mutating=False,
        steps=[
            ActionStep(
                step_id="full_system_check",
                description="Run comprehensive health checks",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "systemctl status"})],
                evidence_required=["service_statuses", "error_logs"],
                stop_if=[StopCondition(key="critical_services_down", op=StopOp.is_true)]
            )
        ]
    )
    return [plan_a, plan_b]


def _generate_implement_feature_candidates() -> list[ActionPlanCandidate]:
    plan_a = ActionPlanCandidate(
        candidate_id="implement_feature_analyze_requirements",
        intent="implement_feature",
        risk_level=RiskLevel.low,
        estimated_tokens=200,
        is_mutating=False,
        steps=[
            ActionStep(
                step_id="gather_context",
                description="Understand current code structure",
                read_only=True,
                tool_calls=[ToolCall(name="list_files", args={"directory": "src"})],
                evidence_required=["code_structure", "relevant_files"],
                stop_if=[StopCondition(key="unclear_requirements", op=StopOp.is_true)]
            ),
            ActionStep(
                step_id="design_sketch",
                description="Outline implementation approach",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo 'Design sketch'"})],
                evidence_required=["design_doc", "risk_assessment"],
                stop_if=[StopCondition(key="high_risk", op=StopOp.is_true)]
            )
        ]
    )
    plan_b = ActionPlanCandidate(
        candidate_id="implement_feature_implement_and_test",
        intent="implement_feature",
        risk_level=RiskLevel.high,
        estimated_tokens=1000,
        is_mutating=True,
        steps=[
            ActionStep(
                step_id="implement_core",
                description="Write the core feature code",
                read_only=False,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo 'Implement core'"})],
                evidence_required=["code_added"],
                stop_if=[]
            )
        ]
    )
    return [plan_a, plan_b]
