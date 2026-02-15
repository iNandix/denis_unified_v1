"""Meta-Intent LLM Layer for DENIS.

Uses local LLM to detect:
- Tone and emotion (irony, frustration, urgency)
- Implicit requests
- Secondary intents
- User's true goal vs literal request

Always returns structured MetaIntentV1 output.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from denis_unified_v1.intent.intent_v1 import (
    MetaIntentV1,
    IntentType,
    IntentEntity,
    ToneType,
    ConfidenceSource,
    SourceInfo,
)
from denis_unified_v1.intent.entity_extractors import extract_entities


# System prompt for structured meta-intent detection
META_INTENT_SYSTEM_PROMPT = """You are a meta-intent detection system. Analyze the user's message and extract:

1. PRIMARY_INTENT: The main intent (one of: debug_repo, run_tests_ci, refactor_migration, implement_feature, ops_health_check, incident_triage, design_architecture, explain_concept, plan_rollout, toolchain_task, write_docs, unknown)

2. SECONDARY_INTENTS: Other intents detected (list, can be empty)

3. USER_GOAL: What the user REALLY wants in 1 sentence (read between the lines)

4. TONE: Detect emotion (neutral, urgent, frustrated, ironic, confused, assertive, polite, angry)

5. IMPLICIT_REQUEST: true if request is indirect (e.g., "great, another error 🙃"), false if direct

6. CONFIDENCE: 0.0-1.0 how confident you are

7. WHY: Brief explanation (max 160 chars) for logs

8. SUGGESTED_CLARIFICATION: If confidence < 0.8, suggest 1 clarifying question

Respond ONLY with valid JSON matching this exact schema:
{
  "primary_intent": "string",
  "secondary_intents": ["string"],
  "user_goal": "string",
  "tone": "string",
  "implicit_request": boolean,
  "confidence": number,
  "why": "string",
  "suggested_clarification": "string or null"
}

DO NOT include any text outside the JSON."""


@dataclass
class MetaIntentResult:
    """Result from meta-intent LLM parsing."""

    meta_intent: Optional[MetaIntentV1]
    status: str  # "ok", "unavailable", "invalid", "error"
    source_info: SourceInfo
    error_message: Optional[str] = None


class MetaIntentLLM:
    """Meta-intent detection using local LLM."""

    def __init__(self, model: Optional[str] = None, enabled: Optional[bool] = None):
        """Initialize Meta-Intent LLM layer.

        Args:
            model: Model name/endpoint to use
            enabled: Whether LLM layer is enabled (auto-detects if None)
        """
        self.model = model or os.getenv("DENIS_META_INTENT_MODEL", "local")
        self._enabled = enabled
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if LLM meta-intent is available."""
        if self._enabled is not None:
            return self._enabled

        if self._available is None:
            self._available = self._check_availability()
        return self._available

    def _check_availability(self) -> bool:
        """Check if we can call LLM for meta-intent."""
        # Check if we have local models available through inference router
        try:
            from denis_unified_v1.inference.router import InferenceRouter

            router = InferenceRouter()
            # Check if any engine is available
            return len(router.engine_registry) > 0
        except Exception:
            return False

    def should_trigger(
        self, rasa_confidence: float, heuristic_confidence: float, prompt: str
    ) -> bool:
        """Determine if meta-intent LLM should be called.

        Triggers if:
        - Rasa confidence < 0.80
        - Heuristic confidence < 0.80
        - Tone/irony suspected
        """
        if not self.is_available():
            return False

        # Confidence threshold trigger
        if rasa_confidence < 0.80 or heuristic_confidence < 0.80:
            return True

        # Tone/irony indicators
        tone_indicators = [
            r"🙃",
            r"🙄",
            r"😤",
            r"🤦",
            r"😒",  # emojis
            r"genial",
            r"great",
            r"perfect",
            r"wonderful",  # sarcasm
            r"again",
            r"otro vez",
            r"de nuevo",  # repetition
            r"obviously",
            r"clearly",
            r"por supuesto",  # irony
        ]

        prompt_lower = prompt.lower()
        for indicator in tone_indicators:
            if indicator in prompt_lower:
                return True

        return False

    async def parse(self, prompt: str) -> MetaIntentResult:
        """Parse prompt using LLM for meta-intent detection.

        Returns structured MetaIntentV1 or error result.
        """
        if not self.is_available():
            return MetaIntentResult(
                meta_intent=None,
                status="unavailable",
                source_info=SourceInfo(
                    source=ConfidenceSource.META_LLM,
                    status="unavailable",
                    notes="LLM not available",
                ),
            )

        try:
            # Build messages for LLM
            messages = [
                {"role": "system", "content": META_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            # Call inference router
            from denis_unified_v1.inference.router import InferenceRouter

            router = InferenceRouter()

            result = await router.route_chat(
                messages=messages,
                request_id=f"meta_intent_{datetime.now(timezone.utc).isoformat()}",
                params={"temperature": 0.2, "max_tokens": 500},
            )

            response_text = result.get("response", "").strip()

            # Parse JSON response
            try:
                parsed = json.loads(response_text)

                # Extract entities from prompt
                entities = extract_entities(prompt)

                # Map to MetaIntentV1
                meta_intent = MetaIntentV1(
                    primary_intent=IntentType(parsed.get("primary_intent", "unknown")),
                    secondary_intents=[
                        IntentType(i) for i in parsed.get("secondary_intents", [])
                    ],
                    user_goal=parsed.get("user_goal", ""),
                    tone=ToneType(parsed.get("tone", "neutral")),
                    implicit_request=parsed.get("implicit_request", False),
                    confidence=parsed.get("confidence", 0.0),
                    why=parsed.get("why", ""),
                    entities=entities,
                    suggested_clarification=parsed.get("suggested_clarification"),
                )

                return MetaIntentResult(
                    meta_intent=meta_intent,
                    status="ok",
                    source_info=SourceInfo(
                        source=ConfidenceSource.META_LLM,
                        confidence=meta_intent.confidence,
                        status="ok",
                        latency_ms=result.get("latency_ms"),
                        notes=f"Tone: {meta_intent.tone.value}, Implicit: {meta_intent.implicit_request}",
                    ),
                )

            except json.JSONDecodeError as e:
                return MetaIntentResult(
                    meta_intent=None,
                    status="invalid",
                    source_info=SourceInfo(
                        source=ConfidenceSource.META_LLM,
                        status="error",
                        notes="Invalid JSON from LLM",
                    ),
                    error_message=f"JSON parse error: {e}",
                )
            except Exception as e:
                return MetaIntentResult(
                    meta_intent=None,
                    status="error",
                    source_info=SourceInfo(
                        source=ConfidenceSource.META_LLM,
                        status="error",
                        notes="Failed to parse LLM response",
                    ),
                    error_message=str(e),
                )

        except Exception as e:
            return MetaIntentResult(
                meta_intent=None,
                status="error",
                source_info=SourceInfo(
                    source=ConfidenceSource.META_LLM,
                    status="error",
                    notes="LLM call failed",
                ),
                error_message=str(e),
            )

    def parse_sync(self, prompt: str) -> MetaIntentResult:
        """Synchronous wrapper for parse()."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.parse(prompt))


# Singleton
_meta_llm: Optional[MetaIntentLLM] = None


def get_meta_intent_llm() -> MetaIntentLLM:
    """Get singleton meta-intent LLM."""
    global _meta_llm
    if _meta_llm is None:
        _meta_llm = MetaIntentLLM()
    return _meta_llm


def detect_meta_intent(
    prompt: str, rasa_confidence: float = 0.0, heuristic_confidence: float = 0.0
) -> MetaIntentResult:
    """Detect meta-intent if needed."""
    meta = get_meta_intent_llm()

    if not meta.should_trigger(rasa_confidence, heuristic_confidence, prompt):
        return MetaIntentResult(
            meta_intent=None,
            status="skipped",
            source_info=SourceInfo(
                source=ConfidenceSource.META_LLM,
                status="skipped",
                notes="Not triggered (confidence high enough)",
            ),
        )

    return meta.parse_sync(prompt)
