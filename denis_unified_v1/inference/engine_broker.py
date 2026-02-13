"""Engine Broker - filtrado, selección y ejecución de engines."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .engine_catalog import EngineCatalog, EngineSpec
from .policy_bandit import PolicyBandit
from .request_features import RequestFeatures
from .providers.smx_provider import create_smx_provider
from .providers.openai_compat_provider import (
    create_openai_provider,
)
from .advanced_routing import AdvancedRoutingManager, LoadBalancer, CircuitState
from .hedging import HedgingExecutor, AdaptiveHedgingPolicy, HedgedRequest
from denis_unified_v1.memory.backends import RedisBackend
from denis_unified_v1.observability.metrics import (
    inference_circuit_breaker_state,
    inference_circuit_breaker_failures,
    inference_hedging_decisions,
)


@dataclass
class RoutingDecision:
    engine_id: str
    candidate_scores: Dict[str, float]
    reason: str
    hedged_engine: Optional[str] = None
    shadow_mode: bool = False


@dataclass
class ExecutionResult:
    result: Any
    engine_id: str
    latency_ms: float
    success: bool


class EngineBroker:
    def __init__(self):
        self.catalog = EngineCatalog()
        self.policy = PolicyBandit()
        self._providers: Dict[str, Any] = {}

        # Advanced routing
        self.redis = RedisBackend()
        self.advanced_routing = AdvancedRoutingManager(self.redis)
        self.hedging_executor = HedgingExecutor()
        self.adaptive_hedging = AdaptiveHedgingPolicy()
        self.load_balancer = LoadBalancer()

        # Set capacities from catalog
        for engine in self.catalog.list_all():
            self.load_balancer.set_capacity(engine.id, 50)

    def _get_provider(self, engine_spec: EngineSpec):
        if engine_spec.id in self._providers:
            return self._providers[engine_spec.id]

        if engine_spec.provider == "smx":
            provider = create_smx_provider(engine_spec)
        elif engine_spec.provider == "openai_compat":
            provider = create_openai_provider(engine_spec)
        else:
            provider = create_smx_provider(engine_spec)

        self._providers[engine_spec.id] = provider
        return provider

    async def filter_candidates(
        self,
        features: RequestFeatures,
        required_capability: Optional[str] = None,
    ) -> List[tuple[str, EngineSpec]]:
        candidates = []

        for engine in self.catalog.list_all():
            if required_capability and not engine.supports(required_capability):
                continue

            if features.safety_risk_hint and engine.safety_level == "low":
                continue

            if (
                features.ops_intent
                and "code" in engine.capabilities
                and "chat" not in engine.capabilities
            ):
                continue

            provider = self._get_provider(engine)
            try:
                is_healthy = await provider.health()
            except Exception:
                is_healthy = False

            if is_healthy or not required_capability:
                candidates.append((engine.id, engine))

        return candidates

    async def route(
        self,
        features: RequestFeatures,
        shadow_mode: bool = False,
        required_capability: str = "chat",
    ) -> RoutingDecision:
        start_time = time.time()

        # === ADVANCED NLU ROUTING ===

        # High urgency → use fastest engine
        if features.urgency_level >= 3:
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                # Prioritize smx_fast_check for urgent requests
                for eid, eng in candidates:
                    if "fast" in eid:
                        return RoutingDecision(
                            engine_id=eid,
                            candidate_scores={eid: 1.0},
                            reason="urgent_high_priority",
                            shadow_mode=shadow_mode,
                        )
                # Fallback to first available
                return RoutingDecision(
                    engine_id=candidates[0][0],
                    candidate_scores={candidates[0][0]: 1.0},
                    reason="urgent_fallback",
                    shadow_mode=shadow_mode,
                )

        # Irony or sarcasm detected → use empathetic engine with emotional intelligence
        if features.has_irony or features.has_sarcasm:
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                # Use smx_macro for emotional nuance
                for eid, eng in candidates:
                    if "macro" in eid:
                        return RoutingDecision(
                            engine_id=eid,
                            candidate_scores={eid: 1.0},
                            reason="irony_sarcasm_empathetic",
                            shadow_mode=shadow_mode,
                        )
                return RoutingDecision(
                    engine_id=candidates[0][0],
                    candidate_scores={candidates[0][0]: 1.0},
                    reason="irony_sarcasm_fallback",
                    shadow_mode=shadow_mode,
                )

        # High ambiguity → use engine with better context understanding
        if features.ambiguity_level >= 2:
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                for eid, eng in candidates:
                    if "macro" in eid or "intent" in eid:
                        return RoutingDecision(
                            engine_id=eid,
                            candidate_scores={eid: 1.0},
                            reason="ambiguous_needs_context",
                            shadow_mode=shadow_mode,
                        )

        # Serious tone + negative sentiment → might need careful handling
        if features.tone == "serious" and features.emotional_valence == "negative":
            candidates = await self.filter_candidates(features, "safety")
            if candidates:
                return RoutingDecision(
                    engine_id=candidates[0][0],
                    candidate_scores={candidates[0][0]: 1.0},
                    reason="serious_negative_needs_safety",
                    shadow_mode=shadow_mode,
                )

        # Formal tone → use more precise engine
        if features.tone == "formal" and features.requires_precision:
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                for eid, eng in candidates:
                    if "response" in eid:  # smx_response is more precise
                        return RoutingDecision(
                            engine_id=eid,
                            candidate_scores={eid: 1.0},
                            reason="formal_requires_precision",
                            shadow_mode=shadow_mode,
                        )

        # Relaxed tone → can use more creative engine
        if features.tone == "relaxed":
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                for eid, eng in candidates:
                    if "macro" in eid:  # More conversational
                        return RoutingDecision(
                            engine_id=eid,
                            candidate_scores={eid: 1.0},
                            reason="relaxed_tone_casual",
                            shadow_mode=shadow_mode,
                        )

        # === BASIC ROUTING ===

        if features.is_short_utterance or features.streaming_requested:
            candidates = await self.filter_candidates(features, "chat")
            if candidates:
                best = candidates[0]
                return RoutingDecision(
                    engine_id=best[0],
                    candidate_scores={best[0]: 1.0},
                    reason="short_utterance_fast_path",
                    shadow_mode=shadow_mode,
                )

        if features.has_code_markers:
            candidates = await self.filter_candidates(features, "code")
            if candidates:
                engine_id, engine_spec = candidates[0]
                return RoutingDecision(
                    engine_id=engine_id,
                    candidate_scores={engine_id: 1.0},
                    reason="code_intent",
                    shadow_mode=shadow_mode,
                )

        if features.safety_risk_hint:
            candidates = await self.filter_candidates(features, "safety")
            if not candidates:
                candidates = await self.filter_candidates(features, "chat")
            if candidates:
                engine_id, engine_spec = candidates[0]
                return RoutingDecision(
                    engine_id=engine_id,
                    candidate_scores={engine_id: 1.0},
                    reason="safety_risk_force_safe",
                    shadow_mode=shadow_mode,
                )

        candidates = await self.filter_candidates(features, required_capability)

        if not candidates:
            return RoutingDecision(
                engine_id="smx_response",
                candidate_scores={},
                reason="fallback_default",
                shadow_mode=shadow_mode,
            )

        # Apply advanced routing policies (circuit breaker, A/B, load balancing)
        candidate_ids = [c[0] for c in candidates]
        filtered_ids = await self.advanced_routing.apply_routing_policies(
            candidate_ids,
            user_id=features.user_id,
            class_key=features.class_key,
        )

        # Re-filter candidates based on advanced routing
        candidates = [(eid, eng) for eid, eng in candidates if eid in filtered_ids]
        if not candidates:
            return RoutingDecision(
                engine_id=candidate_ids[0],
                candidate_scores={},
                reason="circuit_breaker_all_blocked",
                shadow_mode=shadow_mode,
            )

        chosen, scores = self.policy.choose(features.class_key, candidates, features)

        hedged = None
        if len(candidates) > 1 and features.is_short_utterance:
            hedged = candidates[1][0]

        elapsed_ms = (time.time() - start_time) * 1000
        reason = f"policy_chosen_{elapsed_ms:.0f}ms"

        return RoutingDecision(
            engine_id=chosen or candidates[0][0],
            candidate_scores=scores,
            reason=reason,
            hedged_engine=hedged,
            shadow_mode=shadow_mode,
        )

    async def execute(
        self,
        engine_id: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        hedge: bool = False,
        **kwargs,
    ) -> ExecutionResult:
        start = time.time()

        engine = self.catalog.get(engine_id)
        if not engine:
            return ExecutionResult(
                result={"error": f"Unknown engine {engine_id}"},
                engine_id=engine_id,
                latency_ms=0,
                success=False,
            )

        # Check circuit breaker
        cb = self.advanced_routing.get_circuit_breaker(engine_id)
        if not cb.can_attempt():
            # Record circuit breaker state
            inference_circuit_breaker_state.labels(engine_id=engine_id).set(1)  # OPEN
            return ExecutionResult(
                result={"error": "circuit_breaker_open"},
                engine_id=engine_id,
                latency_ms=0,
                success=False,
            )

        # Acquire load balancer slot
        if not self.load_balancer.acquire(engine_id):
            return ExecutionResult(
                result={"error": "load_balancer_rejected"},
                engine_id=engine_id,
                latency_ms=0,
                success=False,
            )

        provider = self._get_provider(engine)

        try:
            result = await provider.chat(messages, stream=stream, **kwargs)
            latency = (time.time() - start) * 1000

            # Record success for circuit breaker and adaptive hedging
            cb.record_success()
            self.adaptive_hedging.update_stats(engine_id, latency, True)
            self.advanced_routing.record_execution_result(engine_id, True, latency)

            # Update circuit breaker metrics
            state_map = {"closed": 0, "open": 1, "half_open": 2}
            inference_circuit_breaker_state.labels(engine_id=engine_id).set(
                state_map.get(cb.state.value, 0)
            )

            return ExecutionResult(
                result=result,
                engine_id=engine_id,
                latency_ms=latency,
                success=True,
            )
        except Exception as e:
            latency = (time.time() - start) * 1000

            # Record failure
            cb.record_failure()
            self.adaptive_hedging.update_stats(engine_id, latency, False)
            self.advanced_routing.record_execution_result(engine_id, False, latency)

            # Record failure metric
            inference_circuit_breaker_failures.labels(engine_id=engine_id).inc()
            state_map = {"closed": 0, "open": 1, "half_open": 2}
            inference_circuit_breaker_state.labels(engine_id=engine_id).set(
                state_map.get(cb.state.value, 0)
            )

            return ExecutionResult(
                result={"error": str(e)},
                engine_id=engine_id,
                latency_ms=latency,
                success=False,
            )

    async def execute_hedged(
        self,
        primary_engine: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        **kwargs,
    ) -> ExecutionResult:
        """Execute with hedging (parallel backup engines)."""
        # Get available backup engines
        all_engines = [e.id for e in self.catalog.list_all()]
        backups = [e for e in all_engines if e != primary_engine]

        if not backups:
            return await self.execute(primary_engine, messages, stream, **kwargs)

        # Check if we should hedge
        if not self.adaptive_hedging.should_hedge(primary_engine, ""):
            return await self.execute(primary_engine, messages, stream, **kwargs)

        # Get hedge config
        hedge_config = self.adaptive_hedging.get_hedge_config(
            primary_engine, all_engines
        )
        if not hedge_config:
            return await self.execute(primary_engine, messages, stream, **kwargs)

        # Execute hedged
        hedge_config.primary_engine = primary_engine

        async def exec_fn(engine_id: str, messages: List, stream: bool = False, **kw):
            return await self.execute(engine_id, messages, stream, **kw)

        hedged_result = await self.hedging_executor.execute_hedged(
            hedge_config=hedge_config,
            execute_fn=exec_fn,
            messages=messages,
            stream=stream,
            **kwargs,
        )

        return ExecutionResult(
            result=hedged_result.result,
            engine_id=hedged_result.winner_engine,
            latency_ms=hedged_result.latency_ms,
            success=True,
        )


def get_engine_broker() -> EngineBroker:
    return EngineBroker()
