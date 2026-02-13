"""Minimal SMX implementation for fail-open."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List


class SMXClient:
    """Minimal SMX client implementation."""
    
    def __init__(self):
        pass
    
    async def call_motor(self, motor: str, messages: List[Dict], max_tokens: int = 100) -> Dict[str, Any]:
        """Mock motor call."""
        # Return minimal response
        return {
            "response": f"SMX {motor} response for {len(messages)} messages",
            "motor": motor,
            "tokens_used": min(len(str(messages)), max_tokens),
        }


class NLUClient:
    """Minimal NLU client."""
    
    def __init__(self):
        pass
    
    async def parse(self, text: str) -> Dict[str, Any]:
        """Mock NLU parse."""
        return {
            "intent": "general_query",
            "entities": [],
            "route_hint": "inference",
        }


# Export for compatibility
__all__ = ["SMXClient", "NLUClient"]
