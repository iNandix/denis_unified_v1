"""
Legacy compatibility shim for denisunifiedv1.api imports.
Re-exports API functionality from the canonical api package.
"""

# Re-export API components
from api.fastapi_server import create_app as createapp, app
from api.metacognitive_api import router as metacognitiveapi_router

__all__ = ["createapp", "app", "metacognitiveapi_router"]
