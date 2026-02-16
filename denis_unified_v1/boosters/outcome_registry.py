"""Outcome Registry - Feedback loop para boosters.

Registra resultados de ejecución para actualizar health y tunear policy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from denis_unified_v1.boosters.models import SelectionResult
from denis_unified_v1.boosters.booster_catalog import get_booster_catalog

logger = logging.getLogger(__name__)


class OutcomeRegistry:
    """Registry para outcomes de booster execution."""

    def __init__(self, reports_dir: Path = Path("reports")):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(exist_ok=True)
        self.catalog = get_booster_catalog()

    def record_outcome(
        self,
        selection_result: SelectionResult,
        execution_result: Dict[str, Any],
        task_context: Dict[str, Any]
    ) -> None:
        """Registra outcome de ejecución."""
        outcome = {
            "timestamp": datetime.now().isoformat(),
            "selection": {
                "policy_applied": selection_result.policy_applied,
                "execution_mode": selection_result.execution_mode,
                "selected_booster": selection_result.selected_booster.id if selection_result.selected_booster else None,
                "fallback_reason": selection_result.fallback_reason,
            },
            "execution": execution_result,
            "task_context": task_context,
            "health_updates": self._compute_health_updates(execution_result)
        }

        # Save to file
        outcome_file = self.reports_dir / f"booster_outcome_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(outcome_file, 'w') as f:
            json.dump(outcome, f, indent=2)

        # Update catalog health
        if selection_result.selected_booster:
            booster_id = selection_result.selected_booster.id
            health_updates = outcome["health_updates"]
            self.catalog.update_health(booster_id, health_updates)

        logger.info(f"Recorded outcome for booster {selection_result.selected_booster.id if selection_result.selected_booster else 'none'}")

    def _compute_health_updates(self, execution_result: Dict[str, Any]) -> Dict[str, float]:
        """Computa updates de health basado en resultado."""
        updates = {}

        if "latency_ms" in execution_result:
            latency = execution_result["latency_ms"]
            # Adjust reliability based on latency
            if latency < 500:
                updates["reliability"] = 0.02  # Slight increase
            elif latency > 2000:
                updates["reliability"] = -0.05  # Decrease

        if execution_result.get("success", True):
            updates["reliability"] = (updates.get("reliability", 0) + 0.01)
        else:
            updates["reliability"] = (updates.get("reliability", 0) - 0.1)

        return updates

    def get_recent_outcomes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtiene outcomes recientes para análisis."""
        outcome_files = sorted(self.reports_dir.glob("booster_outcome_*.json"), reverse=True)
        outcomes = []
        for f in outcome_files[:limit]:
            try:
                with open(f) as file:
                    outcomes.append(json.load(file))
            except Exception as e:
                logger.warning(f"Failed to load outcome {f}: {e}")
        return outcomes


# Global instance
_outcome_registry = None

def get_outcome_registry() -> OutcomeRegistry:
    global _outcome_registry
    if _outcome_registry is None:
        _outcome_registry = OutcomeRegistry()
    return _outcome_registry