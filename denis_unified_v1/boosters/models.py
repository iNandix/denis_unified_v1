"""Modo Vampiro - Booster Models and Contracts.

Minimal schemas for ephemeral resource boosters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List
from abc import ABC, abstractmethod


@dataclass
class OpportunitySpec:
    """Especificación cruda de recurso descubierto."""
    id: str  # Unique ID (e.g., "hf_space_123")
    type: str  # "hf_space", "promo_endpoint", "gpu_idle", etc.
    endpoint: str  # URL or access point
    capabilities: List[str]  # ["inference", "embedding", "gpu_accel"]
    health_score: float  # 0.0-1.0 (estimated reliability)
    cost_per_use: float  # USD or tokens
    latency_ms: int  # Estimated latency
    expires_at: datetime  # When it becomes unavailable
    meta: Dict[str, Any]  # Extra data (e.g., model name, API limits)


@dataclass
class BoosterSpec:
    """Especificación normalizada de booster."""
    id: str  # Same as OpportunitySpec.id
    provider: str  # "huggingface", "cloudflare", "custom"
    model: str  # Model name or capability
    adapter_class: str  # "HFAdapter", "GPUAdapter"
    health: Dict[str, float]  # {"reliability": 0.9, "uptime": 0.95}
    cost: Dict[str, Any]  # {"per_token": 0.001, "free_tier": True}
    latency: Dict[str, int]  # {"p50_ms": 200, "p95_ms": 500}
    tags: List[str]  # ["internet_required", "gpu"]
    active: bool  # True if available


class Adapter(ABC):
    """Interfaz para ejecutar con booster."""
    @abstractmethod
    async def execute(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Ejecuta tarea con booster. Retorna resultado o lanza excepción para fallback."""
        pass

    @abstractmethod
    def is_available(self, booster: BoosterSpec) -> bool:
        """Verifica si booster está disponible."""
        pass


@dataclass
class SelectionResult:
    """Resultado de selección de booster."""
    selected_booster: BoosterSpec | None
    fallback_reason: str | None  # "no_booster", "health_low", "cost_high"
    policy_applied: str  # "best_health", "lowest_cost", "fastest"
    candidates_scored: List[Dict[str, Any]]  # [{"booster_id": "hf_123", "score": 0.8}]
    execution_mode: str  # "boosted", "local_fallback"