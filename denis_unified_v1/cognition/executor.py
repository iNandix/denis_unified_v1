"""Cognition Module - Loop 3 & 4: Execution and Introspection.

Provides:
- Executor: Evidence-based tool execution
- Evaluator: Result evaluation against acceptance criteria
- ReentryController: Manages iteration (max 2 re-entries)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from denis_unified_v1.actions.models import ActionPlanCandidate, ActionStep, StepStatus


@dataclass
class StepExecutionResult:
    """Result of executing a single step."""

    step_id: str
    status: StepStatus
    output: Optional[str] = None
    error: Optional[str] = None
    evidence_paths: List[str] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    retry_count: int = 0
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "evidence_paths": self.evidence_paths,
            "facts": self.facts,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "reason_codes": self.reason_codes,
        }


@dataclass
class PlanExecutionResult:
    """Result of executing an entire action plan."""

    plan_id: str
    status: str = "pending"  # "pending", "success", "failed", "stopped", "degraded"
    step_results: List[StepExecutionResult] = field(default_factory=list)
    total_duration_ms: int = 0
    evidence_artifacts: List[str] = field(default_factory=list)
    reason_code: Optional[str] = None
    degraded_reason: Optional[str] = None
    iterations: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status,
            "step_results": [s.to_dict() for s in self.step_results],
            "total_duration_ms": self.total_duration_ms,
            "evidence_artifacts": self.evidence_artifacts,
            "reason_code": self.reason_code,
            "degraded_reason": self.degraded_reason,
            "iterations": self.iterations,
        }


class Executor:
    """Evidence-based executor for action plans."""

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Callable]] = None,
        evidence_dir: Optional[Path] = None,
    ):
        self.tool_registry = tool_registry or {}
        self.evidence_dir = evidence_dir or Path(
            "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/_reports"
        )

    def execute_step(
        self,
        step: ActionStep,
        context: Dict[str, Any],
    ) -> StepExecutionResult:
        """Execute a single step with evidence capture."""
        import time

        start_time = time.perf_counter()
        result = StepExecutionResult(step_id=step.step_id, status=StepStatus.ok)

        try:
            for tool_call in step.tool_calls:
                tool_func = self.tool_registry.get(tool_call.name)
                if not tool_func:
                    result.status = StepStatus.failed
                    result.error = f"Tool not found: {tool_call.name}"
                    continue

                output = tool_func(**tool_call.args)
                result.output = str(output)

                self._extract_facts(output, result.facts)

                if step.evidence_required:
                    self._capture_evidence(step.step_id, output, result)

        except Exception as e:
            result.status = StepStatus.failed
            result.error = str(e)

        result.duration_ms = int((time.perf_counter() - start_time) * 1000)
        return result

    def _extract_facts(self, output: str, facts: Dict[str, Any]) -> None:
        """Extract structured facts from output."""
        if "exit_code" not in facts and output:
            facts["exit_code"] = 0 if "error" not in output.lower() else 1
        if "output_length" not in facts:
            facts["output_length"] = len(output) if output else 0

    def _capture_evidence(
        self,
        step_id: str,
        output: str,
        result: StepExecutionResult,
    ) -> None:
        """Capture evidence to file."""
        try:
            ts = (
                datetime.now(timezone.utc)
                .isoformat()
                .replace(":", "")
                .replace("-", "")
                .replace("T", "_")
            )
            filename = f"{ts}_{step_id}_evidence.txt"
            path = self.evidence_dir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(output)
            result.evidence_paths.append(str(path))
        except Exception:
            pass

    def execute_plan(
        self,
        plan: ActionPlanCandidate,
        context: Dict[str, Any],
    ) -> PlanExecutionResult:
        """Execute an entire action plan.

        Guarantees: every step in plan.steps produces a StepExecutionResult
        with status in {ok, failed, skipped, blocked} and reason_codes.
        """
        import time

        start_time = time.perf_counter()
        plan_result = PlanExecutionResult(plan_id=plan.candidate_id)
        enforce_read_only = context.get("enforce_read_only", False)
        stopped = False

        for step in plan.steps:
            # If a previous step triggered stop_if, mark remaining as skipped
            if stopped:
                plan_result.step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.skipped,
                        reason_codes=["stop_if_triggered"],
                    )
                )
                continue

            # Block mutating steps when context enforces read_only
            if enforce_read_only and not step.read_only:
                plan_result.step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.skipped,
                        reason_codes=["confidence_medium_readonly"],
                    )
                )
                continue

            # Block steps whose tools are missing from registry
            missing_tools = [
                tc.name for tc in step.tool_calls
                if tc.name not in self.tool_registry
            ]
            if step.tool_calls and missing_tools:
                plan_result.step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.blocked,
                        error=f"Tools not in registry: {missing_tools}",
                        reason_codes=["capability_missing"],
                    )
                )
                if step.on_failure == "abort":
                    plan_result.status = "failed"
                    plan_result.reason_code = f"blocked_at_{step.step_id}"
                    # Mark remaining steps as skipped
                    stopped = True
                continue

            # Execute the step normally
            step_result = self.execute_step(step, context)
            plan_result.step_results.append(step_result)

            # Evaluate stop_if conditions
            if step.stop_if:
                from denis_unified_v1.actions.stop_eval import eval_stop_condition

                for stop_cond in step.stop_if:
                    if eval_stop_condition(stop_cond, step_result.facts):
                        plan_result.status = "stopped"
                        plan_result.reason_code = f"stopped_by_{step.step_id}"
                        step_result.reason_codes.append("stop_if_triggered")
                        stopped = True
                        break

            if step_result.status == StepStatus.failed:
                step_result.reason_codes.append("step_failed")
                if step.on_failure == "abort":
                    plan_result.status = "failed"
                    plan_result.reason_code = f"failed_at_{step.step_id}"
                    stopped = True
                elif step.on_failure == "fallback":
                    plan_result.status = "degraded"
                    plan_result.degraded_reason = f"fallback_at_{step.step_id}"

        if plan_result.status == "pending":
            plan_result.status = "success"
            plan_result.reason_code = "all_steps_completed"

        plan_result.total_duration_ms = int((time.perf_counter() - start_time) * 1000)
        plan_result.evidence_artifacts = [
            p for sr in plan_result.step_results for p in sr.evidence_paths
        ]
        return plan_result


@dataclass
class EvaluationResult:
    """Result of evaluating plan execution against acceptance criteria."""

    passed: bool
    score: float  # 0.0 - 1.0
    criteria_results: Dict[str, bool] = field(default_factory=dict)
    missing_evidence: List[str] = field(default_factory=list)
    recommendation: str = ""  # "proceed", "reenter", "ask_user", "abort"


class Evaluator:
    """Evaluates execution results against acceptance criteria."""

    def evaluate(
        self,
        plan: ActionPlanCandidate,
        execution: PlanExecutionResult,
        acceptance_criteria: List[str],
    ) -> EvaluationResult:
        """Evaluate execution results against acceptance criteria."""
        criteria_results = {}
        missing_evidence = []
        passed_count = 0

        for criterion in acceptance_criteria:
            criterion_lower = criterion.lower()

            if "evidence" in criterion_lower:
                has_evidence = len(execution.evidence_artifacts) > 0
                criteria_results[criterion] = has_evidence
                if not has_evidence:
                    missing_evidence.append(criterion)
                else:
                    passed_count += 1

            elif "test" in criterion_lower or "fail" in criterion_lower:
                has_test_result = any(
                    "test" in sr.step_id.lower() for sr in execution.step_results
                )
                criteria_results[criterion] = has_test_result
                if has_test_result:
                    passed_count += 1

            elif "error" in criterion_lower or "fail" in criterion_lower:
                has_error = execution.status == "failed"
                criteria_results[criterion] = not has_error
                if not has_error:
                    passed_count += 1

            else:
                criteria_results[criterion] = True
                passed_count += 1

        score = passed_count / max(len(acceptance_criteria), 1)
        passed = score >= 0.7 and execution.status != "failed"

        recommendation = "proceed"
        if execution.status == "failed":
            recommendation = "abort"
        elif score < 0.5:
            recommendation = "reenter"
        elif missing_evidence:
            recommendation = "reenter"

        return EvaluationResult(
            passed=passed,
            score=score,
            criteria_results=criteria_results,
            missing_evidence=missing_evidence,
            recommendation=recommendation,
        )


@dataclass
class ReentryDecision:
    """Decision about whether to re-enter the planning loop."""

    should_reenter: bool
    reenter_reason: Optional[str] = None
    target_loop: int = 2  # Loop 2 = Planning
    max_iterations_reached: bool = False


class ReentryController:
    """Controls re-entry into the planning loop (max 2 iterations)."""

    MAX_ITERATIONS = 2

    def __init__(self):
        self.current_iteration = 0

    def decide(
        self,
        evaluation: EvaluationResult,
        execution: PlanExecutionResult,
        new_evidence: Optional[Dict[str, Any]] = None,
    ) -> ReentryDecision:
        """Decide whether to re-enter the planning loop."""
        self.current_iteration += 1

        if self.current_iteration >= self.MAX_ITERATIONS:
            return ReentryDecision(
                should_reenter=False,
                max_iterations_reached=True,
            )

        if evaluation.recommendation == "reenter":
            return ReentryDecision(
                should_reenter=True,
                reenter_reason=f"evaluation_recommendation:{evaluation.recommendation}",
            )

        if execution.status == "failed":
            return ReentryDecision(
                should_reenter=True,
                reenter_reason="step_failed_but_recoverable",
            )

        if new_evidence and self._evidence_changes_hypothesis(new_evidence):
            return ReentryDecision(
                should_reenter=True,
                reenter_reason="new_evidence_changes_hypothesis",
            )

        return ReentryDecision(should_reenter=False)

    def _evidence_changes_hypothesis(self, evidence: Dict[str, Any]) -> bool:
        """Check if new evidence significantly changes the hypothesis."""
        significant_keys = {"root_cause", "new_error", "unexpected_output"}
        return any(k in evidence for k in significant_keys)


def save_toolchain_log(
    execution: PlanExecutionResult,
    reports_dir: Path,
    request_id: str,
) -> Path:
    """Save toolchain execution log to _reports."""
    ts = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace(":", "")
        .replace("-", "")
        .replace("T", "_")
    )
    filename = f"{ts}_{request_id}_toolchain_step_log.json"
    path = reports_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = execution.to_dict()
    payload["kind"] = "toolchain_step_log_v1"

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

    return path
