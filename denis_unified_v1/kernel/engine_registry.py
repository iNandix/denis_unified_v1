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
    """Build the static engine registry (canonical source).

    Graph-centric: Reads from Neo4j if available, falls back to static config.
    Mixture of Experts across node1 (heavy) and node2 (specialized).

    node1: 2x large models (chat_general, reasoning_deep) - parallel heavy lifting
    node2: 4x specialized (PLANNER, SCHEDULER, WATCHER, EXECUTOR)
    """
    # TODO: Load from graph when DENIS_GRAPH_ENABLED=true
    # Query: MATCH (e:Engine) RETURN e.name, e.endpoint, e.model, e.tags, e.priority, e.role
    return {
        # node1: Heavy engines (parallel capable)
        "llamacpp_node1_1": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://10.10.10.1:8081",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 8192,
            "tags": ["local", "fast", "chat_general"],
            "role": "chat_general",
            "priority": 5,
        },
        "llamacpp_node1_2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-7b",
            "endpoint": "http://10.10.10.1:8082",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 8192,
            "tags": ["local", "reasoning", "deep"],
            "role": "reasoning_deep",
            "priority": 6,
        },
        # node2: Specialized engines (Mixture of Experts)
        "llamacpp_node2_1": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "llama-3.1-8b",
            "endpoint": "http://10.10.10.2:8081",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "fast", "planner"],
            "role": "PLANNER",
            "priority": 10,
        },
        "llamacpp_node2_2": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "qwen2.5-3b",
            "endpoint": "http://10.10.10.2:8082",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.001,
            "max_context": 4096,
            "tags": ["local", "scheduler"],
            "role": "SCHEDULER",
            "priority": 20,
        },
        "llamacpp_node2_3": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "phi-3-mini",
            "endpoint": "http://10.10.10.2:8083",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0005,
            "max_context": 4096,
            "tags": ["local", "small", "watcher", "preprocess"],
            "role": "WATCHER",
            "priority": 25,
        },
        "llamacpp_node2_4": {
            "provider_key": "llamacpp",
            "provider": "llama_cpp",
            "model": "tinyllama",
            "endpoint": "http://10.10.10.2:8084",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.0001,
            "max_context": 2048,
            "tags": ["local", "tiny", "fast", "chat_fast", "executor"],
            "role": "EXECUTOR",
            "priority": 30,
        },
        # Internet boosters
        "groq_1": {
            "provider_key": "groq",
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "endpoint": "groq://api.groq.com/openai/v1",
            "params_default": {"temperature": 0.2},
            "cost_factor": 0.05,
            "max_context": 128000,
            "tags": ["booster", "internet_required", "fast"],
            "role": "booster",
            "priority": 50,
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
