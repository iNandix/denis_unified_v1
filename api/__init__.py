"""API module for Denis Unified V1 - Canonical Package Structure.

This module provides the unified API for all Denis functionality.
All imports should be relative and work within the package context.
"""

# Canonical exports - avoid import cycles by lazy importing
__all__ = [
    "create_app",  # Main FastAPI app factory
    "get_metacognitive_router",  # Metacognitive endpoints
    "get_memory_router",  # Memory management endpoints
    "get_voice_router",  # Voice processing endpoints
    "get_openai_compatible_router",  # OpenAI compatible API
]

def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name == "create_app":
        from .fastapi_server import create_app
        return create_app
    elif name == "get_metacognitive_router":
        from .metacognitive_api import router
        return router
    elif name == "get_memory_router":
        from .memory_handler import build_memory_router
        return build_memory_router()
    elif name == "get_voice_router":
        from .voice_handler import build_voice_router
        return build_voice_router()
    elif name == "get_openai_compatible_router":
        from .openai_compatible import build_openai_router
        return build_openai_router()
    else:
        raise AttributeError(f"module 'api' has no attribute '{name}'")

