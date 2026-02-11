"""Feature flags for DENIS_UNIFIED_V1_INCREMENTAL.

Phase-0 policy:
- Legacy remains default.
- New capabilities stay disabled until phase gates pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_mode(name: str, default: str, allowed: set[str]) -> str:
    raw = (os.getenv(name) or default).strip().lower()
    return raw if raw in allowed else default


@dataclass(frozen=True)
class UnifiedFeatureFlags:
    denis_use_quantum_substrate: bool = False
    denis_use_quantum_search: bool = False
    denis_use_cortex: bool = False
    denis_use_orchestration_aug: bool = False
    denis_use_api_unified: bool = False
    denis_use_inference_router: bool = False
    denis_use_voice_pipeline: bool = False
    denis_use_memory_unified: bool = False
    denis_use_atlas: bool = False
    denis_enable_metagraph: bool = True
    denis_autopoiesis_mode: str = "supervised"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_feature_flags() -> UnifiedFeatureFlags:
    return UnifiedFeatureFlags(
        denis_use_quantum_substrate=_env_bool(
            "DENIS_USE_QUANTUM_SUBSTRATE", False
        ),
        denis_use_quantum_search=_env_bool("DENIS_USE_QUANTUM_SEARCH", False),
        denis_use_cortex=_env_bool("DENIS_USE_CORTEX", False),
        denis_use_orchestration_aug=_env_bool("DENIS_USE_ORCHESTRATION_AUG", False),
        denis_use_api_unified=_env_bool("DENIS_USE_API_UNIFIED", False),
        denis_use_inference_router=_env_bool("DENIS_USE_INFERENCE_ROUTER", False),
        denis_use_voice_pipeline=_env_bool("DENIS_USE_VOICE_PIPELINE", False),
        denis_use_memory_unified=_env_bool("DENIS_USE_MEMORY_UNIFIED", False),
        denis_use_atlas=_env_bool("DENIS_USE_ATLAS", False),
        denis_enable_metagraph=_env_bool("DENIS_ENABLE_METAGRAPH", True),
        denis_autopoiesis_mode=_env_mode(
            "DENIS_AUTOPOIESIS_MODE", "supervised", {"off", "supervised", "manual"}
        ),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(load_feature_flags().as_dict(), indent=2, sort_keys=True))
