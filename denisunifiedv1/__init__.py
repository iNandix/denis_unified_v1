"""
Legacy compatibility shim for denisunifiedv1 imports.
Re-exports functionality from the canonical packages.
"""

# Re-export core functionality
from api.fastapi_server import create_app as createapp
from api.metacognitive_api import router as metacognitiveapi_router

__all__ = ["createapp", "metacognitiveapi_router"]
