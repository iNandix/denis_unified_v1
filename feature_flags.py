"""Real feature flags implementation."""

import os
from typing import Dict, Any


class FeatureFlags:
    """Real feature flags implementation."""

    def __init__(self):
        self._flags = self._load_flags()

    def _load_flags(self) -> Dict[str, Any]:
        """Load flags from environment."""
        flags = {}
        
        # Default flags
        defaults = {
            "denis_use_voice_pipeline": False,
            "denis_use_memory_unified": False,
            "denis_use_atlas": False,
            "denis_use_inference_router": False,
            "phase10_enable_prompt_injection_guard": False,
            "phase10_max_output_tokens": 512,
        }
        
        # Override from environment
        for key, default in defaults.items():
            env_key = key.upper()
            env_value = os.getenv(env_key)
            if env_value is not None:
                # Parse boolean
                if isinstance(default, bool):
                    flags[key] = env_value.lower() in ('true', '1', 'yes', 'on')
                else:
                    flags[key] = type(default)(env_value)
            else:
                flags[key] = default
        
        return flags

    def get(self, key: str, default=None):
        return self._flags.get(key, default)

    def __getitem__(self, key: str):
        return self._flags[key]

    def __contains__(self, key: str):
        return key in self._flags

    def as_dict(self):
        return self._flags.copy()


# Global instance
_flags_instance = None

def load_feature_flags():
    """Load feature flags."""
    global _flags_instance
    if _flags_instance is None:
        _flags_instance = FeatureFlags()
    return _flags_instance

def load_featureflags():
    """Alias."""
    return load_feature_flags()
