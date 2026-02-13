"""
Unified Inference Engine - Production version
Integrates with provider_loader and InferenceRouter for 4-specialty inference
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import sys
from pathlib import Path

# Configure paths
base_dir = Path(__file__).parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from inference.router import InferenceRouter, RedisMetricsStore, QueryProfile
from inference.provider_loader import (
    DiscoveredModel,
    discover_provider_models,
    ProviderLoadRegistry,
)
from sprint_orchestrator.model_adapter import (
    build_provider_request,
    invoke_provider_request,
    parse_provider_response,
)
from sprint_orchestrator.config import SprintOrchestratorConfig
from sprint_orchestrator.providers import load_provider_statuses

logger = logging.getLogger(__name__)


class Specialty(Enum):
    """4 specialties for model classification"""

    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    DEVOPS = "devops"


@dataclass
class ModelSlot:
    """Model slot assigned to a specialty"""

    specialty: Specialty
    current_model: str  # model_id
    provider: str
    confidence: float
    last_rotation: datetime
    calls_count: int = 0
    errors_count: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class RateLimitStatus:
    """Rate limit status for a model"""

    model_id: str
    provider: str
    remaining: int
    reset_time: datetime
    last_request: datetime
    requests_this_minute: int = 0
    requests_this_hour: int = 0


@dataclass
class BridgeRequest:
    """Normalized request for the bridge"""

    messages: List[Dict[str, str]]
    specialty: Optional[Specialty] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    tools: Optional[List[Dict]] = None
    response_format: Optional[Dict] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgeResponse:
    """Normalized response from the bridge"""

    content: str
    model_used: str
    provider: str
    specialty: Optional[Specialty]
    latency_ms: float
    tokens_used: int
    cached: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RateLimitManager:
    """Manages rate limits per model and provider"""

    def __init__(self):
        self.limits: Dict[str, RateLimitStatus] = {}
        self._lock = asyncio.Lock()

    async def check_limit(self, model_id: str, provider: str) -> Tuple[bool, int]:
        """Check if request is allowed. Returns: (allowed, remaining)"""
        async with self._lock:
            key = f"{provider}:{model_id}"
            status = self.limits.get(key)

            if not status:
                return True, 100

            now = datetime.now()

            # Reset counters if time has passed
            if now > status.reset_time:
                status.requests_this_minute = 0
                status.requests_this_hour = 0

            # Check limits (estimated)
            if status.requests_this_minute >= 20:  # RPM estimated
                return False, 0

            if status.requests_this_hour >= 1000:  # RPH estimated
                return False, 0

            remaining = max(0, 20 - status.requests_this_minute)
            return True, remaining

    async def record_request(self, model_id: str, provider: str):
        """Record a request and update limits"""
        async with self._lock:
            key = f"{provider}:{model_id}"
            now = datetime.now()

            if key not in self.limits:
                self.limits[key] = RateLimitStatus(
                    model_id=model_id,
                    provider=provider,
                    remaining=100,
                    reset_time=now + timedelta(minutes=1),
                    last_request=now,
                )

            status = self.limits[key]
            status.last_request = now
            status.requests_this_minute += 1
            status.requests_this_hour += 1

    def get_status(self) -> Dict[str, Any]:
        """Get all rate limit status"""
        return {
            key: {
                "model": status.model_id,
                "provider": status.provider,
                "remaining": status.remaining,
                "rpm": status.requests_this_minute,
                "rph": status.requests_this_hour,
            }
            for key, status in self.limits.items()
        }


class DynamicModelSelector:
    """Dynamic model selector with automatic rotation"""

    def __init__(
        self,
        registry: ProviderLoadRegistry,
        rate_limit_manager: RateLimitManager,
        rotation_interval: int = 300,  # 5 minutes
    ):
        self.registry = registry
        self.rate_limiter = rate_limit_manager
        self.rotation_interval = rotation_interval

        # Slots for each specialty
        self.slots: Dict[Specialty, ModelSlot] = {}

        # Model classifications cache
        self.classifications: Dict[str, Dict[Specialty, float]] = {}

        # Initialize slots
        self._initialize_slots()

    def _initialize_slots(self):
        """Initialize empty slots for each specialty"""
        for specialty in Specialty:
            self.slots[specialty] = ModelSlot(
                specialty=specialty,
                current_model="",
                provider="",
                confidence=0.0,
                last_rotation=datetime.now(),
            )

    def classify_model(self, model: DiscoveredModel) -> Dict[Specialty, float]:
        """Classify a model for the 4 specialties"""
        scores = {specialty: 0.0 for specialty in Specialty}

        model_name = model.model_name.lower()
        model_id = model.model_id.lower()
        tags = [t.lower() for t in model.tags]

        # ARCHITECT: Reasoning + long context
        if model.context_length >= 32000:
            scores[Specialty.ARCHITECT] += 4.0
        elif model.context_length >= 16000:
            scores[Specialty.ARCHITECT] += 3.0
        else:
            scores[Specialty.ARCHITECT] += 1.0

        if (
            "reasoning" in tags
            or "think" in model_id
            or "o1" in model_id
            or "qwq" in model_id
        ):
            scores[Specialty.ARCHITECT] += 4.0
        if "code" in tags:
            scores[Specialty.ARCHITECT] += 2.0
        if model.supports_tools:
            scores[Specialty.ARCHITECT] += 1.5

        # BACKEND: Code + tools + JSON
        if "code" in tags or "coder" in tags:
            scores[Specialty.BACKEND] += 5.0
        if "instruct" in tags:
            scores[Specialty.BACKEND] += 2.0
        if model.supports_tools:
            scores[Specialty.BACKEND] += 3.0
        if model.supports_json_mode:
            scores[Specialty.BACKEND] += 2.5
        if model.context_length >= 16000:
            scores[Specialty.BACKEND] += 1.5

        # FRONTEND: JSON + instruct + faster
        if model.supports_json_mode:
            scores[Specialty.FRONTEND] += 4.0
        if "instruct" in tags:
            scores[Specialty.FRONTEND] += 3.0
        if model.context_length >= 4096:
            scores[Specialty.FRONTEND] += 2.0
        if model.context_length <= 8192:  # Prefer faster models
            scores[Specialty.FRONTEND] += 1.5
        if "code" in tags:
            scores[Specialty.FRONTEND] += 1.0

        # DEVOPS: Tools + JSON + scripts
        if model.supports_tools:
            scores[Specialty.DEVOPS] += 4.0
        if model.supports_json_mode:
            scores[Specialty.DEVOPS] += 4.0
        if "instruct" in tags:
            scores[Specialty.DEVOPS] += 2.5
        if model.context_length >= 4096:
            scores[Specialty.DEVOPS] += 1.5

        # Size bonuses/penalties
        if "70b" in model_id or "large" in model_name:
            scores[Specialty.ARCHITECT] *= 1.2
            scores[Specialty.BACKEND] *= 1.2
        elif "7b" in model_id or "small" in model_name:
            scores[Specialty.FRONTEND] *= 1.15
            scores[Specialty.ARCHITECT] *= 0.85

        # Normalize to 0-10
        for key in scores:
            scores[key] = min(10.0, scores[key])

        self.classifications[model.model_id] = scores
        return scores

    async def select_model(
        self, specialty: Specialty, force_rotation: bool = False
    ) -> Optional[Tuple[str, str, float]]:
        """Select best model for a specialty"""

        slot = self.slots[specialty]
        time_since_rotation = (datetime.now() - slot.last_rotation).total_seconds()

        # Check if we need rotation
        if (
            not force_rotation
            and time_since_rotation < self.rotation_interval
            and slot.current_model
        ):
            allowed, remaining = await self.rate_limiter.check_limit(
                slot.current_model, slot.provider
            )
            if allowed and remaining > 5:
                logger.debug(
                    f"Using cached model for {specialty.value}: {slot.current_model}"
                )
                return slot.current_model, slot.provider, slot.confidence

        # Need to select new model
        logger.info(f"Selecting new model for {specialty.value}...")

        # Get all available free models
        all_models = []
        for provider_type in ["groq", "openrouter", "claude"]:
            try:
                total, models = discover_provider_models(
                    provider=provider_type,
                    api_key=os.getenv(f"{provider_type.upper()}_API_KEY", ""),
                )
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"Could not discover models for {provider_type}: {e}")

        if not all_models:
            logger.error(f"No available models for {specialty.value}")
            return None

        # Score models for this specialty
        candidates = []
        for model in all_models:
            if not model.is_free:
                continue

            # Check rate limit
            allowed, remaining = await self.rate_limiter.check_limit(
                model.model_id, model.provider
            )
            if not allowed or remaining < 3:
                continue

            # Classify model
            if model.model_id not in self.classifications:
                self.classify_model(model)

            scores = self.classifications[model.model_id]
            specialty_score = scores.get(specialty, 0.0)

            # Cache bonus (if model has been used recently - we'd need to track this)
            # For now, no cache bonus since we're using provider_loader without caching

            candidates.append((model, specialty_score, remaining))

        if not candidates:
            logger.error(f"No available models for {specialty.value} after filtering")
            return None

        # Select best model
        candidates.sort(key=lambda x: (-x[1], -x[2]))
        best_model, score, remaining = candidates[0]

        # Update slot
        slot.current_model = best_model.model_id
        slot.provider = best_model.provider
        slot.confidence = score
        slot.last_rotation = datetime.now()
        slot.calls_count = 0
        slot.errors_count = 0

        logger.info(
            f"Selected model for {specialty.value}: {best_model.model_id} "
            f"({best_model.provider}) with score {score:.2f}"
        )

        return best_model.model_id, best_model.provider, score

    def get_slot_info(self) -> Dict[str, Any]:
        """Get information about all slots"""
        return {
            specialty.value: {
                "model": slot.current_model,
                "provider": slot.provider,
                "confidence": slot.confidence,
                "last_rotation": slot.last_rotation.isoformat(),
                "calls": slot.calls_count,
                "errors": slot.errors_count,
                "avg_latency_ms": slot.avg_latency_ms,
            }
            for specialty, slot in self.slots.items()
        }


class UniversalLLMBridge:
    """Universal bridge for provider-agnostic LLM calls"""

    def __init__(
        self,
        selector: DynamicModelSelector,
        rate_limiter: RateLimitManager,
        config: SprintOrchestratorConfig,
    ):
        self.selector = selector
        self.rate_limiter = rate_limiter
        self.config = config

        # Load provider statuses
        self.provider_statuses = load_provider_statuses(config)
        self.provider_dict = {
            s.provider: s for s in self.provider_statuses if s.configured
        }

        # HTTP client
        import httpx

        self.http = httpx.AsyncClient(timeout=60.0)

    async def generate(self, request: BridgeRequest) -> BridgeResponse:
        """Generate response using the universal bridge"""

        start_time = time.time()

        # Detect specialty if not provided
        if not request.specialty:
            request.specialty = self._detect_specialty(request.messages)

        # Select model
        model_result = await self.selector.select_model(request.specialty)
        if not model_result:
            return BridgeResponse(
                content="",
                model_used="",
                provider="",
                specialty=request.specialty,
                latency_ms=0,
                tokens_used=0,
                error="No available models",
            )

        model_id, provider, confidence = model_result

        try:
            # Get provider status
            provider_status = self.provider_dict.get(provider)
            if not provider_status:
                raise ValueError(f"Provider {provider} not configured")

            # Build request using existing model_adapter
            messages = request.messages
            provider_req = build_provider_request(
                config=self.config,
                status=provider_status,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            # Invoke provider
            response = await asyncio.to_thread(
                invoke_provider_request, provider_req, timeout_sec=60.0
            )

            # Parse response
            normalized = parse_provider_response(provider_status, response["data"])

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Update slot
            slot = self.selector.slots[request.specialty]
            slot.calls_count += 1
            if slot.avg_latency_ms:
                slot.avg_latency_ms = 0.9 * slot.avg_latency_ms + 0.1 * latency_ms
            else:
                slot.avg_latency_ms = latency_ms

            # Record rate limit
            await self.rate_limiter.record_request(model_id, provider)

            # Extract content
            content = normalized.get("text", "")
            tokens_used = normalized.get("usage", {}).get("total_tokens", 0)

            return BridgeResponse(
                content=content,
                model_used=model_id,
                provider=provider,
                specialty=request.specialty,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                cached=False,
                metadata={"confidence": confidence, "raw_response": normalized},
            )

        except Exception as e:
            # Register error
            slot = self.selector.slots[request.specialty]
            slot.errors_count += 1

            logger.error(f"Bridge error for {provider}/{model_id}: {e}")

            # Force rotation and retry
            if slot.errors_count < 3:
                logger.info(f"Retrying with rotation for {request.specialty.value}...")
                return await self.generate(request)

            return BridgeResponse(
                content="",
                model_used=model_id,
                provider=provider,
                specialty=request.specialty,
                latency_ms=(time.time() - start_time) * 1000,
                tokens_used=0,
                error=str(e),
            )

    def _detect_specialty(self, messages: List[Dict[str, str]]) -> Specialty:
        """Detect specialty from message content"""
        text = " ".join(
            [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
        ).lower()

        # Keywords by specialty
        keywords = {
            Specialty.ARCHITECT: [
                "architecture",
                "design",
                "structure",
                "pattern",
                "diagram",
                "system",
                "component",
            ],
            Specialty.BACKEND: [
                "api",
                "endpoint",
                "database",
                "server",
                "logic",
                "model",
                "schema",
                "backend",
            ],
            Specialty.FRONTEND: [
                "ui",
                "ux",
                "component",
                "interface",
                "css",
                "html",
                "react",
                "vue",
                "frontend",
            ],
            Specialty.DEVOPS: [
                "docker",
                "deploy",
                "ci/cd",
                "pipeline",
                "kubernetes",
                "infra",
                "devops",
            ],
        }

        scores = {}
        for specialty, words in keywords.items():
            scores[specialty] = sum(1 for word in words if word in text)

        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else Specialty.ARCHITECT

    async def close(self):
        """Close HTTP client"""
        await self.http.aclose()


class UnifiedInferenceEngine:
    """Unified inference engine - main entry point"""

    def __init__(self, config: SprintOrchestratorConfig):
        self.config = config
        self.rate_limiter = RateLimitManager()
        self.registry = ProviderLoadRegistry()
        self.selector: Optional[DynamicModelSelector] = None
        self.bridge: Optional[UniversalLLMBridge] = None

        self.initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the complete engine"""
        async with self._lock:
            if self.initialized:
                return

            logger.info("Initializing Unified Inference Engine...")

            # Create selector
            self.selector = DynamicModelSelector(
                registry=self.registry, rate_limit_manager=self.rate_limiter
            )

            # Create bridge
            self.bridge = UniversalLLMBridge(
                selector=self.selector,
                rate_limit_manager=self.rate_limiter,
                config=self.config,
            )

            self.initialized = True
            logger.info("✅ Unified Inference Engine initialized")

    async def generate(
        self, messages: List[Dict[str, str]], specialty: Optional[str] = None, **kwargs
    ) -> BridgeResponse:
        """Generate response using the unified engine"""

        if not self.initialized:
            await self.initialize()

        # Convert specialty string to enum
        specialty_enum = None
        if specialty:
            try:
                specialty_enum = Specialty(specialty.lower())
            except:
                pass

        # Create request
        request = BridgeRequest(messages=messages, specialty=specialty_enum, **kwargs)

        # Generate
        return await self.bridge.generate(request)

    def get_status(self) -> Dict[str, Any]:
        """Get complete engine status"""
        return {
            "initialized": self.initialized,
            "slots": self.selector.get_slot_info() if self.selector else {},
            "rate_limits": self.rate_limiter.get_status(),
            "classifications_count": len(self.selector.classifications)
            if self.selector
            else 0,
        }

    async def close(self):
        """Close the engine"""
        if self.bridge:
            await self.bridge.close()


# Convenience function
async def get_engine(
    config: Optional[SprintOrchestratorConfig] = None,
) -> UnifiedInferenceEngine:
    """Get singleton engine instance"""
    if config is None:
        config = SprintOrchestratorConfig()

    engine = UnifiedInferenceEngine(config)
    await engine.initialize()
    return engine


if __name__ == "__main__":
    # Test with real API keys
    import asyncio

    async def test():
        # Load config
        config = SprintOrchestratorConfig()

        # Get engine
        engine = await get_engine(config)

        print("\n" + "=" * 60)
        print("UNIFIED INFERENCE ENGINE TEST")
        print("=" * 60)

        # Test each specialty
        test_cases = [
            ("Design a scalable microservices architecture", "architect"),
            ("Create a REST API endpoint for user authentication", "backend"),
            ("Build a responsive React component for a dashboard", "frontend"),
            ("Write a Dockerfile for a Python FastAPI application", "devops"),
        ]

        for prompt, specialty in test_cases:
            print(f"\n{'=' * 60}")
            print(f"Testing {specialty.upper()}: {prompt[:50]}...")
            print(f"{'=' * 60}")

            try:
                response = await engine.generate(
                    messages=[{"role": "user", "content": prompt}],
                    specialty=specialty,
                    max_tokens=200,
                )

                print(f"Model: {response.model_used} ({response.provider})")
                print(f"Latency: {response.latency_ms:.2f}ms")
                print(f"Response: {response.content[:150]}...")
            except Exception as e:
                print(f"ERROR: {e}")

        # Show final status
        print("\n" + "=" * 60)
        print("ENGINE STATUS:")
        print("=" * 60)
        status = engine.get_status()
        print(json.dumps(status, indent=2, default=str))

        await engine.close()

    # Run test
    asyncio.run(test())
