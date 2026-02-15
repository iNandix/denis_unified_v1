"""Outcome Recording - P1.3: Telemetry for CatBoost.

Records execution outcomes for ML training:
- Success/fail per step
- Evidence paths
- Confidence bands
- Execution time
- Mode selection (clarify/actions_plan/direct_local/direct_boosted)
- Reason codes for degradation analysis
- All stored in _reports for CatBoost
"""

from __future__ import annotations

import json
import os
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


class ExecutionMode(str, Enum):
    """P1.3: Execution modes (deterministic selection)."""

    CLARIFY = "clarify"  # Low confidence - ask 1 question or 2 plans
    ACTIONS_PLAN = "actions_plan"  # Core-code intents (tests, debug, refactor, etc.)
    DIRECT_LOCAL = "direct_local"  # Chat general offline or boosters off
    DIRECT_BOOSTED = "direct_boosted"  # Only if allow_boosters=true AND internet OK
    DIRECT_DEGRADED_LOCAL = (
        "direct_degraded_local"  # Chat intent but no booster available
    )


# P1.3 Stable Reason Codes for CatBoost
class ReasonCode(str, Enum):
    """Fixed set of reason codes for ML training."""

    # Success
    SUCCESS = "success"

    # Degradation reasons
    OFFLINE_MODE = "offline_mode"
    BOOSTERS_DISABLED = "boosters_disabled"
    BOOSTERS_UNAVAILABLE = "boosters_unavailable"
    LOW_CONFIDENCE = "low_confidence"
    LOCAL_RESPONSE_USED = "local_response_template_used"

    # Failure reasons
    STEP_FAILED = "step_failed"
    PLAN_ABORTED = "plan_aborted"
    INTENT_CONFLICT = "intent_conflict"
    NO_EVIDENCE = "no_evidence"
    TIMEOUT = "timeout"

    # Clarification
    CLARIFY_LOW_CONFIDENCE = "clarify_low_confidence"
    CLARIFY_MISSING_CONTEXT = "clarify_missing_context"

    # Reentry
    REENTRY_ITERATION = "reentry_iteration"
    REENTRY_NEW_EVIDENCE = "reentry_new_evidence"

    # Catalog / capability decisions (P1.3 spec)
    CONFIDENCE_MEDIUM_READONLY = "confidence_medium_readonly"
    CAPABILITY_EXISTS = "capability_exists"
    CAPABILITY_PARTIAL_COMPOSE = "capability_partial_compose"
    CAPABILITY_MISSING = "capability_missing"
    TOOL_COMPOSED = "tool_composed"
    CAPABILITY_CREATED = "capability_created"
    STOP_IF_TRIGGERED = "stop_if_triggered"


class InternetStatus(str, Enum):
    OK = "OK"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band.value
            if hasattr(self.confidence_band, "value")
            else str(self.confidence_band),
            "sources_used": self.sources_used,
            "reason_codes": self.reason_codes,
        }


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
    """Full execution outcome for ML training (P1.3 format)."""

    request_id: str
    ts_utc: str

    # Intent
    intent: IntentOutcome

    # Mode selection (P1.3)
    selected_mode: ExecutionMode = ExecutionMode.DIRECT_LOCAL
    allow_boosters: bool = False
    internet_status: InternetStatus = InternetStatus.UNKNOWN

    # Planning
    plan: Optional[PlanOutcome] = None

    # Execution
    status: OutcomeStatus = OutcomeStatus.PENDING
    steps: List[StepOutcome] = field(default_factory=list)
    total_duration_ms: int = 0

    # Evidence
    evidence_artifacts: List[str] = field(default_factory=list)

    # Context
    engine_used: Optional[str] = None

    # Degradation (P1.3)
    degraded: bool = False
    reason_codes: List[str] = field(default_factory=list)
    reentry_count: int = 0

    # Catalog features (P1.3 spec)
    catalog_size: int = 0
    num_matches: int = 0
    top_score: float = 0.0
    booster_health: bool = False
    steps_planned: int = 0
    blocked_steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "ts_utc": self.ts_utc,
            "intent": self.intent.to_dict(),
            # P1.3 fields
            "selected_mode": self.selected_mode.value
            if hasattr(self.selected_mode, "value")
            else str(self.selected_mode),
            "allow_boosters": self.allow_boosters,
            "internet_status": self.internet_status.value
            if hasattr(self.internet_status, "value")
            else str(self.internet_status),
            # Execution
            "plan": self.plan.to_dict() if self.plan else None,
            "status": self.status.value
            if hasattr(self.status, "value")
            else str(self.status),
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "evidence_artifacts": self.evidence_artifacts,
            "engine_used": self.engine_used,
            # Degradation
            "degraded": self.degraded,
            "reason_codes": self.reason_codes,
            "reentry_count": self.reentry_count,
            # Catalog features (P1.3 spec)
            "catalog_size": self.catalog_size,
            "num_matches": self.num_matches,
            "top_score": self.top_score,
            "booster_health": self.booster_health,
            "steps_planned": self.steps_planned,
            "blocked_steps": self.blocked_steps,
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


def get_internet_status() -> InternetStatus:
    """Get current internet status from environment."""
    status = os.getenv("DENIS_INTERNET_STATUS", "UNKNOWN")
    if status not in ["OK", "DOWN", "UNKNOWN"]:
        status = "UNKNOWN"
    return InternetStatus(status)


def get_allow_boosters() -> bool:
    """Determine if boosters are allowed based on policy."""
    allow = os.getenv("DENIS_ALLOW_BOOSTERS", "0") == "1"
    internet = get_internet_status()

    # If internet is DOWN or UNKNOWN (treated as DOWN), no boosters
    if internet != InternetStatus.OK:
        return False

    return allow


def select_mode(
    confidence_band: ConfidenceBand,
    intent: str,
    internet_status: InternetStatus,
    allow_boosters: bool,
) -> tuple[ExecutionMode, List[ReasonCode]]:
    """P1.3: Deterministic mode selection based on policy.

    Rules:
    1. Low confidence -> CLARIFY (ask 1 question or 2 plans)
    2. Core-code intents -> ACTIONS_PLAN
    3. If internet != OK -> DIRECT_LOCAL (never DIRECT_BOOSTED)
    4. If allow_boosters=false -> DIRECT_LOCAL
    5. Otherwise -> DIRECT_BOOSTED

    Returns (mode, reason_codes)
    """
    reason_codes: List[ReasonCode] = []
    degraded = False

    # Rule 1: Low confidence -> clarify
    if confidence_band == ConfidenceBand.LOW:
        return ExecutionMode.CLARIFY, [ReasonCode.CLARIFY_LOW_CONFIDENCE]

    # Core-code intents always use actions_plan
    core_intents = {
        "run_tests_ci",
        "debug_repo",
        "refactor_migration",
        "implement_feature",
        "ops_health_check",
        "plan_rollout",
        "incident_triage",
    }

    if intent in core_intents:
        return ExecutionMode.ACTIONS_PLAN, []

    # Rule 3: If internet not OK -> local (degraded if it was chat intent)
    if internet_status != InternetStatus.OK:
        if intent in {"chat", "general", "unknown"}:
            return ExecutionMode.DIRECT_DEGRADED_LOCAL, [ReasonCode.OFFLINE_MODE]
        return ExecutionMode.DIRECT_LOCAL, [ReasonCode.OFFLINE_MODE]

    # Rule 4: Boosters disabled -> local
    if not allow_boosters:
        if intent in {"chat", "general", "unknown"}:
            return ExecutionMode.DIRECT_DEGRADED_LOCAL, [ReasonCode.BOOSTERS_DISABLED]
        return ExecutionMode.DIRECT_LOCAL, [ReasonCode.BOOSTERS_DISABLED]

    # Rule 5: Normal case - boosted
    return ExecutionMode.DIRECT_BOOSTED, []


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
        internet_status: Optional[InternetStatus] = None,
        selected_mode: Optional[ExecutionMode] = None,
        allow_boosters: Optional[bool] = None,
        degraded: bool = False,
        reason_codes: Optional[List[ReasonCode]] = None,
        catalog_features: Optional[Dict[str, Any]] = None,
    ) -> ExecutionOutcome:
        """Record a complete execution outcome with P1.3 fields."""

        ts = datetime.now(timezone.utc).isoformat()

        # Get intent info
        intent_val = getattr(intent_result, "intent", "unknown")
        # Handle IntentType enum
        if hasattr(intent_val, "value"):
            intent_val = intent_val.value

        intent_outcome = IntentOutcome(
            intent=intent_val,
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

        # Auto-select mode if not provided
        if selected_mode is None:
            confidence = getattr(intent_result, "confidence_band", "low")
            intent_str = getattr(intent_result, "intent", "unknown")
            if hasattr(intent_str, "value"):
                intent_str = intent_str.value

            internet = internet_status or get_internet_status()
            boosters = (
                allow_boosters if allow_boosters is not None else get_allow_boosters()
            )

            selected_mode, auto_reasons = select_mode(
                ConfidenceBand(confidence),
                intent_str,
                internet,
                boosters,
            )
            if auto_reasons:
                reason_codes = reason_codes or []
                reason_codes.extend(auto_reasons)
                degraded = True

        # Get internet status
        if internet_status is None:
            internet_status = get_internet_status()

        if allow_boosters is None:
            allow_boosters = get_allow_boosters()

        # Plan outcome
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

        # Execution status
        status = OutcomeStatus.SUCCESS
        step_outcomes = []
        evidence = []

        if execution_result:
            status_val = getattr(execution_result, "status", "pending")
            if hasattr(status_val, "value"):
                status = OutcomeStatus(status_val.value)
            else:
                status = OutcomeStatus(status_val)

            for sr in getattr(execution_result, "step_results", []):
                step_status = getattr(sr, "status", "pending")
                if hasattr(step_status, "value"):
                    step_status = OutcomeStatus(step_status.value)
                else:
                    step_status = OutcomeStatus(step_status)

                step_outcomes.append(
                    StepOutcome(
                        step_id=getattr(sr, "step_id", "unknown"),
                        status=step_status,
                        duration_ms=getattr(sr, "duration_ms", 0),
                        evidence_paths=getattr(sr, "evidence_paths", []),
                        error=getattr(sr, "error", None),
                        retry_count=getattr(sr, "retry_count", 0),
                    )
                )
                evidence.extend(getattr(sr, "evidence_paths", []))

            evidence.extend(getattr(execution_result, "evidence_artifacts", []))

        # Catalog-derived features (P1.3 spec)
        cat_size = 0
        cat_matches = 0
        cat_top_score = 0.0
        cat_booster_health = False
        if catalog_features:
            cat_size = catalog_features.get("catalog_size", 0)
            cat_matches = catalog_features.get("num_matches", 0)
            cat_top_score = catalog_features.get("top_score", 0.0)
            cat_booster_health = catalog_features.get("booster_health", False)

        # Steps planned vs blocked
        steps_planned = 0
        blocked_steps = 0
        if plan_result:
            steps_planned = len(getattr(plan_result, "steps", []))
        if execution_result:
            blocked_steps = sum(
                1 for sr in getattr(execution_result, "step_results", [])
                if getattr(sr, "status", None) in ("blocked", "skipped")
                or (hasattr(sr, "status") and hasattr(sr.status, "value")
                    and sr.status.value in ("blocked", "skipped"))
            )

        outcome = ExecutionOutcome(
            request_id=request_id,
            ts_utc=ts,
            intent=intent_outcome,
            selected_mode=selected_mode,
            allow_boosters=allow_boosters,
            internet_status=internet_status,
            plan=plan_outcome,
            status=status,
            steps=step_outcomes,
            total_duration_ms=getattr(execution_result, "total_duration_ms", 0)
            if execution_result
            else 0,
            evidence_artifacts=evidence,
            engine_used=getattr(execution_result, "plan_id", None)
            if execution_result
            else None,
            degraded=degraded,
            reason_codes=[
                r.value if hasattr(r, "value") else str(r) for r in (reason_codes or [])
            ],
            reentry_count=getattr(execution_result, "iterations", 1)
            if execution_result
            else 1,
            catalog_size=cat_size,
            num_matches=cat_matches,
            top_score=cat_top_score,
            booster_health=cat_booster_health,
            steps_planned=steps_planned,
            blocked_steps=blocked_steps,
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
    """Create ML-ready features from outcome for CatBoost (P1.3)."""

    # Mode features
    mode = outcome.selected_mode
    is_clarify = mode == ExecutionMode.CLARIFY
    is_actions_plan = mode == ExecutionMode.ACTIONS_PLAN
    is_direct_local = mode == ExecutionMode.DIRECT_LOCAL
    is_direct_boosted = mode == ExecutionMode.DIRECT_BOOSTED
    is_degraded = mode == ExecutionMode.DIRECT_DEGRADED_LOCAL

    features = {
        # Intent features
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
        # Mode selection (P1.3)
        "mode_clarify": int(is_clarify),
        "mode_actions_plan": int(is_actions_plan),
        "mode_direct_local": int(is_direct_local),
        "mode_direct_boosted": int(is_direct_boosted),
        "mode_degraded": int(is_degraded),
        # Plan features
        "plan_type_mutating": int(outcome.plan.plan_type == "mutating")
        if outcome.plan
        else 0,
        "steps_total": len(outcome.steps),
        "steps_success_rate": outcome.success_rate,
        # Catalog features (P1.3 spec)
        "catalog_size": outcome.catalog_size,
        "num_matches": outcome.num_matches,
        "top_score": outcome.top_score,
        "steps_planned": outcome.steps_planned,
        "blocked_steps": outcome.blocked_steps,
        # Execution
        "total_duration_ms": outcome.total_duration_ms,
        "has_evidence": int(len(outcome.evidence_artifacts) > 0),
        # Context (P1.3)
        "internet_ok": int(outcome.internet_status == InternetStatus.OK),
        "allow_boosters": int(outcome.allow_boosters),
        "booster_health": int(outcome.booster_health),
        "degraded": int(outcome.degraded),
        "reentry_count": outcome.reentry_count,
        # Reason codes (P1.3)
        "reason_offline": int(ReasonCode.OFFLINE_MODE.value in outcome.reason_codes),
        "reason_boosters_disabled": int(
            ReasonCode.BOOSTERS_DISABLED.value in outcome.reason_codes
        ),
        "reason_low_confidence": int(
            ReasonCode.LOW_CONFIDENCE.value in outcome.reason_codes
        ),
        # Target
        "is_success": int(outcome.is_success),
    }

    return features
