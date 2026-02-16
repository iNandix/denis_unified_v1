"""Booster Broker/Policy - Selecciona el mejor booster.

Policy engine para elegir booster óptimo con fallback.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any

from denis_unified_v1.boosters.models import BoosterSpec, SelectionResult
from denis_unified_v1.boosters.booster_catalog import get_booster_catalog
from denis_unified_v1.kernel.internet_health import get_internet_health

logger = logging.getLogger(__name__)


class BoosterBroker:
    """Broker que selecciona booster basado en policy."""

    def __init__(self):
        self.catalog = get_booster_catalog()
        self.internet = get_internet_health()

    def select_booster(
        self,
        task_type: str,
        capabilities: List[str],
        max_cost: float = 0.01,
        prefer_speed: bool = False,
        allow_boosters: bool = True
    ) -> SelectionResult:
        """Selecciona mejor booster para tarea."""
        if not allow_boosters:
            return SelectionResult(
                selected_booster=None,
                fallback_reason="boosters_disabled",
                policy_applied="none",
                candidates_scored=[],
                execution_mode="local_fallback"
            )

        candidates = self.catalog.get_active_boosters(capabilities)
        if not candidates:
            return SelectionResult(
                selected_booster=None,
                fallback_reason="no_booster",
                policy_applied="none",
                candidates_scored=[],
                execution_mode="local_fallback"
            )

        # Filter by cost
        candidates = [b for b in candidates if b.cost.get("per_use", 0) <= max_cost]

        if not candidates:
            return SelectionResult(
                selected_booster=None,
                fallback_reason="cost_too_high",
                policy_applied="cost_filter",
                candidates_scored=[],
                execution_mode="local_fallback"
            )

        # Filter by internet if needed
        internet_ok = self.internet.is_internet_ok()
        candidates = [b for b in candidates if not "internet_required" in b.tags or internet_ok]

        if not candidates:
            return SelectionResult(
                selected_booster=None,
                fallback_reason="internet_down",
                policy_applied="internet_filter",
                candidates_scored=[],
                execution_mode="local_fallback"
            )

        # Score candidates
        scored = []
        for booster in candidates:
            score = self._score_booster(booster, task_type, prefer_speed)
            scored.append({"booster": booster, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Select policy
        policy = "best_health"
        if prefer_speed:
            policy = "fastest"
        elif max_cost < 0.005:
            policy = "lowest_cost"

        best = scored[0]["booster"] if scored else None

        return SelectionResult(
            selected_booster=best,
            fallback_reason=None,
            policy_applied=policy,
            candidates_scored=[{"booster_id": s["booster"].id, "score": s["score"]} for s in scored],
            execution_mode="boosted"
        )

    def _score_booster(self, booster: BoosterSpec, task_type: str, prefer_speed: bool) -> float:
        """Score booster basado en task y preferences."""
        base_score = 0.0

        # Health weight (50%)
        reliability = booster.health.get("reliability", 0.5)
        base_score += reliability * 0.5

        # Cost weight (30%)
        cost_per_use = booster.cost.get("per_use", 0.01)
        cost_score = max(0, 1.0 - (cost_per_use / 0.01))  # Lower cost = higher score
        base_score += cost_score * 0.3

        # Latency weight (20%) - only if prefer_speed
        if prefer_speed:
            latency_ms = booster.latency.get("p50_ms", 1000)
            latency_score = max(0, 1.0 - (latency_ms / 2000))  # Lower latency = higher score
            base_score += latency_score * 0.2
        else:
            base_score += 0.2  # Neutral if not preferring speed

        # Task affinity bonus
        if task_type == "inference" and "inference" in booster.tags:
            base_score += 0.1
        elif task_type == "gpu" and "gpu" in booster.tags:
            base_score += 0.1

        return min(1.0, base_score)


# Global instance
_booster_broker = None

def get_booster_broker() -> BoosterBroker:
    global _booster_broker
    if _booster_broker is None:
        _booster_broker = BoosterBroker()
    return _booster_broker