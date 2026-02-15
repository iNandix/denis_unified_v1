"""Response Composer - Loop 4: Introspection/Synthesis.

Composes human-readable responses with DENIS persona voice,
including evidence summaries and meta signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from denis_unified_v1.cognition.executor import PlanExecutionResult, EvaluationResult


@dataclass
class PersonaResponse:
    """Final response to user with persona voice."""

    response_text: str
    meta: Dict[str, Any] = field(default_factory=dict)
    evidence_summary: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)
    degraded_reason: Optional[str] = None


class PersonaResponseComposer:
    """Composes responses with DENIS persona voice.

    Rules:
    - No chain-of-thought or internal mechanics in response
    - Evidence pointers only (no raw traces)
    - Persona voice: direct, helpful, confident when high confidence
    """

    def __init__(self, persona_name: str = "DENIS"):
        self.persona_name = persona_name

    def compose(
        self,
        user_message: str,
        intent_result: Any,
        execution_result: Optional[PlanExecutionResult],
        evaluation: Optional[EvaluationResult],
        internet_status: str = "OK",
    ) -> PersonaResponse:
        """Compose final response with persona voice."""

        if execution_result is None:
            return self._compose_no_execution(user_message, intent_result)

        response_parts = []

        if evaluation and evaluation.passed:
            response_parts.append(self._compose_success(execution_result))
        elif execution_result.status == "failed":
            response_parts.append(self._compose_failure(execution_result))
        else:
            response_parts.append(self._compose_progress(execution_result))

        response_text = " ".join(response_parts)

        evidence_summary = None
        if execution_result.evidence_artifacts:
            evidence_summary = self._summarize_evidence(
                execution_result.evidence_artifacts
            )

        next_steps = self._determine_next_steps(evaluation, execution_result)

        meta = self._build_meta(
            intent_result=intent_result,
            execution_result=execution_result,
            evaluation=evaluation,
            internet_status=internet_status,
        )

        degraded_reason = (
            execution_result.degraded_reason
            if execution_result.status == "degraded"
            else None
        )

        return PersonaResponse(
            response_text=response_text,
            meta=meta,
            evidence_summary=evidence_summary,
            next_steps=next_steps,
            degraded_reason=degraded_reason,
        )

    def _compose_no_execution(
        self, user_message: str, intent_result: Any
    ) -> PersonaResponse:
        """Compose response when no execution happened (low confidence)."""

        if (
            hasattr(intent_result, "two_plans_required")
            and intent_result.two_plans_required
        ):
            response_text = "Para ayudarte mejor, necesito entender mejor qué necesitas. Aquí van algunas opciones:\n"
            response_text += "1. Debuggear un error o problema\n"
            response_text += "2. Ejecutar tests o verificar CI\n"
            response_text += "3. Implementar una nueva feature\n"
            response_text += "4. Revisar el estado del sistema\n"
            response_text += "\n¿Cuál se acerca más a lo que necesitas?"

        elif (
            hasattr(intent_result, "needs_clarification")
            and intent_result.needs_clarification
        ):
            clarification = (
                intent_result.needs_clarification[0]
                if intent_result.needs_clarification
                else "¿Puedes dar más detalles?"
            )
            response_text = f"Para entender mejor tu solicitud: {clarification}"

        else:
            response_text = (
                "He detectado tu solicitud. ¿Cómo puedo ayudarte más específicamente?"
            )

        meta = {
            "engine_id": "intent_only",
            "llm_used": "none",
            "degraded": False,
            "internet_status": "OK",
            "confidence_band": getattr(intent_result, "confidence_band", "unknown"),
        }

        return PersonaResponse(
            response_text=response_text,
            meta=meta,
        )

    def _compose_success(self, execution: PlanExecutionResult) -> str:
        """Compose success message."""
        step_count = len(execution.step_results)
        if step_count == 1:
            return "He completado la tarea."
        return f"He completado las {step_count} operaciones solicitadas."

    def _compose_failure(self, execution: PlanExecutionResult) -> str:
        """Compose failure message."""
        failed_step = None
        for sr in execution.step_results:
            if sr.status.value == "failed":
                failed_step = sr.step_id
                break

        if failed_step:
            return f"Tuve problemas en el paso '{failed_step}'. {execution.reason_code or 'El proceso no pudo completarse.'}"
        return "El proceso no pudo completarse. ¿Puedes proporcionar más contexto sobre lo que necesitas?"

    def _compose_progress(self, execution: PlanExecutionResult) -> str:
        """Compose progress/partial message."""
        completed = sum(
            1 for sr in execution.step_results if sr.status.value == "completed"
        )
        total = len(execution.step_results)
        return f"Llevo {completed} de {total} pasos completados."

    def _summarize_evidence(self, evidence_paths: List[str]) -> str:
        """Summarize evidence paths for user."""
        if not evidence_paths:
            return None
        if len(evidence_paths) == 1:
            path = Path(evidence_paths[0])
            return f"Detalles guardados en: {path.name}"
        return f"{len(evidence_paths)} archivos de evidencia generados."

    def _determine_next_steps(
        self,
        evaluation: Optional[EvaluationResult],
        execution: PlanExecutionResult,
    ) -> List[str]:
        """Determine recommended next steps."""
        next_steps = []

        if evaluation and evaluation.missing_evidence:
            next_steps.append("Recopilar más información")

        if execution.status == "failed":
            next_steps.append("Revisar el error y reintentar")
            next_steps.append("Pedir más contexto al usuario")

        if evaluation and evaluation.recommendation == "ask_user":
            next_steps.append("Confirmar con el usuario antes de continuar")

        return next_steps

    def _build_meta(
        self,
        intent_result: Any,
        execution_result: Optional[PlanExecutionResult],
        evaluation: Optional[EvaluationResult],
        internet_status: str,
    ) -> Dict[str, Any]:
        """Build meta signals for response."""

        meta = {
            "engine_id": execution_result.plan_id
            if execution_result
            else "intent_only",
            "llm_used": "inference_router",
            "internet_status": internet_status,
            "attempts": execution_result.iterations if execution_result else 1,
        }

        if execution_result:
            meta["degraded"] = execution_result.status == "degraded"
            meta["latency_ms"] = execution_result.total_duration_ms
            meta["evidence_count"] = len(execution_result.evidence_artifacts)

        if hasattr(intent_result, "confidence_band"):
            meta["confidence_band"] = intent_result.confidence_band

        if evaluation:
            meta["evaluation_score"] = evaluation.score

        return meta


def save_composer_snapshot(
    composer_input: Dict[str, Any],
    composer_output: PersonaResponse,
    reports_dir: Path,
    request_id: str,
) -> Path:
    """Save composer snapshot to _reports."""
    ts = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace(":", "")
        .replace("-", "")
        .replace("T", "_")
    )
    filename = f"{ts}_{request_id}_composer_snapshot.json"
    path = reports_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "input": composer_input,
        "output": {
            "response_text": composer_output.response_text,
            "meta": composer_output.meta,
            "evidence_summary": composer_output.evidence_summary,
            "next_steps": composer_output.next_steps,
        },
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return path
