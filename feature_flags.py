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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except:
        return default


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
    denis_use_inference_router: bool = True
    denis_use_voice_pipeline: bool = False
    denis_use_memory_unified: bool = True
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

    # Fase 7: Self-Aware Inference Router
    phase7_hedged_requests_enabled: bool = True
    phase7_bandit_enabled: bool = True
    phase7_router_shadow_mode: bool = True
    phase7_router_budget_ms: int = 1200
    phase7_max_parallel_candidates: int = 2

    # Fase 8: Voice Pipeline
    phase8_voice_store_audio: bool = False
    phase8_stt_backend: str = "faster-whisper"
    phase8_tts_backend: str = "piper"
    phase8_voice_streaming_enabled: bool = True

    # Fase 9: Unified Memory
    phase9_memory_write_enabled: bool = True
    phase9_memory_read_enabled: bool = True
    phase9_memory_consolidation_enabled: bool = True
    phase9_memory_retention_days: int = 30
    phase9_memory_pii_redaction: bool = True

    # Fase 10: Gate Hardening (Inference & Tools Sandbox)
    denis_use_gate_hardening: bool = False
    phase10_budget_total_ms: int = 4500
    phase10_budget_ttft_ms: int = 900
    phase10_max_output_tokens: int = 512
    phase10_max_prompt_chars: int = 12000
    phase10_rate_limit_rps: int = 8
    phase10_rate_limit_burst: int = 16
    phase10_sandbox_enabled: bool = True
    phase10_strict_output_schema: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_feature_flags() -> UnifiedFeatureFlags:
    return UnifiedFeatureFlags(
        denis_use_quantum_substrate=_env_bool("DENIS_USE_QUANTUM_SUBSTRATE", False),
        denis_use_quantum_search=_env_bool("DENIS_USE_QUANTUM_SEARCH", False),
        denis_use_cortex=_env_bool("DENIS_USE_CORTEX", False),
        denis_use_orchestration_aug=_env_bool("DENIS_USE_ORCHESTRATION_AUG", False),
        denis_use_api_unified=_env_bool("DENIS_USE_API_UNIFIED", False),
        denis_use_inference_router=_env_bool("DENIS_USE_INFERENCE_ROUTER", True),
        denis_use_voice_pipeline=_env_bool("DENIS_USE_VOICE_PIPELINE", False),
        denis_use_memory_unified=_env_bool("DENIS_USE_MEMORY_UNIFIED", True),
        denis_use_atlas=_env_bool("DENIS_USE_ATLAS", False),
        denis_use_sprint_orchestrator=_env_bool("DENIS_USE_SPRINT_ORCHESTRATOR", False),
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
        phase3_active_metagraph_enabled=_env_bool(
            "PHASE3_ACTIVE_METAGRAPH_ENABLED", True
        ),
        phase5_cognitive_router_uses_graph=_env_bool(
            "PHASE5_COGNITIVE_ROUTER_USES_GRAPH", True
        ),
        # Fase 7: Self-Aware Inference Router
        phase7_hedged_requests_enabled=_env_bool(
            "PHASE7_HEDGED_REQUESTS_ENABLED", True
        ),
        phase7_bandit_enabled=_env_bool("PHASE7_BANDIT_ENABLED", True),
        phase7_router_shadow_mode=_env_bool("PHASE7_ROUTER_SHADOW_MODE", True),
        phase7_router_budget_ms=_env_int("PHASE7_ROUTER_BUDGET_MS", 1200),
        phase7_max_parallel_candidates=_env_int("PHASE7_MAX_PARALLEL_CANDIDATES", 2),
        # Fase 8: Voice Pipeline
        phase8_voice_store_audio=_env_bool("PHASE8_VOICE_STORE_AUDIO", False),
        phase8_stt_backend=_env_mode(
            "PHASE8_STT_BACKEND",
            "faster-whisper",
            {"faster-whisper", "whisper", "vosk"},
        ),
        phase8_tts_backend=_env_mode(
            "PHASE8_TTS_BACKEND", "piper", {"piper", "coqui", "gtts"}
        ),
        phase8_voice_streaming_enabled=_env_bool(
            "PHASE8_VOICE_STREAMING_ENABLED", True
        ),
        # Fase 9: Unified Memory
        phase9_memory_write_enabled=_env_bool("PHASE9_MEMORY_WRITE_ENABLED", True),
        phase9_memory_read_enabled=_env_bool("PHASE9_MEMORY_READ_ENABLED", True),
        phase9_memory_consolidation_enabled=_env_bool(
            "PHASE9_MEMORY_CONSOLIDATION_ENABLED", True
        ),
        phase9_memory_retention_days=_env_int("PHASE9_MEMORY_RETENTION_DAYS", 30),
        phase9_memory_pii_redaction=_env_bool("PHASE9_MEMORY_PII_REDACTION", True),
        # Fase 10: Gate Hardening
        denis_use_gate_hardening=_env_bool("DENIS_USE_GATE_HARDENING", False),
        phase10_budget_total_ms=_env_int("PHASE10_BUDGET_TOTAL_MS", 4500),
        phase10_budget_ttft_ms=_env_int("PHASE10_BUDGET_TTFT_MS", 900),
        phase10_max_output_tokens=_env_int("PHASE10_MAX_OUTPUT_TOKENS", 512),
        phase10_max_prompt_chars=_env_int("PHASE10_MAX_PROMPT_CHARS", 12000),
        phase10_rate_limit_rps=_env_int("PHASE10_RATE_LIMIT_RPS", 8),
        phase10_rate_limit_burst=_env_int("PHASE10_RATE_LIMIT_BURST", 16),
        phase10_sandbox_enabled=_env_bool("PHASE10_SANDBOX_ENABLED", True),
        phase10_strict_output_schema=_env_bool("PHASE10_STRICT_OUTPUT_SCHEMA", True),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(load_feature_flags().as_dict(), indent=2, sort_keys=True))
