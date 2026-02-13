"""
SMX Models - Dataclasses para enrichment
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SMXLayerResult:
    """Resultado de un motor SMX individual"""
    layer_name: str
    success: bool
    output: Any
    latency_ms: int
    error: Optional[str] = None


@dataclass
class SMXEnrichment:
    """Enrichment result completo de SMX"""
    text_normalized: str
    intent_refined: str
    entities_extracted: list[dict]
    world_context: dict
    safety_passed: bool
    safety_score: float
    fast_response: Optional[str]
    macro_needed: bool
    confidence_final: float
    smx_latency_ms: int
    layers_used: list[str]
    metrics: dict = field(default_factory=dict)
