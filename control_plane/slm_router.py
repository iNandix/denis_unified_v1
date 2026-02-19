"""SLM Router - Fast local intent classification.

Uses nodo1's small local models (llama-3.2-3b, qwen2.5-3b) for intent classification
before deciding whether to escalate to Groq or use local heuristics.

Goal: 80% of requests handled locally, NO Groq unless necessary.
"""

import os
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Threshold for escalation - below this, clarify with user
CONFIDENCE_THRESHOLD = 0.55


@dataclass
class SLMClassification:
    """Result from SLM intent classification."""

    intent: str
    confidence: float
    missing_inputs: list[str]
    should_clarify: bool
    local_routing: str  # "local", "heuristic", "groq"
    reasoning: str


class SLMRouter:
    """
    SLM-first intent classifier.

    Flow:
    1. nodo1 llama-3.2-3b classifies intent + confidence
    2. If confidence >= 0.55 → route locally/heuristic
    3. If confidence < 0.55 → clarify() prompt, NO Groq yet
    4. Only escalate to Groq if clarification fails

    Target: 80% handled locally
    """

    def __init__(self):
        self._client = None
        self._endpoint = os.getenv("SLM_ENDPOINT", "http://127.0.0.1:9997")

    def _get_client(self):
        """Lazy load local LLM client."""
        if self._client is None:
            try:
                from denis_unified_v1.inference.llamacpp_client import LlamaCppClient

                self._client = LlamaCppClient(endpoint=self._endpoint)
            except Exception as e:
                logger.warning(f"LLM client init failed: {e}")
        return self._client

    async def classify(self, user_prompt: str) -> SLMClassification:
        """
        Classify user intent using local SLM.

        Returns classification with confidence and routing decision.
        """
        system_prompt = """Eres un clasificador de intents. Analiza el mensaje del usuario.

Intents válidos:
- implement_feature: crear algo nuevo, añadir funcionalidad
- debug_repo: arreglar bugs, errores, problemas
- refactor_migration: refactorizar, migrar código
- run_tests_ci: ejecutar tests, CI/CD
- explain_concept: explicar, documentar
- design_architecture: diseño, arquitectura
- toolchain_task: tareas de herramientas
- ops_health_check: проверка здоровья системы
- incident_triage: incidentes, emergencias
- greeting: saludo simple
- unknown: no se puede determinar

Responde SOLO en JSON:
{"intent": "...", "confidence": 0.0-1.0, "missing_inputs": [], "reasoning": "..."}

Si confidence < 0.6, especifica qué falta en missing_inputs."""

        try:
            client = self._get_client()
            if not client:
                return self._fallback_classify(user_prompt)

            response = await client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )

            # Parse JSON response
            import json
            import re

            content = response.get("content", "")
            json_match = re.search(r"\{.*\}", content, re.DOTALL)

            if json_match:
                data = json.loads(json_match.group())
                return self._build_classification(user_prompt, data)
            else:
                logger.warning(f"Invalid SLM response: {content}")
                return self._fallback_classify(user_prompt)

        except Exception as e:
            logger.warning(f"SLM classification failed: {e}")
            return self._fallback_classify(user_prompt)

    def _build_classification(self, prompt: str, data: dict) -> SLMClassification:
        """Build classification from SLM response."""
        intent = data.get("intent", "unknown")
        confidence = float(data.get("confidence", 0.0))
        missing = data.get("missing_inputs", [])

        # Determine routing
        if confidence >= CONFIDENCE_THRESHOLD:
            # High confidence → route locally
            if intent in ["debug_repo", "run_tests_ci", "ops_health_check"]:
                local_routing = "local"
            else:
                local_routing = "heuristic"
        else:
            # Low confidence → clarify (NO Groq yet)
            local_routing = "clarify"

        should_clarify = confidence < CONFIDENCE_THRESHOLD or len(missing) > 0

        return SLMClassification(
            intent=intent,
            confidence=confidence,
            missing_inputs=missing,
            should_clarify=should_clarify,
            local_routing=local_routing,
            reasoning=data.get("reasoning", ""),
        )

    def _fallback_classify(self, prompt: str) -> SLMClassification:
        """Fallback to keyword-based classification."""
        prompt_lower = prompt.lower()

        # Simple keyword matching
        intent = "unknown"
        confidence = 0.3
        missing = []
        reasoning = "fallback_heuristic"

        keywords = {
            "implement_feature": ["crea", "añade", "implementa", "nueva", "feature", "haz"],
            "debug_repo": ["arregla", "bug", "error", "problema", "fix", "debug"],
            "refactor_migration": ["refactoriza", "migra", "restructura"],
            "run_tests_ci": ["test", "prueba", "ci", "ejecuta"],
            "explain_concept": ["explica", "qué es", "cómo funciona"],
            "design_architecture": ["diseño", "arquitectura", "estructura"],
            "toolchain_task": ["git", "docker", "npm", "pip"],
            "ops_health_check": ["salud", "status", "health", "monitor"],
            "incident_triage": ["incidente", "emergencia", " outage"],
            "greeting": ["hola", "hi", "hello", "buenas"],
        }

        for intent_name, words in keywords.items():
            if any(w in prompt_lower for w in words):
                intent = intent_name
                confidence = 0.6
                reasoning = f"keyword_match:{words[0]}"
                break

        if intent == "unknown":
            local_routing = "clarify"
            should_clarify = True
            missing = ["intent_unclear"]
        elif confidence >= 0.55:
            local_routing = "heuristic"
            should_clarify = False
        else:
            local_routing = "clarify"
            should_clarify = True

        return SLMClassification(
            intent=intent,
            confidence=confidence,
            missing_inputs=missing,
            should_clarify=should_clarify,
            local_routing=local_routing,
            reasoning=reasoning,
        )

    async def clarify(self, prompt: str, missing: list[str]) -> str:
        """
        Generate clarification question for missing inputs.

        Uses local model to ask clarifying questions.
        """
        system_prompt = f"""El usuario quiere: "{prompt}"

Falta información: {", ".join(missing)}

Genera una pregunta de clarificación SIMPLE y DIRECTA (1-2 líneas).
No menciones los intents disponibles. Solo pregunta qué necesita."""

        try:
            client = self._get_client()
            if not client:
                return f"¿Qué más necesitas sobre: {', '.join(missing)}?"

            response = await client.chat(
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.5,
                max_tokens=100,
            )
            return response.get("content", "").strip()
        except Exception:
            return f"¿Qué más necesitas sobre: {', '.join(missing)}?"


# Singleton
_slm_router: Optional[SLMRouter] = None


def get_slm_router() -> SLMRouter:
    """Get SLM Router singleton."""
    global _slm_router
    if _slm_router is None:
        _slm_router = SLMRouter()
    return _slm_router
