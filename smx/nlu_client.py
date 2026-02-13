# Minimal NOOP implementation for compatibility

class NLUClient:
    def parse(self, text: str) -> dict:
        # Dummy NLU parsing
        return {
            "intent": "unknown",
            "entities": [],
            "confidence": 0.5
        }
