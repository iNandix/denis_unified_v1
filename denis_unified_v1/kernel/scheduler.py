"""
Denis Kernel - Model Scheduler
==============================
Manages 8 inference engines with class-based assignment.

Engines:
- 2x llama.cpp medianos (3080 GTX, node1) -> Class B
- 4x pequeños (1050Ti, node2) -> Class A
- Harvester (OpenRouter pool) -> Class D
- 2x Groq (low latency) -> Class A

Routes:
- FAST_TALK: Class A/B (1 model)
- TOOL: Class A/B (0-1 model)
- PROJECT: Class B/C (S1) + Class D (S2-S4 parallel)
- VERIFY: Class B/D (1 model)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from denis_unified_v1.inference.provider_loader import discover_provider_models_cached
from denis_unified_v1.kernel.internet_health import get_internet_health

logger = logging.getLogger(__name__)


class ModelClass(Enum):
    """Model class by capability."""

    A_TTFT = "a"  # Fast, small models (1050Ti small, Groq)
    B_LOCAL = "b"  # General local (3080 llama.cpp medianos)
    C_PLANNER = "c"  # Best for planning/code (3080 best)
    D_CLOUD = "d"  # Cloud burst (OpenRouter harvester)


class Provider(Enum):
    """Inference provider."""

    LLAMA_CPP = "llama_cpp"  # Local llama.cpp
    GROQ = "groq"  # Groq API
    OPENROUTER = "openrouter"  # OpenRouter harvester
    VLLM = "vllm"  # vLLM server


@dataclass
class InferenceEngine:
    """An inference engine definition."""

    id: str
    name: str
    provider: Provider
    model_class: ModelClass
    endpoint: str
    max_context: int = 4096
    max_output: int = 2048
    priority: int = 10  # Lower = higher preference
    available: bool = True
    current_load: int = 0  # Active requests
    quota_remaining: Optional[float] = None  # For cloud providers
    tags: List[str] = field(default_factory=list)
    cost_per_1k_tokens: Optional[float] = None

    @property
    def is_available(self) -> bool:
        return self.available and self.current_load < 3  # Max 3 parallel


@dataclass
class InferenceRequest:
    """An inference request."""

    request_id: str
    session_id: str
    route_type: str
    task_type: str  # "chat", "tool_selection", "planning", "code", "review"
    payload: Dict[str, Any]
    preferred_class: Optional[ModelClass] = None
    max_latency_ms: Optional[float] = None
    max_cost: Optional[float] = None
    cancel_key: Optional[str] = None


@dataclass
class InferenceAssignment:
    """Result of model scheduling."""

    request_id: str
    engine_id: str
    model_name: str
    endpoint: str
    estimated_latency_ms: float
    estimated_cost: Optional[float] = None


@dataclass(frozen=True)
class InferencePlan:
    primary_engine_id: str                 # "groq_1" | "openrouter_free_xyz" | "llamacpp_node2_1"
    fallback_engine_ids: List[str] = field(default_factory=list)

    # "Expectation" (útil para auditoría y tests de integridad)
    expected_model: Optional[str] = None   # "llama-3.1-8b-instant" (si quieres detectar drift)

    # Runtime controls
    params: Dict[str, Any] = field(default_factory=dict)      # {"temperature":0.7,"max_tokens":512}
    timeouts_ms: Dict[str, int] = field(default_factory=dict) # {"connect_ms":200,"total_ms":5000}

    # Budget / policy signals (scheduler authority)
    budget: Dict[str, Any] = field(default_factory=dict)      # {"planned_tokens":512,"planned_cost":0.0004}
    trace_tags: Dict[str, Any] = field(default_factory=dict)  # {"policy_mode": "local_first", "internet_status": "OK"}

    attempt_policy: Dict[str, Any] = field(default_factory=lambda: {
        "max_attempts": 1 + 3,            # primary + 3 fallbacks default
        "retry_on": ["timeout", "5xx"],   # router only retries on these
    })


class ModelScheduler:
    """
    Model scheduler with class-based assignment.

    Rules:
    - FAST_TALK: 1x Class A or B
    - TOOL: 0-1x Class A or B
    - PROJECT: 1x Class B/C (S1) + up to 3x Class D (S2-S4)
    - VERIFY: 1x Class B or D
    """

    # Limits per route
    MAX_PARALLEL_FAST = 1
    MAX_PARALLEL_TOOL = 1
    MAX_PARALLEL_PROJECT = 4
    MAX_PARALLEL_VERIFY = 1

    # Class preference by route
    ROUTE_CLASS_PREFERENCE = {
        "fast_talk": [ModelClass.A_TTFT, ModelClass.B_LOCAL],
        "tool": [ModelClass.A_TTFT, ModelClass.B_LOCAL],
        "project": [ModelClass.C_PLANNER, ModelClass.B_LOCAL, ModelClass.D_CLOUD],
        "deliberate": [ModelClass.C_PLANNER, ModelClass.B_LOCAL, ModelClass.D_CLOUD],
        "toolchain": [ModelClass.C_PLANNER, ModelClass.B_LOCAL, ModelClass.D_CLOUD],
        "verify": [ModelClass.B_LOCAL, ModelClass.D_CLOUD],
        "safe": [ModelClass.A_TTFT, ModelClass.B_LOCAL],
    }

    def __init__(self):
        self._engines: Dict[str, InferenceEngine] = {}
        self._active_requests: Dict[str, InferenceAssignment] = {}
        self._setup_default_engines()

    def _setup_default_engines(self):
        """Setup the inference engines with dynamic catalog."""

        # Static local engines
        static_engines = [
            # Class A: Fast/Small (1050Ti small + Groq)
            InferenceEngine(
                id="llama_1050_1",
                name="llama-3.2-1b",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.A_TTFT,
                endpoint="http://10.10.10.2:8081",
                max_context=2048,
                max_output=1024,
                priority=15,
                tags=["small", "fast", "node2", "local"],
            ),
            InferenceEngine(
                id="llama_1050_2",
                name="qwen-0.5b",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.A_TTFT,
                endpoint="http://10.10.10.2:8082",
                max_context=2048,
                max_output=1024,
                priority=15,
                tags=["small", "fast", "node2", "local"],
            ),
            InferenceEngine(
                id="llama_1050_3",
                name="phi-3-mini",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.A_TTFT,
                endpoint="http://10.10.10.2:8083",
                max_context=4096,
                max_output=1024,
                priority=15,
                tags=["small", "fast", "node2", "local"],
            ),
            InferenceEngine(
                id="llama_1050_4",
                name="tinyllama",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.A_TTFT,
                endpoint="http://10.10.10.2:8084",
                max_context=2048,
                max_output=512,
                priority=20,
                tags=["tiny", "fast", "node2", "local"],
            ),
            # Groq (low latency "hola" responses)
            InferenceEngine(
                id="groq_1",
                name="llama-3.1-8b-instant",
                provider=Provider.GROQ,
                model_class=ModelClass.A_TTFT,
                endpoint="groq://api.groq.com/openai/v1",
                max_context=8192,
                max_output=4096,
                priority=5,  # Very fast
                quota_remaining=100.0,  # $100 budget
                cost_per_1k_tokens=0.0004,
                tags=["cloud", "fast", "low_latency", "internet_required"],
            ),
            InferenceEngine(
                id="groq_2",
                name="mixtral-8x7b-32768",
                provider=Provider.GROQ,
                model_class=ModelClass.A_TTFT,
                endpoint="groq://api.groq.com/openai/v1",
                max_context=32768,
                max_output=4096,
                priority=5,
                quota_remaining=100.0,
                cost_per_1k_tokens=0.0007,
                tags=["cloud", "fast", "large_context", "internet_required"],
            ),
            # Class B: General local (3080 GTX medianos)
            InferenceEngine(
                id="llama_3080_1",
                name="llama-3.1-8b",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.B_LOCAL,
                endpoint="http://10.10.10.1:8081",
                max_context=8192,
                max_output=2048,
                priority=10,
                tags=["medium", "general", "node1", "local"],
            ),
            InferenceEngine(
                id="llama_3080_2",
                name="qwen-7b",
                provider=Provider.LLAMA_CPP,
                model_class=ModelClass.B_LOCAL,
                endpoint="http://10.10.10.1:8082",
                max_context=8192,
                max_output=2048,
                priority=10,
                tags=["medium", "general", "node1", "local"],
            ),
        ]

        # Dynamic from harvester
        dynamic_engines = []
        try:
            openrouter_models = discover_provider_models_cached("openrouter")
            for m in openrouter_models[:5]:  # Limit to top 5 free
                dynamic_engines.append(InferenceEngine(
                    id=f"openrouter_{m.model_id.replace('/', '_')}",
                    name=m.model_name,
                    provider=Provider.OPENROUTER,
                    model_class=ModelClass.D_CLOUD,
                    endpoint="openrouter://api.openrouter.ai/v1",
                    max_context=m.context_length,
                    cost_per_1k_tokens=m.pricing.get("completion", 0.001),
                    tags=["harvester", "free", "internet_required"],
                ))
        except Exception:
            pass  # Degrade to static

        all_engines = static_engines + dynamic_engines
        for eng in all_engines:
            self._engines[eng.id] = eng

        logger.info(f"ModelScheduler initialized with {len(self._engines)} engines")

    def get_engine(self, engine_id: str) -> Optional[InferenceEngine]:
        """Get engine by ID."""
        return self._engines.get(engine_id)

    def get_available_engines(
        self, model_class: Optional[ModelClass] = None
    ) -> List[InferenceEngine]:
        """Get available engines, optionally filtered by class."""
        engines = [e for e in self._engines.values() if e.is_available]
        if model_class:
            engines = [e for e in engines if e.model_class == model_class]
        return sorted(engines, key=lambda e: e.priority)

    def get_engines_by_class(self, model_class: ModelClass) -> List[InferenceEngine]:
        """Get all engines of a specific class."""
        return [e for e in self._engines.values() if e.model_class == model_class]

    def get_parallel_limit(self, route_type: str) -> int:
        """Get max parallel models for a route."""
        limits = {
            "fast_talk": self.MAX_PARALLEL_FAST,
            "tool": self.MAX_PARALLEL_TOOL,
            "project": self.MAX_PARALLEL_PROJECT,
            "deliberate": self.MAX_PARALLEL_PROJECT,
            "toolchain": self.MAX_PARALLEL_PROJECT,
            "verify": self.MAX_PARALLEL_VERIFY,
            "safe": self.MAX_PARALLEL_FAST,
        }
        return limits.get(route_type, 1)

    def get_current_load(self, route_type: str) -> int:
        """Get current parallel load for a route."""
        return sum(
            1
            for a in self._active_requests.values()
            if self._engines.get(a.engine_id)
            and self._engines[a.engine_id].provider != Provider.OPENROUTER
        )

    def can_schedule(self, route_type: str) -> bool:
        """Check if we can schedule more for this route."""
        current = self.get_current_load(route_type)
        limit = self.get_parallel_limit(route_type)
        return current < limit

    def assign(
        self,
        request: InferenceRequest,
        slot: int = 0,  # 0 = S1 (primary), 1-3 = S2-S4 (workers)
    ) -> Optional[InferencePlan]:
        """
        Assign an engine to a request using local-first policy.

        Returns InferencePlan or None if can't schedule
        """
        if not self.can_schedule(request.route_type):
            logger.warning(f"Cannot schedule {request.route_type}: at parallel limit")
            return None

        # Internet health
        internet_status = get_internet_health().check()
        internet_ok = internet_status == "OK"

        # Classify engines
        local_engines = [e for e in self._engines.values() if e.is_available and "local" in e.tags]
        booster_engines = [e for e in self._engines.values() if e.is_available and "internet_required" in e.tags]

        # Local-first selection
        degraded = False
        if local_engines:
            # Primary: best local
            primary = sorted(local_engines, key=lambda e: e.priority)[0]
            # Fallbacks: other locals + boosters if internet OK
            fallbacks = sorted(local_engines, key=lambda e: e.priority)[1:]
            if internet_ok:
                fallbacks += sorted(booster_engines, key=lambda e: e.priority)
        else:
            # No locals: use boosters as degraded if internet OK
            if internet_ok and booster_engines:
                primary = sorted(booster_engines, key=lambda e: e.priority)[0]
                fallbacks = sorted(booster_engines, key=lambda e: e.priority)[1:]
                degraded = True
            else:
                primary = None
                fallbacks = []

        if not primary:
            return None

        # Track load
        primary.current_load += 1
        self._active_requests[request.request_id] = InferenceAssignment(
            request_id=request.request_id,
            engine_id=primary.id,
            model_name=primary.name,
            endpoint=primary.endpoint,
            estimated_latency_ms=self._estimate_latency(primary, request),
            estimated_cost=self._estimate_cost(primary, request),
        )

        # Build InferencePlan
        planned_tokens = min(request.payload.get("max_tokens", 512), primary.max_context - 100)
        planned_cost = (planned_tokens / 1000) * (primary.cost_per_1k_tokens or 0.0001)

        trace_tags = {
            "policy_mode": "local_first",
            "internet_status_at_plan": internet_status,
            "degraded": degraded,
        }

        plan = InferencePlan(
            primary_engine_id=primary.id,
            expected_model=primary.name,
            params={
                "temperature": request.payload.get("temperature", 0.7),
                "max_tokens": request.payload.get("max_tokens", 512),
            },
            timeouts_ms={"connect_ms": 200, "total_ms": 5000},
            budget={"planned_tokens": planned_tokens, "planned_cost": planned_cost},
            fallback_engine_ids=[e.id for e in fallbacks],
            trace_tags=trace_tags,
        )

        logger.info(
            f"Assigned {primary.name} (local_first, degraded={degraded}) to {request.request_id}"
        )
        return plan

    def release(self, request_id: str):
        """Release an assignment after completion."""
        assignment = self._active_requests.pop(request_id, None)
        if assignment:
            engine = self._engines.get(assignment.engine_id)
            if engine and engine.current_load > 0:
                engine.current_load -= 1
            logger.debug(f"Released {assignment.engine_id}")

    def _estimate_latency(
        self, engine: InferenceEngine, request: InferenceRequest
    ) -> float:
        """Estimate latency for an engine."""
        base_latency = {
            Provider.LLAMA_CPP: 50,  # Local fast
            Provider.GROQ: 150,  # Cloud fast
            Provider.OPENROUTER: 800,  # Cloud variable
            Provider.VLLM: 100,
        }.get(engine.provider, 200)

        # Adjust by model class
        multiplier = {
            ModelClass.A_TTFT: 0.5,
            ModelClass.B_LOCAL: 1.0,
            ModelClass.C_PLANNER: 1.5,
            ModelClass.D_CLOUD: 2.0,
        }.get(engine.model_class, 1.0)

        return base_latency * multiplier

    def _estimate_cost(
        self, engine: InferenceEngine, request: InferenceRequest
    ) -> Optional[float]:
        """Estimate cost for an engine."""
        if engine.cost_per_1k_tokens is None:
            return None

        tokens = request.payload.get("max_tokens", 1024)
        return (tokens / 1000) * engine.cost_per_1k_tokens

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        stats = {
            "total_engines": len(self._engines),
            "available_engines": len(self.get_available_engines()),
            "active_requests": len(self._active_requests),
            "by_class": {},
            "by_provider": {},
        }

        for model_class in ModelClass:
            engines = self.get_engines_by_class(model_class)
            stats["by_class"][model_class.value] = {
                "count": len(engines),
                "available": len([e for e in engines if e.is_available]),
                "load": sum(e.current_load for e in engines),
            }

        for provider in Provider:
            engines = [e for e in self._engines.values() if e.provider == provider]
            stats["by_provider"][provider.value] = {
                "count": len(engines),
                "available": len([e for e in engines if e.is_available]),
                "load": sum(e.current_load for e in engines),
            }

        return stats


# Global scheduler
_model_scheduler: Optional[ModelScheduler] = None


def get_model_scheduler() -> ModelScheduler:
    """Get the global model scheduler."""
    global _model_scheduler
    if _model_scheduler is None:
        _model_scheduler = ModelScheduler()
    return _model_scheduler
