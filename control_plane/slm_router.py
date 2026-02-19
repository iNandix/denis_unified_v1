"""SLM Router - Rasa NLU + ParLAI + Local SLM intent classification.

Uses:
- Rasa NLU for intent classification (trained model)
- ParLAI action templates for response generation
- nodo1 local SLM (llama-3.2-3b) as fallback

Goal: 100% local intent classification, NO external APIs.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Threshold for escalation - below this, clarify with user
CONFIDENCE_THRESHOLD = 0.55

# Rasa NLU model path
RASA_MODEL_PATH = os.getenv("RASA_MODEL_PATH", "models/rasa_nlu")


# ParLAI action templates - mapped from Rasa intents
PARLAI_ACTIONS: Dict[str, Dict[str, Any]] = {
    "implement_feature": {
        "action": "utter_ask_details",
        "template": "Para crear {feature}, necesito saber: technology stack, scope",
        "slots": ["tech_stack", "scope"],
    },
    "debug_repo": {
        "action": "utter_ask_error",
        "template": "Para debuggear, necesito: error message, file path, reproduction steps",
        "slots": ["error_msg", "file_path", "steps"],
    },
    "refactor_migration": {
        "action": "utter_ask_target",
        "template": "Refactorizando, necesito: target architecture, files affected",
        "slots": ["target", "files"],
    },
    "run_tests_ci": {
        "action": "utter_run_tests",
        "template": "Ejecutando tests en {test_suite}...",
        "slots": ["test_suite"],
    },
    "explain_concept": {
        "action": "utter_explain",
        "template": "Explicando {concept}...",
        "slots": ["concept"],
    },
    "design_architecture": {
        "action": "utter_ask_requirements",
        "template": "Para diseñar, necesito: requirements, constraints, scale",
        "slots": ["requirements", "constraints", "scale"],
    },
    "toolchain_task": {
        "action": "utter_toolchain",
        "template": "Ejecutando toolchain: {tool}...",
        "slots": ["tool"],
    },
    "ops_health_check": {
        "action": "utter_health_check",
        "template": "Ejecutando health check de {component}...",
        "slots": ["component"],
    },
    "incident_triage": {
        "action": "utter_incident",
        "template": "Triaging incidente: {incident_id}",
        "slots": ["incident_id"],
    },
    "greeting": {
        "action": "utter_greet",
        "template": "¡Hola! Soy Denis. ¿En qué puedo ayudarte?",
        "slots": [],
    },
}


@dataclass
class SLMClassification:
    """Result from SLM intent classification."""

    intent: str
    confidence: float
    missing_inputs: list[str]
    should_clarify: bool
    local_routing: str  # "local", "heuristic", "groq"
    reasoning: str
    # Rasa/ParLAI fields
    rasa_intent: str = ""
    parlai_action: str = ""
    action_template: str = ""
    slots_needed: list[str] = field(default_factory=list)


class SLMRouter:
    """
    SLM-first intent classifier with Rasa NLU + ParLAI integration.

    Flow:
    1. Try Rasa NLU first (trained model)
    2. Fallback to local SLM (nodo1)
    3. Last fallback: keyword heuristics
    4. Map to ParLAI action template

    Target: 100% local, NO external APIs
    """

    def __init__(self):
        self._client = None
        self._rasa_agent = None
        self._endpoint = os.getenv("SLM_ENDPOINT", "http://127.0.0.1:9997")

    def _get_rasa(self):
        """Lazy load Rasa NLU agent."""
        if self._rasa_agent is None:
            try:
                from rasa.core.agent import Agent

                self._rasa_agent = Agent.load(RASA_MODEL_PATH)
                logger.info("Rasa NLU loaded")
            except Exception as e:
                logger.warning(f"Rasa NLU init failed: {e}")
                self._rasa_agent = False  # Mark as failed
        return self._rasa_agent if self._rasa_agent else None

    def _get_parlai_action(self, intent: str) -> Dict[str, str]:
        """Get ParLAI action template for intent."""
        return PARLAI_ACTIONS.get(
            intent,
            {
                "action": "utter_unknown",
                "template": "No entiendo, ¿puedes reformular?",
                "slots": [],
            },
        )

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
        Classify user intent: Rasa NLU → Local SLM → Fallback.

        Priority:
        1. Rasa NLU (trained model) - highest confidence
        2. Local SLM (nodo1)
        3. Keyword heuristics (fallback)

        Always maps to ParLAI action template.
        """
        # 1. Try Rasa NLU first
        rasa_result = self._try_rasa(user_prompt)
        if rasa_result:
            return rasa_result

        # 2. Try local SLM
        slm_result = await self._try_slm(user_prompt)
        if slm_result:
            return slm_result

        # 3. Fallback to heuristics
        return self._fallback_classify(user_prompt)

    def _try_rasa(self, user_prompt: str) -> Optional[SLMClassification]:
        """Try Rasa NLU classification."""
        try:
            rasa = self._get_rasa()
            if not rasa:
                return None

            parse_result = rasa.parse_message(user_prompt)
            intent = parse_result.get("intent", {}).get("name", "unknown")
            confidence = parse_result.get("intent", {}).get("confidence", 0.0)

            if intent and confidence > 0.5:
                parlai = self._get_parlai_action(intent)
                return SLMClassification(
                    intent=intent,
                    confidence=confidence,
                    missing_inputs=[],
                    should_clarify=False,
                    local_routing="local",
                    reasoning=f"rasa_nlu:{confidence:.2f}",
                    rasa_intent=intent,
                    parlai_action=parlai["action"],
                    action_template=parlai["template"],
                    slots_needed=parlai.get("slots", []),
                )
        except Exception as e:
            logger.debug(f"Rasa parse failed: {e}")
        return None

    async def _try_slm(self, user_prompt: str) -> Optional[SLMClassification]:
        """Try local SLM classification."""
        system_prompt = """Eres un clasificador de intents.

Intents: implement_feature, debug_repo, refactor_migration, run_tests_ci, explain_concept, design_architecture, toolchain_task, ops_health_check, incident_triage, greeting, unknown

Responde JSON: {"intent": "...", "confidence": 0.0-1.0, "missing_inputs": []}"""

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
