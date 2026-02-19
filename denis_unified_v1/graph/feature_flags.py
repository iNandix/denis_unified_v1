"""Feature flags for Denis engine."""

from enum import Enum
from typing import Any, Optional


class FeatureFlag(str, Enum):
    """Available feature flags."""

    ENABLE_CONTEXT_HARVESTER = "enable_context_harvester"
    ENABLE_REDUNDANCY_DETECTOR = "enable_redundancy_detector"
    ENABLE_CONTROL_PLANE = "enable_control_plane"
    ENABLE_HITL_ASYNC = "enable_hitl_async"
    ENABLE_MAKINA_FILTER = "enable_makina_filter"


_FLAGS = {
    FeatureFlag.ENABLE_CONTEXT_HARVESTER: True,
    FeatureFlag.ENABLE_REDUNDANCY_DETECTOR: True,
    FeatureFlag.ENABLE_CONTROL_PLANE: True,
    FeatureFlag.ENABLE_HITL_ASYNC: True,
    FeatureFlag.ENABLE_MAKINA_FILTER: True,
}


def get_flag(flag: FeatureFlag, default: Optional[Any] = None) -> Any:
    """Get a feature flag value."""
    return _FLAGS.get(flag, default)


def set_flag(flag: FeatureFlag, value: Any) -> None:
    """Set a feature flag value."""
    _FLAGS[flag] = value


def is_enabled(flag: FeatureFlag) -> bool:
    """Check if a feature flag is enabled."""
    return bool(_FLAGS.get(flag, False))
