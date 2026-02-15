"""DENIS Intent Detection Module.

Provides hybrid intent detection using:
- Heuristics (fast, keyword-based)
- Rasa NLU (if available)
- Meta-Intent LLM (for nuance/subtext)
- Fusion engine with confidence gating
"""

from denis_unified_v1.intent.intent_v1 import (
    IntentV1,
    IntentType,
    IntentEntity,
    IntentConstraints,
    ToneType,
    RiskLevel,
    ConfidenceSource,
    ReasonCode,
)
from denis_unified_v1.intent.unified_parser import (
    parse_intent,
    parse_intent_with_clarification,
)

__all__ = [
    "IntentV1",
    "IntentType",
    "IntentEntity",
    "IntentConstraints",
    "ToneType",
    "RiskLevel",
    "ConfidenceSource",
    "ReasonCode",
    "parse_intent",
    "parse_intent_with_clarification",
]
