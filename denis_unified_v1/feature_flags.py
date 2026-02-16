"""Feature flags for DENIS.

Local re-implementation to avoid circular imports.
"""

import os
from typing import Dict, Any


class FeatureFlags:
    """Feature flags container."""

    def __init__(self):
        self._flags = self._load_flags()

    def _load_flags(self) -> Dict[str, Any]:
        flags = {}
        defaults = {
            "denis_use_voice_pipeline": False,
            "denis_use_memory_unified": False,
            "denis_use_atlas": False,
            "denis_use_inference_router": False,
            "phase10_enable_prompt_injection_guard": False,
            "phase10_max_output_tokens": 512,
            "use_smx_local": True,
            "phase12_smx_enabled": True,
            "phase12_smx_fast_path": True,
            "denis_persona_unified": False,
            "denis_enable_action_planner": False,
            # Graph-centric migration flags
            "graph_only": False,
            "router_uses_graph": True,
            "planner_uses_graph": True,
            "approval_uses_graph": False,
            "tool_executor_uses_graph": False,
            "context_uses_graph": False,
            "memory_uses_graph": False,
            "engines_uses_graph": False,
        }
        for key, default in defaults.items():
            env_val = os.getenv(key.upper())
            if env_val is not None:
                flags[key] = env_val.lower() == "true"
            else:
                flags[key] = default
        return flags

    def get(self, key: str, default: Any = None) -> Any:
        return self._flags.get(key, default)

    def is_enabled(self, key: str) -> bool:
        return self._flags.get(key, False)

    def __getitem__(self, key: str) -> Any:
        return self._flags[key]

    def __contains__(self, key: str) -> bool:
        return key in self._flags


_flags_instance: FeatureFlags = None


def load_feature_flags() -> FeatureFlags:
    """Load feature flags."""
    global _flags_instance
    if _flags_instance is None:
        _flags_instance = FeatureFlags()
    return _flags_instance


def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled."""
    return load_feature_flags().is_enabled(flag)
