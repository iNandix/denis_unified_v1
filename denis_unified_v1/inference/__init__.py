"""Inference module.

Keep this package import fail-open.

Some inference components have optional dependencies (redis/memory backends, etc).
Importing `denis_unified_v1.inference.*` submodules should not fail just because a
non-critical optional backend isn't present.
"""

from __future__ import annotations

__all__: list[str] = []

try:
    from .engine_catalog import EngineCatalog, EngineSpec, get_engine_catalog

    __all__ += ["EngineCatalog", "EngineSpec", "get_engine_catalog"]
except Exception:  # pragma: no cover
    pass

try:
    from .engine_broker import EngineBroker, get_engine_broker

    __all__ += ["EngineBroker", "get_engine_broker"]
except Exception:  # pragma: no cover
    pass

try:
    from .router_v2 import InferenceRouterV2, create_inference_router

    __all__ += ["InferenceRouterV2", "create_inference_router"]
except Exception:  # pragma: no cover
    pass

try:
    from .policy_bandit import PolicyBandit, get_policy_bandit

    __all__ += ["PolicyBandit", "get_policy_bandit"]
except Exception:  # pragma: no cover
    pass

try:
    from .request_features import RequestFeatures, extract_request_features

    __all__ += ["RequestFeatures", "extract_request_features"]
except Exception:  # pragma: no cover
    pass

try:
    from .health_manager import HealthManager, get_health_manager

    __all__ += ["HealthManager", "get_health_manager"]
except Exception:  # pragma: no cover
    pass

try:
    from .makina_filter import filter_input, filter_input_safe, MakinaOutput

    __all__ += ["filter_input", "filter_input_safe", "MakinaOutput"]
except Exception:  # pragma: no cover
    pass

try:
    from .compiler_service import (
        compile,
        compile_with_fallback,
        compile_with_llm,
        CompilerInput,
        CompilerOutput,
    )

    __all__ += [
        "compile",
        "compile_with_fallback",
        "compile_with_llm",
        "CompilerInput",
        "CompilerOutput",
    ]
except Exception:  # pragma: no cover
    pass
