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

    Hardware-aware Mixture of Experts:

    nodo1 / PC (RTX 3080 10GB) - Chat principal pesado:
      - llama3_8b_response_a (9001) → response
      - llama3_8b_response_b (9002) → response (fallback/load-balance)
      - qwen2_7b_macro (9003) → macro (reasoning largo)

    nodo2 (1050 Ti 4GB) - Engines ligeros:
      - smollm_intent (8081) → intent, router
      - phi3_safety (8082) → safety, policy
      - tiny_draft (8083) → draft, speculative decoding
    """
    # TODO: Load from graph when DENIS_GRAPH_ENABLED=true
    return {
        # nodo1 / PC: RTX 3080 10GB - Heavy chat
        "llama3_8b_response_a": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://127.0.0.1:9001",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "response"],
            "role": "response",
            "priority": 10,
            "max_concurrency": 4,
            "gpu": "3080_10gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        "llama3_8b_response_b": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://127.0.0.1:9002",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "response"],
            "role": "response",
            "priority": 20,
            "max_concurrency": 4,
            "gpu": "3080_10gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        "qwen2_7b_macro": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-7b",
            "endpoint": "http://127.0.0.1:9003",
            "params_default": {"temperature": 0.3},
            "cost_factor": 0.001,
            "max_context": 8192,
            "tags": ["local", "macro"],
            "role": "macro",
            "priority": 40,
            "max_concurrency": 2,
            "gpu": "3080_10gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        # nodo2: 1050 Ti 4GB - Light engines
        "smollm_intent": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "smollm",
            "endpoint": "http://10.10.10.2:8081",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "intent", "router"],
            "role": "intent",
            "priority": 5,
            "max_concurrency": 8,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        "phi3_safety": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "phi-3-mini",
            "endpoint": "http://10.10.10.2:8082",
            "params_default": {"temperature": 0.1},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "safety", "policy"],
            "role": "safety",
            "priority": 8,
            "max_concurrency": 8,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": False, "chat": True, "tools": False},
        },
        "tiny_draft": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "tinyllama",
            "endpoint": "http://10.10.10.2:8083",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "draft", "response"],
            "role": "draft",
            "priority": 15,
            "max_concurrency": 8,
            "gpu": "1050ti_4gb",
            "capabilities": {"stream": True, "chat": True, "tools": False},
        },
        # Internet boosters (disabled - offline-first)
        "groq_1": {
            "provider_key": "groq",
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "endpoint": "groq://api.groq.com/openai/v1",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.05,
            "max_context": 128000,
            "tags": ["booster", "internet_required"],
            "role": "booster",
            "priority": 50,
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
                if not (
                    endpoint.startswith("http://") or endpoint.startswith("https://")
                ):
                    _err(
                        f"{engine_id}: local endpoint must be http(s), got {endpoint!r}"
                    )

    if errors:
        raise ValueError("Invalid engine_registry:\n  - " + "\n  - ".join(errors))


def get_engine_registry() -> dict[str, dict[str, Any]]:
    """Return the engine registry (canonical source)."""
    global _engine_registry
    if not _engine_registry:
        _engine_registry = _build_static_registry()
        validate_engine_registry(_engine_registry)
    return _engine_registry


def resolve_engine(engine_id: str) -> dict[str, Any] | None:
    """Resolve a single engine_id to its registry entry."""
    return get_engine_registry().get(engine_id)


def reset_registry() -> None:
    """Reset the registry (for testing)."""
    global _engine_registry
    _engine_registry = {}
