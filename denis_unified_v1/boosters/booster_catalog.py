"""Booster Catalog - Registry dinámico de boosters.

Normaliza y mantiene catálogo de boosters disponibles.
"""

from __future__ import annotations

import logging
from typing import Dict, List
from datetime import datetime

from denis_unified_v1.boosters.models import OpportunitySpec, BoosterSpec

logger = logging.getLogger(__name__)


class BoosterCatalog:
    """Catálogo dinámico de boosters."""

    def __init__(self):
        self.boosters: Dict[str, BoosterSpec] = {}
        self._load_predefined_boosters()

    def add_opportunity(self, opportunity: OpportunitySpec) -> None:
        """Añade oportunidad y normaliza a booster."""
        if opportunity.id in self.boosters:
            logger.info(f"Updating existing booster {opportunity.id}")
        else:
            logger.info(f"Adding new booster {opportunity.id}")

        booster = self._normalize_opportunity(opportunity)
        self.boosters[opportunity.id] = booster

    def remove_booster(self, booster_id: str) -> None:
        """Remueve booster expirado o caído."""
        if booster_id in self.boosters:
            del self.boosters[booster_id]
            logger.info(f"Removed booster {booster_id}")

    def get_active_boosters(self, capabilities: List[str] = None) -> List[BoosterSpec]:
        """Retorna boosters activos, opcionalmente filtrados por capabilities."""
        active = [b for b in self.boosters.values() if b.active]

        if capabilities:
            active = [b for b in active if any(cap in b.tags for cap in capabilities)]

        return active

    def get_booster(self, booster_id: str) -> BoosterSpec | None:
        """Obtiene booster por ID."""
        return self.boosters.get(booster_id)

    def update_health(self, booster_id: str, health_updates: Dict[str, float]) -> None:
        """Actualiza health de booster basado en outcome."""
        if booster_id in self.boosters:
            booster = self.boosters[booster_id]
            booster.health.update(health_updates)
            # Deactivate if health too low
            if booster.health.get("reliability", 1.0) < 0.5:
                booster.active = False
                logger.warning(f"Deactivated booster {booster_id} due to low health")

    def _normalize_opportunity(self, opportunity: OpportunitySpec) -> BoosterSpec:
        """Normaliza OpportunitySpec a BoosterSpec."""
        provider = self._infer_provider(opportunity.type)
        model = opportunity.meta.get("model", "unknown")
        adapter_class = self._infer_adapter_class(opportunity.type)

        health = {
            "reliability": opportunity.health_score,
            "uptime": 0.9  # Estimated
        }

        cost = {
            "per_use": opportunity.cost_per_use,
            "free_tier": opportunity.cost_per_use == 0.0
        }

        latency = {
            "p50_ms": opportunity.latency_ms,
            "p95_ms": int(opportunity.latency_ms * 1.5)
        }

        tags = []
        if "internet" in opportunity.type.lower():
            tags.append("internet_required")
        if "gpu" in opportunity.capabilities:
            tags.append("gpu")
        tags.extend(opportunity.capabilities)

        active = True
        if opportunity.expires_at and opportunity.expires_at < datetime.now():
            active = False

        return BoosterSpec(
            id=opportunity.id,
            provider=provider,
            model=model,
            adapter_class=adapter_class,
            health=health,
            cost=cost,
            latency=latency,
            tags=tags,
            active=active
        )

    def _infer_provider(self, opp_type: str) -> str:
        """Infiera provider de tipo de oportunidad."""
        if "hf" in opp_type:
            return "huggingface"
        elif "gpu" in opp_type:
            return "cloud_gpu"
        elif "promo" in opp_type:
            return "promo"
        else:
            return "custom"

    def _infer_adapter_class(self, opp_type: str) -> str:
        """Infiera adapter class."""
        if "hf" in opp_type:
            return "HFAdapter"
        elif "gpu" in opp_type:
            return "GPUAdapter"
        else:
            return "GenericAdapter"

    def _load_predefined_boosters(self) -> None:
        """Carga boosters predefinidos para offline."""
        # Local LLM
        self.boosters["local_llm"] = BoosterSpec(
            id="local_llm",
            provider="local",
            model="llama-3.1-8b",
            adapter_class="LocalAdapter",
            health={"reliability": 0.95, "uptime": 1.0},
            cost={"per_use": 0.0, "free_tier": True},
            latency={"p50_ms": 100, "p95_ms": 200},
            tags=["local", "offline"],
            active=True
        )


# Global instance
_booster_catalog = None

def get_booster_catalog() -> BoosterCatalog:
    global _booster_catalog
    if _booster_catalog is None:
        _booster_catalog = BoosterCatalog()
    return _booster_catalog