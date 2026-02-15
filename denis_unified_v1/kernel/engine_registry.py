"""Engine registry: singleton source for engine_id → provider_key mapping.

This is the CANONICAL source of truth for all engine IDs.
Scheduler and Router must read from here, not maintain separate lists.
"""

from __future__ import annotations

_engine_registry: dict[str, dict] = {}

_PROVIDER_KEY_MAP = {
    "llamacpp": "llamacpp",
    "groq": "groq",
    "openrouter": "openrouter",
    "vllm": "vllm",
}


def _build_static_registry() -> dict[str, dict]:
    """Build the static engine registry (canonical source)."""
    return {
        # Local llama.cpp engines (node2) - sorted by priority (lower = better)
        "llamacpp_node2_1": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://10.10.10.2:8081",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "priority": 10,  # Lower = better
            "tags": ["local", "node2", "fast"],
        },
        "llamacpp_node2_2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-3b",
            "endpoint": "http://10.10.10.2:8082",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "priority": 20,
            "tags": ["local", "node2"],
        },
        # Groq boosters - higher priority number = fallback
        "groq_1": {
            "provider_key": "groq",
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "endpoint": "groq://api.groq.com/openai/v1",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.05,
            "max_context": 128000,
            "priority": 5,  # Lower = better (fast)
            "tags": ["booster", "internet_required", "fast"],
        },
    }


def get_engine_registry() -> dict[str, dict]:
    """Return the engine registry (canonical source)."""
    global _engine_registry
    if not _engine_registry:
        _engine_registry = _build_static_registry()
    return _engine_registry


def resolve_engine(engine_id: str) -> dict | None:
    """Resolve a single engine_id to its registry entry."""
    return get_engine_registry().get(engine_id)


def reset_registry() -> None:
    """Reset the registry (for testing)."""
    global _engine_registry
    _engine_registry = {}
