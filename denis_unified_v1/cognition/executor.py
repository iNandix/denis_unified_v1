"""Cognition Module - Loop 3 & 4: Execution and Introspection.

Provides:
- Executor: Evidence-based tool execution
- Evaluator: Result evaluation against acceptance criteria
- ReentryController: Manages iteration (max 2 re-entries)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from denis_unified_v1.actions.models import ActionPlanCandidate, ActionStep, StepStatus
from denis_unified_v1.cognition.legacy_tools_v2 import build_tool_registry_v2, ToolResult


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

    # Persona: tono cálido pero irónico, spicy a veces, directo sin pudor
    PERSONA_TONE = {
        "prefixes": [
            "Voy a",
            "Dejame",
            "A ver",
            "Miro",
            "Busco",
            "Ejecuto",
            "Esto... ",
            "Uy, ",
            "Anda, ",
            "Vaya, ",
        ],
        "success_suffixes": [
            "listo",
            "hecho",
            "tigre",
            " OK",
            " ✅",
            "sin problemas",
            "como un lujo",
            "perfecto",
        ],
        "failure_suffixes": [
            "ha petao",
            "no ha podido",
            "se ha resistencia",
            "ha fallado",
            "uff...",
            "vaya... ",
        ],
        "spicy_chance": 0.15,  # 15% de probabilidad de ser spicy
    }

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Any]] = None,
        evidence_dir: Optional[Path] = None,
        emit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.tool_registry = tool_registry or build_tool_registry_v2()
        self.evidence_dir = evidence_dir or Path(
            "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/_reports"
        )
        self._emit_callback = emit_callback

    def set_emit_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set the emit callback for narrative events."""
        self._emit_callback = callback

    @property
    def emit_callback(self):
        return self._emit_callback

    def _emit_narrative(self, text: str, request_id: str = "default"):
        """Emit narrative text to frontend via callback."""
        if self.emit_callback:
            self.emit_callback(
                {
                    "request_id": request_id,
                    "type": "render.text.delta",
                    "payload": {"text": text},
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _generate_narrative(self, tool_name: str, will_execute: bool = True) -> str:
        """Generate persona narrative for tool execution."""
        import random

        prefixes = self.PERSONA_TONE["prefixes"]

        # Tool-specific narratives
        tool_narratives = {
            "grep_search": [
                "buscando en archivos...",
                "a ver si aparece...",
                "tiro grep a ver qué sale...",
            ],
            "read_file": [
                "leyendo el archivo...",
                "voy a échale un ojo...",
                "a ver qué hay aquí...",
            ],
            "list_files": [
                "listando...",
                "a ver qué tenemos por aquí...",
                "mirando estructura...",
            ],
            "run_command": [
                "ejecutando comando...",
                "tiro el comando a ver qué pasa...",
                "a riesgos de todo...",
            ],
            "hass_entity": [
                "tocando Home Assistant...",
                "manipulando entidades...",
                "un poco de domótica...",
            ],
            "default": ["ejecutando...", "haciendo cosas...", "trabajando en ello..."],
        }

        prefix = random.choice(prefixes)
        narratives = tool_narratives.get(tool_name, tool_narratives["default"])
        middle = random.choice(narratives)

        # Sometimes be spicy
        spicy = random.random() < self.PERSONA_TONE["spicy_chance"]
        if spicy:
            spicies = [
                "... esto está más caliente que mi procesador.",
                "... esto va a hacer que argon-18 se pone nervioso.",
                "... prepárate para el show.",
                "... esto es más interesante que una conversación de pub.",
            ]
            middle += random.choice(spicies)

        return f"{prefix} {middle}"

    def _generate_result_narrative(
        self, tool_name: str, ok: bool, duration_ms: int
    ) -> str:
        """Generate result narrative."""
        import random

        suffixes = (
            self.PERSONA_TONE["success_suffixes"]
            if ok
            else self.PERSONA_TONE["failure_suffixes"]
        )
        suffix = random.choice(suffixes)

        if ok:
            templates = [
                f"Completado en {duration_ms}ms. {suffix}",
                f"{suffix.capitalize()} ({duration_ms}ms)",
                f"Finiquitado. {suffix}",
            ]
        else:
            templates = [
                f"No ha podido. {suffix}",
                f"Ha petao. {suffix}",
                f"uff... {suffix}",
            ]

        return random.choice(templates)

    def _is_tool_allowed(
        self, tool_name: str, intent: str, band: str,
        consciousness: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Belt filtering for speed and safety.

        WS23-G: when consciousness.guardrails_mode == "strict" or
        consciousness.mode == "degraded", only read-only tools are allowed.
        """
        if band == "low":
            return False
        # WS23-G: strict guardrails -> read-only tools only
        cs = consciousness or {}
        if cs.get("guardrails_mode") == "strict" or cs.get("mode") == "degraded":
            return tool_name in ["list_files", "grep_search", "read_file"]
        if tool_name in ["list_files", "grep_search", "read_file"]:
            return True  # ide.fs belt
        if tool_name == "run_command":
            return band == "high"  # ide.exec belt only high
        return True

    def execute_step(
        self,
        step: ActionStep,
        context: Dict[str, Any],
    ) -> StepExecutionResult:
        """Execute a single step with evidence capture."""
        import time

        start_time = time.perf_counter()
        result = StepExecutionResult(step_id=step.step_id, status=StepStatus.ok)
        intent = context.get("intent", "")
        # Default to high for direct executor usage/tests; policy layers should set explicit band.
        band = context.get("confidence_band", "high")
        request_id = context.get("request_id", "default")
        # WS23-G: consciousness state (fail-open, dict or None)
        consciousness = context.get("consciousness")

        try:
            for tool_call in step.tool_calls:
                if not self._is_tool_allowed(tool_call.name, intent, band, consciousness):
                    result.status = StepStatus.failed
                    result.error = f"Tool not allowed by belt: {tool_call.name}"
                    result.reason_codes.append("belt_filtered")
                    continue

                tool_adapter = self.tool_registry.get(tool_call.name)
                if not tool_adapter:
                    result.status = StepStatus.failed
                    result.error = f"Tool not found: {tool_call.name}"
                    continue

                # === NARRATIVE HOOK: Antes de ejecutar ===
                if self.emit_callback:
                    before_text = self._generate_narrative(
                        tool_call.name, will_execute=True
                    )
                    self._emit_narrative(before_text, request_id)

                # Run async tool in sync context
                if hasattr(tool_adapter, "run"):
                    tool_result = asyncio.run(tool_adapter.run(context, tool_call.args))
                elif callable(tool_adapter):
                    # Allow simple callables in tests (lambda **kw: "ok") without full adapter wrapper.
                    try:
                        out = tool_adapter(**(tool_call.args or {}))
                    except TypeError:
                        out = tool_adapter(context=context, **(tool_call.args or {}))
                    tool_result = ToolResult(ok=True, data={"text": str(out)}, error=None)
                else:
                    tool_result = ToolResult(
                        ok=False,
                        data={},
                        error={"type": "tool", "message": f"Invalid tool adapter: {tool_call.name}"},
                    )
                if tool_result.ok:
                    output = tool_result.data.get("text", "")
                    result.output = str(output)
                    self._extract_facts(output, result.facts)
                    if step.evidence_required:
                        self._capture_evidence(step.step_id, output, result)
                else:
                    result.status = StepStatus.failed
                    result.error = (
                        tool_result.error.get("message", str(tool_result.error))
                        if tool_result.error
                        else "tool_failed"
                    )
                    result.reason_codes.append("tool_policy_error")

                # === NARRATIVE HOOK: Después de ejecutar ===
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                if self.emit_callback:
                    after_text = self._generate_result_narrative(
                        tool_call.name, tool_result.ok, duration_ms
                    )
                    self._emit_narrative(after_text, request_id)

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
                tc.name for tc in step.tool_calls if tc.name not in self.tool_registry
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
