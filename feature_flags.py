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
    denis_use_sprint_orchestrator: bool = False
    denis_use_rasa_gate: bool = False
    denis_enable_metagraph: bool = True
    denis_autopoiesis_mode: str = "supervised"
    # Fase 2: Unified V1 FastAPI Server (8085 compatible with 8084)
    unified_v1_8084_enabled: bool = True
    # Fase 12: SMX NLU Enrichment Layer
    phase12_smx_enabled: bool = False
    # Fase 3: SMX Local Integration
    use_smx_local: bool = False
    phase12_smx_fast_path: bool = True
    phase12_smx_safety_strict: bool = True
    phase12_smx_use_cortex: bool = True
    
    # Fase 0: Metacognitive Hooks
    phase0_hooks_enabled: bool = True
    
    # Fase 1: Metacognitive Perception
    phase1_perception_enabled: bool = True
    
    # Fase 3: Active Metagraph L1
    phase3_active_metagraph_enabled: bool = True
    
    # Fase 5: Cognitive Router con grafo
    phase5_cognitive_router_uses_graph: bool = True

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
        denis_use_sprint_orchestrator=_env_bool(
            "DENIS_USE_SPRINT_ORCHESTRATOR", False
        ),
        denis_use_rasa_gate=_env_bool("DENIS_USE_RASA_GATE", False),
        denis_enable_metagraph=_env_bool("DENIS_ENABLE_METAGRAPH", True),
        denis_autopoiesis_mode=_env_mode(
            "DENIS_AUTOPOIESIS_MODE", "supervised", {"off", "supervised", "manual"}
        ),
        # Fase 2: Unified V1 FastAPI Server
        unified_v1_8084_enabled=_env_bool("UNIFIED_V1_8084_ENABLED", True),
        # Fase 12: SMX
        phase12_smx_enabled=_env_bool("PHASE12_SMX_ENABLED", False),
        # Fase 3: SMX Local
        use_smx_local=_env_bool("USE_SMX_LOCAL", False),
        phase12_smx_fast_path=_env_bool("PHASE12_SMX_FAST_PATH", True),
        phase12_smx_safety_strict=_env_bool("PHASE12_SMX_SAFETY_STRICT", True),
        phase12_smx_use_cortex=_env_bool("PHASE12_SMX_USE_CORTEX", True),
        
        # Metacognitive Phases
        phase0_hooks_enabled=_env_bool("PHASE0_HOOKS_ENABLED", True),
        phase1_perception_enabled=_env_bool("PHASE1_PERCEPTION_ENABLED", True),
        phase3_active_metagraph_enabled=_env_bool("PHASE3_ACTIVE_METAGRAPH_ENABLED", True),
        phase5_cognitive_router_uses_graph=_env_bool("PHASE5_COGNITIVE_ROUTER_USES_GRAPH", True),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(load_feature_flags().as_dict(), indent=2, sort_keys=True))
