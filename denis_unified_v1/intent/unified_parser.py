"""Unified Intent Parser - Main Entry Point.

Orchestrates:
1. S0: Heuristics + Entity Extraction
2. S1: Rasa NLU (if available)
3. S2: Meta-Intent LLM (if triggered)
4. S3: Fusion + Gating
"""

from __future__ import annotations

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from denis_unified_v1.intent.intent_v1 import IntentV1, IntentType
from denis_unified_v1.intent.entity_extractors import (
    extract_entities,
    get_entity_extractor,
)
from denis_unified_v1.intent.rasa_adapter import parse_with_rasa, RasaParseResult
from denis_unified_v1.intent.meta_intent_llm import detect_meta_intent, MetaIntentResult
from denis_unified_v1.intent.intent_fusion import fuse_intents
from denis_unified_v1.intent.intent_v1 import SourceInfo, ConfidenceSource, ReasonCode


class UnifiedIntentParser:
    """Main unified intent parser combining all sources."""

    def __init__(
        self,
        use_rasa: bool = True,
        use_meta_llm: bool = True,
        use_heuristics: bool = True,
    ):
        """Initialize parser.

        Args:
            use_rasa: Whether to use Rasa NLU
            use_meta_llm: Whether to use Meta-Intent LLM
            use_heuristics: Whether to use heuristics
        """
        self.use_rasa = use_rasa
        self.use_meta_llm = use_meta_llm
        self.use_heuristics = use_heuristics

        self._entity_extractor = get_entity_extractor()

    def parse(self, prompt: str) -> IntentV1:
        """Parse prompt using full pipeline.

        Pipeline:
        1. Extract entities (heuristics)
        2. Parse with Rasa (if enabled)
        3. Apply heuristic intent detection
        4. Detect meta-intent (if triggered)
        5. Fuse all sources
        6. Apply confidence gating

        Returns:
            IntentV1 with all metadata
        """
        # S0: Extract entities (always)
        entities = extract_entities(prompt)

        # S1: Rasa parse (if enabled)
        rasa_result = None
        if self.use_rasa:
            try:
                rasa_parse = parse_with_rasa(prompt)
                rasa_result = rasa_parse.to_dict()
            except Exception as e:
                rasa_result = {
                    "intent": None,
                    "confidence": 0.0,
                    "entities": {},
                    "status": "error",
                    "error_message": str(e),
                }

        # S0 continued: Heuristic intent detection
        heuristic_result = None
        if self.use_heuristics:
            heuristic_result = self._apply_heuristics(prompt)

        # S2: Meta-intent detection (if triggered)
        meta_result = None
        if self.use_meta_llm:
            rasa_conf = rasa_result.get("confidence", 0.0) if rasa_result else 0.0
            heur_conf = (
                heuristic_result.get("confidence", 0.0) if heuristic_result else 0.0
            )

            try:
                meta_detect = detect_meta_intent(prompt, rasa_conf, heur_conf)
                meta_result = (
                    {
                        "meta_intent": meta_detect.meta_intent,
                        "status": meta_detect.status,
                        "error_message": meta_detect.error_message,
                    }
                    if meta_detect.meta_intent or meta_detect.status != "skipped"
                    else None
                )
            except Exception as e:
                meta_result = {"status": "error", "error_message": str(e)}

        # S3: Fusion
        intent_v1 = fuse_intents(prompt, rasa_result, heuristic_result, meta_result)

        # Ensure entities are included
        if entities and not intent_v1.entities:
            intent_v1.entities = entities
        elif entities:
            # Merge without duplication
            existing = {(e.type, e.value.lower()) for e in intent_v1.entities}
            for ent in entities:
                if (ent.type, ent.value.lower()) not in existing:
                    intent_v1.entities.append(ent)

        return intent_v1

    def _apply_heuristics(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Apply heuristic intent detection.

        Uses the same patterns as the original intent_parser.
        """
        from denis_unified_v1.intent.intent_parser import HEURISTIC_PATTERNS
        import re

        prompt_lower = prompt.lower()
        scores: Dict[IntentType, float] = {}

        for intent_type, patterns in HEURISTIC_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, prompt_lower, re.IGNORECASE):
                    matches += 1

            if matches > 0:
                # Confidence: 1 match = 0.75, 2 = 0.90, 3+ = 0.95
                if matches == 1:
                    confidence = 0.75
                elif matches == 2:
                    confidence = 0.90
                else:
                    confidence = 0.95
                scores[intent_type] = confidence

        if not scores:
            return None

        # Get best
        best_intent = max(scores.items(), key=lambda x: x[1])
        intent_type, confidence = best_intent

        return {
            "intent": intent_type.value,
            "confidence": confidence,
            "reasoning": f"Matched heuristic patterns for {intent_type.value}",
        }

    def parse_with_clarification(self, prompt: str) -> Dict[str, Any]:
        """Parse and determine if clarification is needed.

        Returns:
            Dict with:
            - action: "proceed" | "ask_clarification" | "offer_options" | "read_only"
            - intent: IntentV1
            - message: str (clarification question or options)
        """
        intent = self.parse(prompt)

        # High confidence + low risk = proceed
        if intent.is_tool_safe:
            return {
                "action": "proceed",
                "intent": intent.to_dict(),
                "message": None,
            }

        # Medium confidence = read-only mode
        if intent.can_read_only and intent.confidence >= 0.50:
            return {
                "action": "read_only",
                "intent": intent.to_dict(),
                "message": self._generate_read_only_message(intent),
                "safe_next_step": intent.safe_next_step,
            }

        # Low confidence = clarification needed
        if intent.needs_clarification and intent.needs_clarification:
            return {
                "action": "ask_clarification",
                "intent": intent.to_dict(),
                "message": intent.needs_clarification[0],
            }

        # Unknown or very low confidence = offer options
        if intent.two_plans_required:
            return {
                "action": "offer_options",
                "intent": intent.to_dict(),
                "message": self._generate_options_message(intent),
                "plans": self._generate_alternative_plans(intent),
            }

        # Fallback: ask for clarification
        return {
            "action": "ask_clarification",
            "intent": intent.to_dict(),
            "message": "No estoy seguro de qué necesitas. ¿Puedes ser más específico?",
        }

    def _generate_read_only_message(self, intent: IntentV1) -> str:
        """Generate message for read-only mode."""
        if intent.safe_next_step:
            step = intent.safe_next_step
            if step.get("type") == "read_only":
                return f"Voy a hacer una verificación primero: {step.get('description', '')}"
        return "Voy a recopilar información antes de actuar."

    def _generate_options_message(self, intent: IntentV1) -> str:
        """Generate options message."""
        if intent.intent == IntentType.UNKNOWN:
            return "No estoy seguro de qué necesitas. Aquí van algunas opciones:\n1. Debuggear un error\n2. Ejecutar tests\n3. Refactorizar código\n4. Verificar estado del sistema"

        return f"Detecté que podrías querer '{intent.intent.value}', pero no estoy 100% seguro. ¿Puedes confirmar o elegir una opción?"

    def _generate_alternative_plans(self, intent: IntentV1) -> list:
        """Generate alternative plans for low confidence."""
        plans = []

        if (
            intent.intent == IntentType.DEBUG_REPO
            or IntentType.RUN_TESTS_CI in intent.secondary_intents
        ):
            plans.append(
                {
                    "id": "A",
                    "summary": "Diagnosticar error y proponer fix",
                    "intent": "debug_repo",
                }
            )

        if (
            intent.intent == IntentType.RUN_TESTS_CI
            or IntentType.DEBUG_REPO in intent.secondary_intents
        ):
            plans.append(
                {
                    "id": "B",
                    "summary": "Ejecutar tests y verificar CI",
                    "intent": "run_tests_ci",
                }
            )

        if intent.intent == IntentType.EXPLAIN_CONCEPT:
            plans.append(
                {
                    "id": "C",
                    "summary": "Explicar concepto o documentar",
                    "intent": "explain_concept",
                }
            )

        # Ensure at least 2 plans
        if len(plans) < 2:
            plans.append(
                {
                    "id": "Z",
                    "summary": "Otra opción: describe qué necesitas exactamente",
                    "intent": "custom",
                }
            )

        return plans


# Global parser
_parser: Optional[UnifiedIntentParser] = None


def get_unified_intent_parser() -> UnifiedIntentParser:
    """Get singleton unified parser."""
    global _parser
    if _parser is None:
        _parser = UnifiedIntentParser()
    return _parser


def parse_intent(prompt: str) -> IntentV1:
    """Convenience function to parse a prompt."""
    return get_unified_intent_parser().parse(prompt)


def parse_intent_with_clarification(prompt: str) -> Dict[str, Any]:
    """Convenience function to parse with clarification check."""
    return get_unified_intent_parser().parse_with_clarification(prompt)
