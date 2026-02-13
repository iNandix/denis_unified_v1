"""
Legacy compatibility shim for denisunifiedv1.api.metacognitiveapi.
Re-exports metacognitive router from the canonical api.metacognitive_api module.
"""

from api.metacognitive_api import router as metacognitiveapi_router

__all__ = ["metacognitiveapi_router"]
