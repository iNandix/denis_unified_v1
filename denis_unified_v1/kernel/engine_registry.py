"""Engine registry: singleton source for engine_id to provider_key mapping."""

from denis_unified_v1.inference.provider_loader import discover_provider_models_cached
from denis_unified_v1.kernel.scheduler import InferenceEngine, Provider, ModelClass

_engine_registry: dict[str, dict] = {}

def get_engine_registry() -> dict[str, dict]:
    global _engine_registry
    if not _engine_registry:
        # Static engines (hardcoded for now, later from config)
        static_engines = [
            InferenceEngine(id="llamacpp_node2_1", name="llama-3.1-8b", provider=Provider.LLAMA_CPP, model_class=ModelClass.B_LOCAL, endpoint="http://10.10.10.2:8081", max_context=4096, cost_per_1k_tokens=0.001),
            InferenceEngine(id="groq_1", name="llama-3.1-8b-instant", provider=Provider.GROQ, model_class=ModelClass.D_CLOUD, endpoint="groq://api.groq.com/openai/v1", max_context=128000, cost_per_1k_tokens=0.05),
            # Add more static if needed, e.g. vllm, claude
        ]
        # Dynamic from harvester
        openrouter_models = discover_provider_models_cached("openrouter", ttl_s=300)
        for m in openrouter_models[:10]:  # Limit for now
            engine_id = f"openrouter_{m.model_id.replace('/', '_')}"
            static_engines.append(
                InferenceEngine(id=engine_id, name=m.model_name, provider=Provider.OPENROUTER, model_class=ModelClass.D_CLOUD, endpoint="openrouter://api.openrouter.ai/v1", max_context=m.context_length, cost_per_1k_tokens=m.pricing.get("completion", 0.001), tags=["harvester"])
            )
        
        for eng in static_engines:
            provider_key = {
                Provider.LLAMA_CPP: "llamacpp",
                Provider.GROQ: "groq",
                Provider.OPENROUTER: "openrouter",
                Provider.VLLM: "vllm",
            }.get(eng.provider, "unknown")
            tags = ["local"] if eng.provider == Provider.LLAMA_CPP else ["booster", "internet_required"]
            _engine_registry[eng.id] = {
                "provider_key": provider_key,
                "provider": eng.provider.value,
                "model": eng.name,
                "endpoint": eng.endpoint,
                "params_default": {"temperature": 0.2},
                "cost_factor": eng.cost_per_1k_tokens or 0.001,
                "max_context": eng.max_context,
                "tags": tags,
            }
    return _engine_registry

def resolve_engine(engine_id: str) -> dict | None:
    return get_engine_registry().get(engine_id)
