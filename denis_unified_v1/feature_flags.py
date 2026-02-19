"""Feature flags for DENIS.

Simple, type-safe feature flags with environment variable support.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os
import threading


def _env_bool(name: str, default: bool) -> bool:
    """Load boolean from environment variable."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class FeatureFlags:
    """Feature flags container - all booleans, no None."""

    # Graph-centric migration flags (graph-first by default)
    graph_only: bool = False
    router_uses_graph: bool = True
    planner_uses_graph: bool = True
    approval_uses_graph: bool = True
    tool_executor_uses_graph: bool = True
    context_uses_graph: bool = True
    memory_uses_graph: bool = True
    engines_uses_graph: bool = True

    # Legacy flags (keep for compatibility)
    denis_use_voice_pipeline: bool = False
    denis_use_memory_unified: bool = False
    denis_use_atlas: bool = False
    denis_use_inference_router: bool = False
    phase10_enable_prompt_injection_guard: bool = False
    phase10_max_output_tokens: int = 512
    use_smx_local: bool = True
    phase12_smx_enabled: bool = True
    phase12_smx_fast_path: bool = True
    denis_persona_unified: bool = False
    denis_enable_action_planner: bool = False

    # InferenceGateway flags (Track B)
    denis_enable_inference_gateway: bool = False
    denis_gateway_shadow_mode: bool = False

    # Chat Control Plane flags
    denis_enable_chat_cp: bool = False
    denis_chat_cp_shadow_mode: bool = False

    # WS23-G Neuroplasticity
    neuro_enabled: bool = True


_flags_instance: Optional[FeatureFlags] = None
_flags_lock = threading.Lock()


def load_feature_flags(force_reload: bool = False) -> FeatureFlags:
    """Load feature flags from environment (thread-safe singleton)."""
    global _flags_instance
    if _flags_instance is not None and not force_reload:
        return _flags_instance

    with _flags_lock:
        if _flags_instance is not None and not force_reload:
            return _flags_instance

        _flags_instance = FeatureFlags(
            # Graph-centric migration flags
            graph_only=_env_bool("GRAPH_ONLY", False),
            router_uses_graph=_env_bool("ROUTER_USES_GRAPH", True),
            planner_uses_graph=_env_bool("PLANNER_USES_GRAPH", True),
            approval_uses_graph=_env_bool("APPROVAL_USES_GRAPH", True),
            tool_executor_uses_graph=_env_bool("TOOL_EXECUTOR_USES_GRAPH", True),
            context_uses_graph=_env_bool("CONTEXT_USES_GRAPH", True),
            memory_uses_graph=_env_bool("MEMORY_USES_GRAPH", True),
            engines_uses_graph=_env_bool("ENGINES_USES_GRAPH", True),
            # Legacy flags
            denis_use_voice_pipeline=_env_bool("DENIS_USE_VOICE_PIPELINE", False),
            denis_use_memory_unified=_env_bool("DENIS_USE_MEMORY_UNIFIED", False),
            denis_use_atlas=_env_bool("DENIS_USE_ATLAS", False),
            denis_use_inference_router=_env_bool("DENIS_USE_INFERENCE_ROUTER", False),
            phase10_enable_prompt_injection_guard=_env_bool(
                "PHASE10_ENABLE_PROMPT_INJECTION_GUARD", False
            ),
            phase10_max_output_tokens=int(
                os.getenv("PHASE10_MAX_OUTPUT_TOKENS", "512")
            ),
            use_smx_local=_env_bool("USE_SMX_LOCAL", True),
            phase12_smx_enabled=_env_bool("PHASE12_SMX_ENABLED", True),
            phase12_smx_fast_path=_env_bool("PHASE12_SMX_FAST_PATH", True),
            denis_persona_unified=_env_bool("DENIS_PERSONA_UNIFIED", False),
            denis_enable_action_planner=_env_bool("DENIS_ENABLE_ACTION_PLANNER", False),
            # InferenceGateway flags (Track B)
            denis_enable_inference_gateway=_env_bool(
                "DENIS_ENABLE_INFERENCE_GATEWAY", False
            ),
            denis_gateway_shadow_mode=_env_bool("DENIS_GATEWAY_SHADOW_MODE", False),
            # Chat Control Plane flags
            denis_enable_chat_cp=_env_bool("DENIS_ENABLE_CHAT_CP", False),
            denis_chat_cp_shadow_mode=_env_bool("DENIS_CHAT_CP_SHADOW_MODE", False),
            # WS23-G Neuroplasticity
            neuro_enabled=_env_bool("NEURO_ENABLED", True),
        )
        return _flags_instance


def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled (compatibility wrapper)."""
    flags = load_feature_flags()
    return getattr(flags, flag, False)
