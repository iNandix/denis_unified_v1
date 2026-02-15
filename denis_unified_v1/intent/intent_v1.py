"""Intent_v1 - Extended structured intent detection for DENIS.

Enhanced model with:
- Multi-source fusion (Rasa + Heuristics + LLM Meta-Intent)
- Tone detection (irony, urgency, frustration)
- Secondary intents for multi-objective tasks
- Risk assessment
- Confidence gating with reason codes
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timezone


class IntentType(Enum):
    """Core intent taxonomy for DENIS."""

    DEBUG_REPO = "debug_repo"
    RUN_TESTS_CI = "run_tests_ci"
    REFACTOR_MIGRATION = "refactor_migration"
    IMPLEMENT_FEATURE = "implement_feature"
    OPS_HEALTH_CHECK = "ops_health_check"
    INCIDENT_TRIAGE = "incident_triage"
    DESIGN_ARCHITECTURE = "design_architecture"
    EXPLAIN_CONCEPT = "explain_concept"
    PLAN_ROLLOUT = "plan_rollout"
    TOOLCHAIN_TASK = "toolchain_task"
    WRITE_DOCS = "write_docs"
    UNKNOWN = "unknown"


class ToneType(Enum):
    """User tone/emotion detected in prompt."""

    NEUTRAL = "neutral"
    URGENT = "urgent"
    FRUSTRATED = "frustrated"
    IRONIC = "ironic"
    CONFUSED = "confused"
    ASSERTIVE = "assertive"
    POLITE = "polite"
    ANGRY = "angry"


class RiskLevel(Enum):
    """Risk assessment for the intent."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceSource(Enum):
    """Source of intent classification."""

    HEURISTICS = "heuristics"
    RASA = "rasa"
    META_LLM = "meta_llm"
    MERGED = "merged"


class ReasonCode(Enum):
    """Reason codes for classification decisions."""

    RASA_UNAVAILABLE = "rasa_unavailable"
    RASA_LOW_CONFIDENCE = "rasa_low_confidence"
    META_INTENT_USED = "meta_intent_used"
    HEURISTICS_USED = "heuristics_used"
    HEURISTICS_HIGH_CONFIDENCE = "heuristics_high_confidence"
    LOW_CONFIDENCE_GATE = "low_confidence_gate"
    INTENT_CONFLICT_RESOLVED = "intent_conflict_resolved"
    RASA_WINS_HIGH_CONFIDENCE = "rasa_wins_high_confidence"
    META_WINS_RASA_LOW = "meta_wins_rasa_low"
    HEURISTICS_WINS_ALL_LOW = "heuristics_wins_all_low"
    TONE_INFLUENCE = "tone_influence"
    DEFAULT_FALLBACK = "default_fallback"


@dataclass
class SourceInfo:
    """Information about a classification source."""

    source: ConfidenceSource
    intent: Optional[str] = None
    confidence: float = 0.0
    status: str = "ok"  # ok, unavailable, error
    latency_ms: Optional[float] = None
    model_version: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "latency_ms": self.latency_ms,
            "model_version": self.model_version,
            "notes": self.notes,
        }


@dataclass
class IntentConstraints:
    """Constraints for intent execution."""

    offline_mode: bool = False
    no_boosters: bool = False
    max_latency_ms: Optional[int] = None
    require_evidence: bool = True
    read_only: bool = False  # New: only allow read/list/probe actions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offline_mode": self.offline_mode,
            "no_boosters": self.no_boosters,
            "max_latency_ms": self.max_latency_ms,
            "require_evidence": self.require_evidence,
            "read_only": self.read_only,
        }


@dataclass
class IntentEntity:
    """Extracted entity from the prompt."""

    type: str  # "path", "command", "service", "port", "variable", "url", "flag"
    value: str
    span: Optional[tuple[int, int]] = None  # (start, end) character positions
    confidence: float = 1.0
    source: ConfidenceSource = ConfidenceSource.HEURISTICS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "value": self.value,
            "span": self.span,
            "confidence": round(self.confidence, 3),
            "source": self.source.value,
        }


@dataclass
class IntentV1:
    """Structured intent with confidence gating and multi-source fusion.

    Enhanced fields:
        intent: The classified primary intent type
        confidence: 0-1 confidence score (final merged)
        confidence_band: high/medium/low based on threshold
        entities: Extracted entities (paths, commands, etc.)
        constraints: Execution constraints
        acceptance_criteria: Short list of success criteria
        risk: Risk level assessment
        tone: Detected user tone/emotion
        secondary_intents: Additional intents detected (multi-objective)
        implicit_request: Whether the request was implicit/indirect
        user_goal: High-level user objective description
        needs_clarification: List of specific clarifications needed
        two_plans_required: Whether to offer two alternative plans
        safe_next_step: Optional read-only action to gather more info
        sources: Dict of classification sources with their details
        reason_codes: Why certain decisions were made
        reasoning: Brief explanation of classification
        raw_prompt: Original prompt for debugging
        parsed_at: ISO timestamp
    """

    # Core classification
    intent: IntentType
    confidence: float
    confidence_band: str = "unknown"  # high/medium/low

    # Entities and constraints
    entities: List[IntentEntity] = field(default_factory=list)
    constraints: IntentConstraints = field(default_factory=IntentConstraints)

    # Acceptance and risk
    acceptance_criteria: List[str] = field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW

    # Tone and style
    tone: ToneType = ToneType.NEUTRAL
    secondary_intents: List[IntentType] = field(default_factory=list)
    implicit_request: bool = False
    user_goal: Optional[str] = None

    # Clarification handling
    needs_clarification: List[str] = field(default_factory=list)
    two_plans_required: bool = False
    safe_next_step: Optional[Dict[str, Any]] = None

    # Sources and provenance
    sources: Dict[str, SourceInfo] = field(default_factory=dict)
    reason_codes: List[ReasonCode] = field(default_factory=list)

    # Metadata
    reasoning: str = ""
    raw_prompt: str = ""
    parsed_at: str = ""

    def __post_init__(self):
        """Validate confidence is in valid range and set confidence band."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")

        # Set confidence band
        threshold = float(os.getenv("DENIS_INTENT_THRESHOLD", "0.72"))
        if self.confidence >= 0.85:
            self.confidence_band = "high"
        elif self.confidence >= threshold:
            self.confidence_band = "medium"
        else:
            self.confidence_band = "low"

            # Auto-set clarification flags for low confidence
            if not self.needs_clarification and not self.two_plans_required:
                self.two_plans_required = True

    @property
    def is_confident(self) -> bool:
        """Check if confidence meets threshold for autonomous action."""
        threshold = float(os.getenv("DENIS_INTENT_THRESHOLD", "0.72"))
        return self.confidence >= threshold

    @property
    def requires_clarification(self) -> bool:
        """Check if we should ask for clarification."""
        return not self.is_confident and self.intent != IntentType.UNKNOWN

    @property
    def is_tool_safe(self) -> bool:
        """Check if it's safe to execute tools."""
        return (
            self.is_confident
            and self.intent != IntentType.UNKNOWN
            and self.risk != RiskLevel.HIGH
        )

    @property
    def can_read_only(self) -> bool:
        """Check if read-only actions are allowed (for medium confidence)."""
        if self.risk == RiskLevel.HIGH:
            return self.confidence >= 0.85
        return self.confidence >= 0.50

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON/logging."""
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 3),
            "confidence_band": self.confidence_band,
            "is_confident": self.is_confident,
            "requires_clarification": self.requires_clarification,
            "is_tool_safe": self.is_tool_safe,
            "can_read_only": self.can_read_only,
            "entities": [e.to_dict() for e in self.entities],
            "constraints": self.constraints.to_dict(),
            "acceptance_criteria": self.acceptance_criteria,
            "risk": self.risk.value,
            "tone": self.tone.value,
            "secondary_intents": [i.value for i in self.secondary_intents],
            "implicit_request": self.implicit_request,
            "user_goal": self.user_goal,
            "needs_clarification": self.needs_clarification,
            "two_plans_required": self.two_plans_required,
            "safe_next_step": self.safe_next_step,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "reason_codes": [r.value for r in self.reason_codes],
            "reasoning": self.reasoning,
            "raw_prompt": self.raw_prompt,
            "parsed_at": self.parsed_at,
        }

    @classmethod
    def unknown(
        cls,
        prompt: str = "",
        reasoning: str = "",
        sources: Optional[Dict[str, SourceInfo]] = None,
    ) -> "IntentV1":
        """Create an unknown intent with universal diagnostic plan."""
        parsed_at = datetime.now(timezone.utc).isoformat()
        return cls(
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            confidence_band="low",
            sources=sources or {},
            reason_codes=[ReasonCode.DEFAULT_FALLBACK],
            raw_prompt=prompt,
            reasoning=reasoning or "Could not classify intent with any source",
            parsed_at=parsed_at,
            two_plans_required=True,
            safe_next_step={
                "type": "universal_diagnostic",
                "steps": [
                    "collect_context: error logs, commands, paths mentioned",
                    "identify_goal: fix, explain, implement, or check",
                    "propose_next: specific step based on findings",
                ],
                "safe_actions": [
                    "list files in mentioned paths",
                    "check recent git changes",
                    "run tests in dry-mode",
                    "read relevant documentation",
                ],
            },
        )


@dataclass
class MetaIntentV1:
    """Meta-intent detection from LLM layer (reading between the lines).

    Captures:
    - Subtext and implicit meaning
    - Tone and emotion
    - Secondary/hidden intents
    - User's true goal vs literal request
    """

    primary_intent: IntentType
    secondary_intents: List[IntentType]
    user_goal: str
    tone: ToneType
    implicit_request: bool
    confidence: float
    why: str  # Explanation for logs (max 160 chars)
    entities: List[IntentEntity]
    suggested_clarification: Optional[str] = None

    def __post_init__(self):
        """Validate confidence and truncate why."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")
        self.why = self.why[:160] if self.why else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_intent": self.primary_intent.value,
            "secondary_intents": [i.value for i in self.secondary_intents],
            "user_goal": self.user_goal,
            "tone": self.tone.value,
            "implicit_request": self.implicit_request,
            "confidence": round(self.confidence, 3),
            "why": self.why,
            "entities": [e.to_dict() for e in self.entities],
            "suggested_clarification": self.suggested_clarification,
        }

    @classmethod
    def from_llm_response(cls, response: Dict[str, Any]) -> "MetaIntentV1":
        """Create MetaIntentV1 from structured LLM response."""
        return cls(
            primary_intent=IntentType(response.get("primary_intent", "unknown")),
            secondary_intents=[
                IntentType(i) for i in response.get("secondary_intents", [])
            ],
            user_goal=response.get("user_goal", ""),
            tone=ToneType(response.get("tone", "neutral")),
            implicit_request=response.get("implicit_request", False),
            confidence=response.get("confidence", 0.0),
            why=response.get("why", ""),
            entities=[IntentEntity(**e) for e in response.get("entities", [])],
            suggested_clarification=response.get("suggested_clarification"),
        )


# Confidence thresholds (configurable via env)
CONFIDENCE_THRESHOLD_HIGH = 0.85  # Full tool execution
CONFIDENCE_THRESHOLD_MEDIUM = float(
    os.getenv("DENIS_INTENT_THRESHOLD", "0.72")
)  # Read-only
CONFIDENCE_THRESHOLD_LOW = 0.50  # Question/plans only

# Alias for backward compatibility
CONFIDENCE_THRESHOLD_AUTONOMOUS = CONFIDENCE_THRESHOLD_HIGH

# Disambiguation templates for common intent pairs
DISAMBIGUATION_TEMPLATES: Dict[Tuple, Dict[str, Any]] = {
    (IntentType.DEBUG_REPO, IntentType.RUN_TESTS_CI): {
        "question": "¿El error ocurre en tu máquina local o solo en CI?",
        "clarification_map": {
            "local": IntentType.DEBUG_REPO,
            "ci": IntentType.RUN_TESTS_CI,
        },
    },
    (IntentType.IMPLEMENT_FEATURE, IntentType.REFACTOR_MIGRATION): {
        "question": "¿Quieres añadir comportamiento nuevo o reestructurar sin cambiar output?",
        "clarification_map": {
            "nuevo": IntentType.IMPLEMENT_FEATURE,
            "reestructurar": IntentType.REFACTOR_MIGRATION,
        },
    },
    (IntentType.OPS_HEALTH_CHECK, IntentType.INCIDENT_TRIAGE): {
        "question": "¿Buscas el estado actual o investigar un fallo activo?",
        "clarification_map": {
            "estado": IntentType.OPS_HEALTH_CHECK,
            "fallo": IntentType.INCIDENT_TRIAGE,
        },
    },
}
