"""Engine registry (canonical).

Canonical source of truth for engine_id -> provider_key/endpoint/model/tags/priority.

Scheduler and Router MUST read from here (or from a future loader that produces the same schema).

Contract (minimal required fields per engine):
  - provider_key: str
  - model: str
  - endpoint: str
  - tags: list[str]  (must include "local" OR "internet_required")
  - priority: int    (lower = better)
Optional:
  - params_default: dict
  - max_context: int
  - cost_factor: float
"""

from __future__ import annotations

from typing import Any

_engine_registry: dict[str, dict[str, Any]] = {}


def _build_static_registry() -> dict[str, dict[str, Any]]:
    """Build the static engine registry.

    ACTUAL HARDWARE:
    - nodo1 (this PC): RTX 3080 10GB -> 9997, 9998
    - nodo2 (10.10.10.2): 1050 Ti 4GB -> 8003-8008
    """
    return {
        # nodo1 / PC: RTX 3080 10GB - Heavy models
        "qwen3b_local": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-3b-instruct",
            "endpoint": "http://127.0.0.1:9997",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "node1", "response"],
            "role": "response",
            "priority": 5,
            "max_concurrency": 2,
            "gpu": "3080_10gb",
            "capabilities": {"stream": True, "chat": True, "tools": True},
        },
        "qwen_coder7b_local": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-coder-7b",
            "endpoint": "http://127.0.0.1:9998",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "node1", "coder"],
            "role": "coder",
            "priority": 6,
            "max_concurrency": 2,
            "gpu": "3080_10gb",
            "capabilities": {"stream": True, "chat": True, "tools": True},
        },
        # nodo2: 1050 Ti 4GB - Light engines
        "qwen05b_node2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-0.5b",
            "endpoint": "http://10.10.10.2:8003",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "node2", "fast"],
            "role": "fast",
            "priority": 10,
            "max_concurrency": 4,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        "smollm_node2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "smollm2-1.7b",
            "endpoint": "http://10.10.10.2:8006",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "node2", "intent"],
            "role": "intent",
            "priority": 15,
            "max_concurrency": 4,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        "gemma_node2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "gemma-3-1b",
            "endpoint": "http://10.10.10.2:8007",
            "params_default": {"temperature": 0.1},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "node2", "safety"],
            "role": "safety",
            "priority": 20,
            "max_concurrency": 4,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": False, "chat": True, "tools": False},
        },
        "qwen15b_node2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-1.5b",
            "endpoint": "http://10.10.10.2:8008",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0002,
            "max_context": 3072,
            "tags": ["local", "node2", "balanced"],
            "role": "balanced",
            "priority": 25,
            "max_concurrency": 3,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        # TTS (Piper)
        "piper_tts": {
            "provider_key": "piper",
            "provider": "piper",
            "model": "piper-es",
            "endpoint": "http://10.10.10.2:8005",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0,
            "max_context": 0,
            "tags": ["local", "node2", "tts"],
            "role": "tts",
            "priority": 1,
            "capabilities": {"stream": True, "chat": False, "tools": False},
        },
        # Internet boosters (disabled - offline-first)
        "groq_booster": {
            "provider_key": "groq",
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "endpoint": "groq://api.groq.com/openai/v1",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.05,
            "max_context": 128000,
            "tags": ["booster", "internet_required"],
            "role": "booster",
            "priority": 99,
            "enabled": False,
        },
    }


def validate_engine_registry(registry: dict[str, dict[str, Any]]) -> None:
    """Fail-loud validation of registry schema and invariants."""
    errors: list[str] = []

    def _err(msg: str) -> None:
        errors.append(msg)

    if not isinstance(registry, dict) or not registry:
        raise ValueError("engine_registry must be a non-empty dict")

    for engine_id, e in registry.items():
        if not isinstance(engine_id, str) or not engine_id.strip():
            _err(f"engine_id invalid: {engine_id!r}")
            continue
        if not isinstance(e, dict):
            _err(f"{engine_id}: entry must be dict, got {type(e).__name__}")
            continue

        provider_key = e.get("provider_key")
        model = e.get("model")
        endpoint = e.get("endpoint")
        tags = e.get("tags")
        priority = e.get("priority")

        if not isinstance(provider_key, str) or not provider_key.strip():
            _err(f"{engine_id}: missing/invalid provider_key")
        if not isinstance(model, str) or not model.strip():
            _err(f"{engine_id}: missing/invalid model")
        if not isinstance(endpoint, str) or not endpoint.strip():
            _err(f"{engine_id}: missing/invalid endpoint")
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            _err(f"{engine_id}: tags must be list[str]")
        if not isinstance(priority, int):
            _err(f"{engine_id}: priority must be int (lower=better)")

        # Behavioral invariants
        if isinstance(tags, list):
            is_local = "local" in tags
            needs_net = "internet_required" in tags
            if not is_local and not needs_net:
                _err(f"{engine_id}: tags must include 'local' or 'internet_required'")

            if is_local and isinstance(endpoint, str):
                if endpoint.startswith("http://") or endpoint.startswith("https://"):
                    pass  # Valid local endpoint
                elif endpoint.startswith("groq://"):
                    _err(f"{engine_id}: groq must be internet_required")

    if errors:
        raise ValueError("engine_registry validation failed:\n" + "\n".join(errors))


def get_engine_registry() -> dict[str, dict[str, Any]]:
    global _engine_registry
    if not _engine_registry:
        _engine_registry = _build_static_registry()
        validate_engine_registry(_engine_registry)
    return _engine_registry


def get_engine(engine_id: str) -> dict[str, Any] | None:
    return get_engine_registry().get(engine_id)


def list_engines(
    tags: list[str] | None = None,
    roles: list[str] | None = None,
    include_disabled: bool = False,
) -> dict[str, dict[str, Any]]:
    registry = get_engine_registry()

    filtered = {}
    for engine_id, config in registry.items():
        # Skip disabled engines
        if not include_disabled and not config.get("enabled", True):
            continue

        # Filter by tags
        if tags:
            engine_tags = config.get("tags", [])
            if not any(t in engine_tags for t in tags):
                continue

        # Filter by role
        if roles:
            if config.get("role") not in roles:
                continue

        filtered[engine_id] = config

    return filtered


def reset_registry() -> None:
    """Reset cached engine registry (tests only)."""
    global _engine_registry
    _engine_registry = {}
