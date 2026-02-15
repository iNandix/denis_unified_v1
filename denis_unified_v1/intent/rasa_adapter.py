"""Rasa NLU Adapter for DENIS Intent Detection.

Provides graceful degradation when Rasa is unavailable.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RasaParseResult:
    """Result from Rasa NLU parsing."""

    intent: Optional[str]
    confidence: float
    entities: Dict[str, Any]
    status: str  # "ok", "unavailable", "error"
    model_fingerprint: Optional[str]
    latency_ms: Optional[float]
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "entities": self.entities,
            "status": self.status,
            "model_fingerprint": self.model_fingerprint,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }


class RasaAdapter:
    """Adapter for Rasa NLU with graceful degradation."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model_path: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """Initialize Rasa adapter.

        Args:
            endpoint: Rasa server endpoint (e.g., "http://localhost:5005")
            model_path: Local model path for direct loading
            timeout: Request timeout in seconds
        """
        self.endpoint = endpoint or os.getenv("RASA_ENDPOINT", "http://localhost:5005")
        self.model_path = model_path or os.getenv("RASA_MODEL_PATH")
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._model_fingerprint: Optional[str] = None

    def is_available(self) -> bool:
        """Check if Rasa is available (cached)."""
        if self._available is None:
            self._available = self._check_availability()
        return self._available

    def _check_availability(self) -> bool:
        """Check Rasa availability by making a health request."""
        try:
            import requests

            response = requests.get(f"{self.endpoint}/status", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                self._model_fingerprint = data.get("model_file", "unknown")
                return True
        except Exception:
            pass

        # Try local model loading if endpoint not available
        if self.model_path and os.path.exists(self.model_path):
            try:
                # Could load model directly here if needed
                self._model_fingerprint = f"local:{self.model_path}"
                return True
            except Exception:
                pass

        return False

    def parse(self, text: str) -> RasaParseResult:
        """Parse text using Rasa NLU.

        Returns:
            RasaParseResult with intent, confidence, entities, and status.
            If Rasa unavailable, returns status="unavailable".
        """
        start_time = time.time()

        # Check availability
        if not self.is_available():
            return RasaParseResult(
                intent=None,
                confidence=0.0,
                entities={},
                status="unavailable",
                model_fingerprint=None,
                latency_ms=None,
                error_message="Rasa not available",
            )

        # Try to parse via endpoint
        try:
            import requests

            response = requests.post(
                f"{self.endpoint}/model/parse",
                json={"text": text},
                timeout=self.timeout,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()

                intent_data = data.get("intent", {})
                entities_data = data.get("entities", [])

                # Convert entities to dict
                entities = {}
                for ent in entities_data:
                    ent_name = ent.get("entity", "unknown")
                    ent_value = ent.get("value", "")
                    if ent_name not in entities:
                        entities[ent_name] = []
                    entities[ent_name].append(ent_value)

                return RasaParseResult(
                    intent=intent_data.get("name"),
                    confidence=intent_data.get("confidence", 0.0),
                    entities=entities,
                    status="ok",
                    model_fingerprint=self._model_fingerprint,
                    latency_ms=latency_ms,
                )
            else:
                return RasaParseResult(
                    intent=None,
                    confidence=0.0,
                    entities={},
                    status="error",
                    model_fingerprint=self._model_fingerprint,
                    latency_ms=latency_ms,
                    error_message=f"HTTP {response.status_code}",
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            # Mark as unavailable for future calls
            self._available = False

            return RasaParseResult(
                intent=None,
                confidence=0.0,
                entities={},
                status="error",
                model_fingerprint=self._model_fingerprint,
                latency_ms=latency_ms,
                error_message=str(e),
            )

    def reset_availability(self) -> None:
        """Reset availability cache (for testing)."""
        self._available = None


# Singleton adapter
_adapter: Optional[RasaAdapter] = None


def get_rasa_adapter() -> RasaAdapter:
    """Get singleton Rasa adapter."""
    global _adapter
    if _adapter is None:
        _adapter = RasaAdapter()
    return _adapter


def parse_with_rasa(text: str) -> RasaParseResult:
    """Convenience function to parse text with Rasa."""
    return get_rasa_adapter().parse(text)


def is_rasa_available() -> bool:
    """Check if Rasa is available."""
    return get_rasa_adapter().is_available()
