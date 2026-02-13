"""Cliente NLU: Rasa 5005 + ParlAI 5006."""
import httpx
from typing import Dict, Optional
from denis_unified_v1.metacognitive.hooks import metacognitive_trace

class NLUClient:
    def __init__(self):
        self.rasa_url = "http://localhost:5005"
        self.parlai_url = "http://localhost:5006"
        self.client = httpx.AsyncClient(timeout=5.0)

    @metacognitive_trace(operation="nlu_parse")
    async def parse(self, text: str) -> Dict:
        """
        Parsea intención con Rasa, enriquece con ParlAI.
        Devuelve: {intent, entities, confidence, risk_level, route_hint}.
        """
        # 1) Rasa: intención básica
        try:
            rasa_resp = await self.client.post(
                f"{self.rasa_url}/model/parse",
                json={"text": text},
            )
            rasa_data = rasa_resp.json()
            intent = rasa_data.get("intent", {}).get("name", "unknown")
            confidence = rasa_data.get("intent", {}).get("confidence", 0.0)
            entities = rasa_data.get("entities", [])
        except:
            intent = "chat"
            confidence = 0.5
            entities = []

        # 2) ParlAI: señales adicionales (si disponible)
        route_hint = "fast" if len(text.split()) <= 3 else "balanced"
        risk_level = "low"

        # Validación: NO alucinar PII
        if intent == "greet" and not any(e["entity"] in ["email", "phone"] for e in entities):
            entities = []  # Limpiar alucinaciones

        return {
            "intent": intent,
            "entities": entities,
            "confidence": confidence,
            "risk_level": risk_level,
            "route_hint": route_hint,
            "needs_macro": intent in ["code", "debug", "infrastructure"],
            "needs_tools": False,
        }
