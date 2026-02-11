"""
Metacognitive Perception - Percepción con autoconciencia.

Añade reflexión sobre cada percepción del cortex:
- PerceptionReflection: metadata sobre cada percepción
- AttentionMechanism: decide qué entidades importan
- GapDetector: detecta entidades faltantes
- ConfidenceScore: calcula confianza en la percepción

Depende de:
- cortex/world_interface.py (existente)
- metacognitive/hooks.py (TICKET F0)

Contratos aplicados:
- L3.META.ONLY_OBSERVE_L0
- L3.META.NEVER_BLOCK
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json

from denis_unified_v1.cortex.entity_registry import EntityRegistry
from denis_unified_v1.metacognitive.hooks import (
    get_hooks,
    emit_reflection,
    metacognitive_trace,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PerceptionReflection:
    """Metadata reflexiva sobre una percepción."""

    perception_id: str
    source: str
    entity_count: int
    entity_types: list[str]
    attention_score: float
    confidence_score: float
    gaps_detected: list[str]
    anomalies_detected: list[str]
    coherence_with_previous: float | None
    timestamp_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttentionTarget:
    """Entidad que merece atención."""

    entity_id: str
    entity_type: str
    attention_score: float
    reason: str
    timestamp_utc: str


@dataclass
class ConfidenceAssessment:
    """Evaluación de confianza en una percepción."""

    overall_score: float
    factors: dict[str, float]
    recommendations: list[str]
    timestamp_utc: str


class AttentionMechanism:
    """Decide qué entidades merecen atención."""

    HIGH_VALUE_TYPES = ["person", "user", "tool", "memory", "conversation"]
    CHANGE_INDICATORS = ["updated_at", "timestamp", "last_seen"]

    def __init__(self):
        self._attention_history: dict[str, list[float]] = {}

    def calculate_attention_score(
        self,
        entity: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> float:
        score = 0.0

        entity_type = entity.get("type", entity.get("entity_type", "unknown"))
        if entity_type in self.HIGH_VALUE_TYPES:
            score += 0.3

        last_updated = entity.get("updated_at") or entity.get("timestamp")
        if last_updated:
            score += 0.2

        importance = entity.get("importance", 0.5)
        score += importance * 0.3

        if context:
            query = context.get("query", "").lower()
            if entity_type in query or entity.get("name", "").lower() in query:
                score += 0.2

        return min(1.0, score)

    def rank_entities(
        self,
        entities: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[AttentionTarget]:
        targets = []
        for entity in entities:
            entity_id = entity.get("id") or entity.get("entity_id")
            if not entity_id:
                continue

            score = self.calculate_attention_score(entity, context)
            if score > 0.3:
                targets.append(
                    AttentionTarget(
                        entity_id=entity_id,
                        entity_type=entity.get("type", "unknown"),
                        attention_score=score,
                        reason=self._get_reason(entity, score),
                        timestamp_utc=_utc_now(),
                    )
                )

        targets.sort(key=lambda t: -t.attention_score)
        return targets

    def _get_reason(self, entity: dict[str, Any], score: float) -> str:
        if score >= 0.7:
            return "high_value_entity"
        elif score >= 0.5:
            return "recently_updated"
        else:
            return "context_relevant"


class GapDetector:
    """Detecta entidades faltantes en el modelo del mundo."""

    EXPECTED_ENTITIES = {
        "user": ["active_users", "known_users"],
        "tool": ["available_tools", "last_used_tools"],
        "memory": ["recent_memories", "important_memories"],
        "conversation": ["active_conversations", "context"],
    }

    def __init__(self):
        self._known_gaps: dict[str, list[str]] = {}

    def detect_gaps(
        self,
        perceived_entities: list[dict[str, Any]],
        expected_types: list[str] | None = None,
    ) -> list[str]:
        gaps = []
        perceived_types = set(
            e.get("type", e.get("entity_type", "unknown")) for e in perceived_entities
        )

        expected = expected_types or list(self.EXPECTED_ENTITIES.keys())

        for exp_type in expected:
            if exp_type not in perceived_types:
                gaps.append(f"missing_{exp_type}")

        for exp_type, subcategories in self.EXPECTED_ENTITIES.items():
            if exp_type in perceived_types:
                for sub in subcategories:
                    if not any(
                        e.get(sub.replace("_", "_")) or e.get(sub)
                        for e in perceived_entities
                    ):
                        gaps.append(f"missing_{sub}")

        return list(set(gaps))


class ConfidenceScorer:
    """Calcula confianza en una percepción."""

    def __init__(self):
        self._history: list[dict[str, Any]] = []

    def assess(
        self,
        entities: list[dict[str, Any]],
        perception_metadata: dict[str, Any] | None = None,
    ) -> ConfidenceAssessment:
        factors = {}

        if not entities:
            factors["entity_count"] = 0.0
            return ConfidenceAssessment(
                overall_score=0.0,
                factors=factors,
                recommendations=["No entities perceived - check perception source"],
                timestamp_utc=_utc_now(),
            )

        factors["entity_count"] = min(1.0, len(entities) / 10)

        entities_with_state = sum(
            1 for e in entities if e.get("state") or e.get("status")
        )
        factors["state_coverage"] = entities_with_state / max(1, len(entities))

        entities_with_timestamps = sum(
            1 for e in entities if e.get("timestamp") or e.get("updated_at")
        )
        factors["temporal_coverage"] = entities_with_timestamps / max(1, len(entities))

        unique_types = len(set(e.get("type", "unknown") for e in entities))
        factors["type_diversity"] = min(1.0, unique_types / 5)

        overall = sum(factors.values()) / len(factors)

        recommendations = []
        if factors["entity_count"] < 0.5:
            recommendations.append("Consider increasing perception interval")
        if factors["state_coverage"] < 0.7:
            recommendations.append("Some entities lack state information")
        if factors["temporal_coverage"] < 0.7:
            recommendations.append("Some entities lack timestamps")

        return ConfidenceAssessment(
            overall_score=overall,
            factors=factors,
            recommendations=recommendations,
            timestamp_utc=_utc_now(),
        )


class MetacognitivePerception:
    """Percepción con metacognición."""

    def __init__(self):
        self._hooks = get_hooks()
        self._attention = AttentionMechanism()
        self._gap_detector = GapDetector()
        self._confidence = ConfidenceScorer()
        self._previous_entities: list[dict[str, Any]] = []

    @metacognitive_trace("metacognitive_perception")
    def perceive_with_reflection(
        self,
        raw_entities: list[dict[str, Any]],
        source: str = "cortex",
        context: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], PerceptionReflection]:
        reflection_id = f"ref_{_utc_now()[:19].replace(':', '')}"

        attention_targets = self._attention.rank_entities(raw_entities, context)

        gaps = self._gap_detector.detect_gaps(raw_entities)

        confidence = self._confidence.assess(raw_entities)

        coherence = self._calculate_coherence(raw_entities)

        anomalies = self._detect_anomalies(raw_entities)

        reflection = PerceptionReflection(
            perception_id=reflection_id,
            source=source,
            entity_count=len(raw_entities),
            entity_types=list(set(e.get("type", "unknown") for e in raw_entities)),
            attention_score=sum(t.attention_score for t in attention_targets)
            / max(1, len(attention_targets)),
            confidence_score=confidence.overall_score,
            gaps_detected=gaps,
            anomalies_detected=anomalies,
            coherence_with_previous=coherence,
            timestamp_utc=_utc_now(),
            metadata={
                "attention_targets": [
                    {"id": t.entity_id, "score": t.attention_score, "reason": t.reason}
                    for t in attention_targets[:5]
                ],
                "confidence_factors": confidence.factors,
                "recommendations": confidence.recommendations,
            },
        )

        self._previous_entities = raw_entities.copy()

        self._emit_perception_events(reflection, attention_targets, gaps, confidence)

        return raw_entities, reflection

    def _calculate_coherence(
        self,
        current_entities: list[dict[str, Any]],
    ) -> float | None:
        if not self._previous_entities:
            return None

        current_ids = set(e.get("id") for e in current_entities if e.get("id"))
        previous_ids = set(e.get("id") for e in self._previous_entities if e.get("id"))

        if not current_ids or not previous_ids:
            return None

        overlap = len(current_ids & previous_ids)
        union = len(current_ids | previous_ids)

        return overlap / union if union > 0 else 0.0

    def _detect_anomalies(
        self,
        entities: list[dict[str, Any]],
    ) -> list[str]:
        anomalies = []

        ids = [e.get("id") for e in entities if e.get("id")]
        if len(ids) != len(set(ids)):
            anomalies.append("duplicate_entity_ids")

        for entity in entities:
            state = entity.get("state")
            if state == "error" or state == "offline":
                if entity.get("type") in ["person", "user"]:
                    anomalies.append(f"entity_offline:{entity.get('id')}")

        return anomalies

    def _emit_perception_events(
        self,
        reflection: PerceptionReflection,
        attention_targets: list[AttentionTarget],
        gaps: list[str],
        confidence: ConfidenceAssessment,
    ) -> None:
        for target in attention_targets[:3]:
            emit_reflection(
                reflection_type="attention",
                target=target.entity_id,
                finding=f"Entity scored {target.attention_score:.2f}",
                confidence=target.attention_score,
                recommendation=f"Monitor {target.entity_type}",
            )

        for gap in gaps[:3]:
            emit_reflection(
                reflection_type="gap_detection",
                target=gap,
                finding=f"Expected but not found",
                confidence=0.8,
                recommendation="Consider adding gap detection to perception",
            )

        if confidence.overall_score < 0.5:
            emit_reflection(
                reflection_type="low_confidence",
                target=reflection.source,
                finding=f"Confidence {confidence.overall_score:.2f}",
                confidence=confidence.overall_score,
                recommendation=confidence.recommendations[0]
                if confidence.recommendations
                else None,
            )

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._hooks.is_enabled(),
            "attention_mechanism": "active",
            "gap_detector": "active",
            "confidence_scorer": "active",
            "previous_entity_count": len(self._previous_entities),
        }


def create_metacognitive_perception() -> MetacognitivePerception:
    return MetacognitivePerception()


if __name__ == "__main__":
    import json

    print("=== METACOGNITIVE PERCEPTION ===")
    mp = create_metacognitive_perception()
    print(json.dumps(mp.get_status(), indent=2))

    print("\n=== PERCEIVE WITH REFLECTION ===")
    entities = [
        {"id": "user:jotah", "type": "user", "state": "active", "importance": 0.9},
        {"id": "tool:search", "type": "tool", "state": "available", "importance": 0.8},
        {
            "id": "memory:recent",
            "type": "memory",
            "state": "stored",
            "updated_at": "2026-02-11T10:00:00Z",
        },
        {"id": "light:led_mesa_1", "type": "light", "state": "on"},
    ]

    result_entities, reflection = mp.perceive_with_reflection(
        entities,
        source="test_cortex",
        context={"query": "jotah tools"},
    )

    print("Entities:", len(result_entities))
    print("Reflection:")
    print(
        json.dumps(
            {
                "perception_id": reflection.perception_id,
                "entity_count": reflection.entity_count,
                "confidence_score": reflection.confidence_score,
                "gaps_detected": reflection.gaps_detected,
                "attention_score": reflection.attention_score,
            },
            indent=2,
            sort_keys=True,
        )
    )

    print("\n=== SECOND PERCEPTION (coherence test) ===")
    entities2 = [
        {"id": "user:jotah", "type": "user", "state": "active", "importance": 0.9},
        {"id": "tool:search", "type": "tool", "state": "available", "importance": 0.8},
        {
            "id": "memory:recent",
            "type": "memory",
            "state": "stored",
            "updated_at": "2026-02-11T10:00:00Z",
        },
        {"id": "light:led_mesa_1", "type": "light", "state": "on"},
        {"id": "new_entity", "type": "conversation", "state": "active"},
    ]

    result_entities2, reflection2 = mp.perceive_with_reflection(
        entities2,
        source="test_cortex_2",
    )

    print("Coherence with previous:", reflection2.coherence_with_previous)
    print("New gaps:", reflection2.gaps_detected)
