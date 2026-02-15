"""Outcome Recording - P1.3: Telemetry for CatBoost.

Records execution outcomes for ML training:
- Success/fail per step
- Evidence paths
- Confidence bands
- Execution time
- All stored in _reports for CatBoost
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    PENDING = "pending"


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class StepOutcome:
    """Outcome for a single step."""

    step_id: str
    status: OutcomeStatus
    duration_ms: int
    evidence_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value
            if hasattr(self.status, "value")
            else str(self.status),
            "duration_ms": self.duration_ms,
            "evidence_paths": self.evidence_paths,
            "error": self.error,
            "retry_count": self.retry_count,
        }


@dataclass
class IntentOutcome:
    """Intent detection outcome."""

    intent: str
    confidence: float
    confidence_band: ConfidenceBand
    sources_used: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class PlanOutcome:
    """Action plan outcome."""

    plan_id: str
    plan_type: str  # "read_only", "mutating", "hybrid"
    steps_total: int
    steps_completed: int
    steps_failed: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_type": self.plan_type,
            "steps_total": self.steps_total,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
        }


@dataclass
class ExecutionOutcome:
    """Full execution outcome for ML training."""

    request_id: str
    ts_utc: str

    # Intent
    intent: IntentOutcome

    # Planning
    plan: Optional[PlanOutcome] = None

    # Execution
    status: OutcomeStatus = OutcomeStatus.PENDING
    steps: List[StepOutcome] = field(default_factory=list)
    total_duration_ms: int = 0

    # Evidence
    evidence_artifacts: List[str] = field(default_factory=list)

    # Context
    internet_status: str = "unknown"
    engine_used: Optional[str] = None

    # Meta
    degraded_reason: Optional[str] = None
    reentry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "ts_utc": self.ts_utc,
            "intent": {
                "intent": self.intent.intent.value
                if hasattr(self.intent.intent, "value")
                else str(self.intent.intent),
                "confidence": self.intent.confidence,
                "confidence_band": self.intent.confidence_band.value
                if hasattr(self.intent.confidence_band, "value")
                else str(self.intent.confidence_band),
                "sources_used": self.intent.sources_used,
                "reason_codes": self.intent.reason_codes,
            },
            "plan": self.plan.to_dict() if self.plan else None,
            "status": self.status.value
            if hasattr(self.status, "value")
            else str(self.status),
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "evidence_artifacts": self.evidence_artifacts,
            "internet_status": self.internet_status,
            "engine_used": self.engine_used,
            "degraded_reason": self.degraded_reason,
            "reentry_count": self.reentry_count,
        }

    @property
    def is_success(self) -> bool:
        return self.status == OutcomeStatus.SUCCESS

    @property
    def success_rate(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == OutcomeStatus.SUCCESS)
        return completed / len(self.steps)


class OutcomeRecorder:
    """Records execution outcomes to _reports for CatBoost training."""

    def __init__(self, reports_dir: Optional[Path] = None):
        self.reports_dir = reports_dir or Path(
            "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/denis_unified_v1/_reports"
        )

    def record(
        self,
        request_id: str,
        intent_result: Any,
        plan_result: Any = None,
        execution_result: Any = None,
        internet_status: str = "unknown",
    ) -> ExecutionOutcome:
        """Record a complete execution outcome."""

        ts = datetime.now(timezone.utc).isoformat()

        intent_outcome = IntentOutcome(
            intent=getattr(intent_result, "intent", "unknown"),
            confidence=getattr(intent_result, "confidence", 0.0),
            confidence_band=ConfidenceBand(
                getattr(intent_result, "confidence_band", "low")
            ),
            sources_used=list(getattr(intent_result, "sources", {}).keys()),
            reason_codes=[
                r.value if hasattr(r, "value") else str(r)
                for r in getattr(intent_result, "reason_codes", [])
            ],
        )

        plan_outcome = None
        if plan_result:
            steps = getattr(plan_result, "steps", [])
            plan_outcome = PlanOutcome(
                plan_id=getattr(plan_result, "candidate_id", "unknown"),
                plan_type="mutating"
                if getattr(plan_result, "is_mutating", False)
                else "read_only",
                steps_total=len(steps),
                steps_completed=0,
                steps_failed=0,
            )

        status = OutcomeStatus.SUCCESS
        step_outcomes = []
        evidence = []

        if execution_result:
            status = OutcomeStatus(getattr(execution_result, "status", "pending"))

            for sr in getattr(execution_result, "step_results", []):
                step_outcomes.append(
                    StepOutcome(
                        step_id=getattr(sr, "step_id", "unknown"),
                        status=OutcomeStatus(
                            getattr(sr, "status", "pending").value
                            if hasattr(getattr(sr, "status", None), "value")
                            else "pending"
                        ),
                        duration_ms=getattr(sr, "duration_ms", 0),
                        evidence_paths=getattr(sr, "evidence_paths", []),
                        error=getattr(sr, "error", None),
                        retry_count=getattr(sr, "retry_count", 0),
                    )
                )
                evidence.extend(getattr(sr, "evidence_paths", []))

            evidence.extend(getattr(execution_result, "evidence_artifacts", []))

        outcome = ExecutionOutcome(
            request_id=request_id,
            ts_utc=ts,
            intent=intent_outcome,
            plan=plan_outcome,
            status=status,
            steps=step_outcomes,
            total_duration_ms=getattr(execution_result, "total_duration_ms", 0)
            if execution_result
            else 0,
            evidence_artifacts=evidence,
            internet_status=internet_status,
            engine_used=getattr(execution_result, "plan_id", None)
            if execution_result
            else None,
            degraded_reason=getattr(execution_result, "degraded_reason", None),
            reentry_count=getattr(execution_result, "iterations", 1)
            if execution_result
            else 1,
        )

        self._save_outcome(outcome)
        return outcome

    def _save_outcome(self, outcome: ExecutionOutcome) -> Path:
        """Save outcome to _reports."""
        ts_clean = outcome.ts_utc.replace(":", "").replace("-", "").replace("T", "_")
        filename = f"{ts_clean}_{outcome.request_id}_outcome.json"
        path = self.reports_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(outcome.to_dict(), f, indent=2)

        return path


def create_ml_features(outcome: ExecutionOutcome) -> Dict[str, Any]:
    """Create ML-ready features from outcome for CatBoost."""

    features = {
        "intent_confidence": outcome.intent.confidence,
        "intent_confidence_band_high": int(
            outcome.intent.confidence_band == ConfidenceBand.HIGH
        ),
        "intent_confidence_band_medium": int(
            outcome.intent.confidence_band == ConfidenceBand.MEDIUM
        ),
        "intent_confidence_band_low": int(
            outcome.intent.confidence_band == ConfidenceBand.LOW
        ),
        "plan_type_mutating": int(outcome.plan.plan_type == "mutating")
        if outcome.plan
        else 0,
        "steps_total": len(outcome.steps),
        "steps_success_rate": outcome.success_rate,
        "total_duration_ms": outcome.total_duration_ms,
        "has_evidence": int(len(outcome.evidence_artifacts) > 0),
        "internet_ok": int(outcome.internet_status == "OK"),
        "reentry_count": outcome.reentry_count,
        "is_success": int(outcome.is_success),
    }

    return features
