"""Advanced routing features: A/B testing, circuit breakers, load balancing."""

import asyncio
import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from denis_unified_v1.memory.backends import RedisBackend, utc_now
from denis_unified_v1.observability.metrics import inference_engine_selection
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for engine health management."""
    
    engine_id: str
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    last_state_change: float = field(default_factory=time.time)
    
    def record_success(self) -> None:
        """Record successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self) -> None:
        """Record failed request."""
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
    
    def can_attempt(self) -> bool:
        """Check if request can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if time.time() - self.last_state_change >= self.timeout_seconds:
                self._transition_to_half_open()
                return True
            return False
        
        # HALF_OPEN: allow limited requests
        return True
    
    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()
        self.success_count = 0
    
    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        self.failure_count = 0
    
    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.last_state_change = time.time()
        self.failure_count = 0
        self.success_count = 0


@dataclass
class ABTestConfig:
    """A/B test configuration."""
    
    test_id: str
    variant_a: str  # engine_id
    variant_b: str  # engine_id
    traffic_split: float = 0.5  # % to variant_b
    start_time: str = field(default_factory=utc_now)
    end_time: Optional[str] = None
    active: bool = True
    
    # Metrics
    variant_a_requests: int = 0
    variant_a_successes: int = 0
    variant_a_total_latency: float = 0
    
    variant_b_requests: int = 0
    variant_b_successes: int = 0
    variant_b_total_latency: float = 0


class ABTestManager:
    """Manages A/B tests for engine selection."""
    
    def __init__(self, redis: RedisBackend):
        self.redis = redis
        self.active_tests: Dict[str, ABTestConfig] = {}
        self._load_tests()
    
    def _load_tests(self) -> None:
        """Load active tests from Redis."""
        tests_data = self.redis.hgetall_json("denis:phase7:ab_tests")
        for test_id, test_data in tests_data.items():
            if test_data.get("active"):
                self.active_tests[test_id] = ABTestConfig(**test_data)
    
    def create_test(
        self,
        test_id: str,
        variant_a: str,
        variant_b: str,
        traffic_split: float = 0.5,
        duration_hours: int = 24,
    ) -> ABTestConfig:
        """Create new A/B test."""
        end_time = (
            datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        ).isoformat()
        
        test = ABTestConfig(
            test_id=test_id,
            variant_a=variant_a,
            variant_b=variant_b,
            traffic_split=traffic_split,
            end_time=end_time,
        )
        
        self.active_tests[test_id] = test
        self._save_test(test)
        
        return test
    
    def _save_test(self, test: ABTestConfig) -> None:
        """Save test to Redis."""
        test_dict = {
            "test_id": test.test_id,
            "variant_a": test.variant_a,
            "variant_b": test.variant_b,
            "traffic_split": test.traffic_split,
            "start_time": test.start_time,
            "end_time": test.end_time,
            "active": test.active,
            "variant_a_requests": test.variant_a_requests,
            "variant_a_successes": test.variant_a_successes,
            "variant_a_total_latency": test.variant_a_total_latency,
            "variant_b_requests": test.variant_b_requests,
            "variant_b_successes": test.variant_b_successes,
            "variant_b_total_latency": test.variant_b_total_latency,
        }
        self.redis.hset_json("denis:phase7:ab_tests", test.test_id, test_dict)
    
    def get_variant(self, test_id: str, user_id: str) -> Optional[str]:
        """Get variant for user (consistent hashing)."""
        test = self.active_tests.get(test_id)
        if not test or not test.active:
            return None
        
        # Check if test expired
        if test.end_time:
            end_dt = datetime.fromisoformat(test.end_time)
            if datetime.now(timezone.utc) > end_dt:
                test.active = False
                self._save_test(test)
                return None
        
        # Consistent hashing for user assignment
        hash_input = f"{test_id}:{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        assignment = (hash_value % 100) / 100.0
        
        return test.variant_b if assignment < test.traffic_split else test.variant_a
    
    def record_result(
        self,
        test_id: str,
        variant: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Record test result."""
        test = self.active_tests.get(test_id)
        if not test:
            return
        
        if variant == test.variant_a:
            test.variant_a_requests += 1
            if success:
                test.variant_a_successes += 1
            test.variant_a_total_latency += latency_ms
        elif variant == test.variant_b:
            test.variant_b_requests += 1
            if success:
                test.variant_b_successes += 1
            test.variant_b_total_latency += latency_ms
        
        self._save_test(test)
    
    def get_test_results(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get test results with statistical analysis."""
        test = self.active_tests.get(test_id)
        if not test:
            return None
        
        variant_a_success_rate = (
            test.variant_a_successes / test.variant_a_requests
            if test.variant_a_requests > 0
            else 0
        )
        variant_a_avg_latency = (
            test.variant_a_total_latency / test.variant_a_requests
            if test.variant_a_requests > 0
            else 0
        )
        
        variant_b_success_rate = (
            test.variant_b_successes / test.variant_b_requests
            if test.variant_b_requests > 0
            else 0
        )
        variant_b_avg_latency = (
            test.variant_b_total_latency / test.variant_b_requests
            if test.variant_b_requests > 0
            else 0
        )
        
        # Simple winner determination
        winner = None
        if test.variant_a_requests >= 100 and test.variant_b_requests >= 100:
            a_score = variant_a_success_rate - (variant_a_avg_latency / 1000)
            b_score = variant_b_success_rate - (variant_b_avg_latency / 1000)
            winner = test.variant_a if a_score > b_score else test.variant_b
        
        return {
            "test_id": test.test_id,
            "active": test.active,
            "variant_a": {
                "engine_id": test.variant_a,
                "requests": test.variant_a_requests,
                "success_rate": variant_a_success_rate,
                "avg_latency_ms": variant_a_avg_latency,
            },
            "variant_b": {
                "engine_id": test.variant_b,
                "requests": test.variant_b_requests,
                "success_rate": variant_b_success_rate,
                "avg_latency_ms": variant_b_avg_latency,
            },
            "winner": winner,
        }


class LoadBalancer:
    """Load balancer for distributing requests across engines."""
    
    def __init__(self):
        self.engine_loads: Dict[str, int] = defaultdict(int)
        self.engine_capacities: Dict[str, int] = {}
        self.last_cleanup = time.time()
    
    def set_capacity(self, engine_id: str, max_concurrent: int) -> None:
        """Set max concurrent requests for engine."""
        self.engine_capacities[engine_id] = max_concurrent
    
    def can_accept(self, engine_id: str) -> bool:
        """Check if engine can accept more requests."""
        capacity = self.engine_capacities.get(engine_id, 100)
        current_load = self.engine_loads[engine_id]
        return current_load < capacity
    
    def acquire(self, engine_id: str) -> bool:
        """Acquire slot for request."""
        if self.can_accept(engine_id):
            self.engine_loads[engine_id] += 1
            return True
        return False
    
    def release(self, engine_id: str) -> None:
        """Release slot after request."""
        self.engine_loads[engine_id] = max(0, self.engine_loads[engine_id] - 1)
    
    def get_least_loaded(self, engine_ids: List[str]) -> Optional[str]:
        """Get least loaded engine from list."""
        if not engine_ids:
            return None
        
        available = [eid for eid in engine_ids if self.can_accept(eid)]
        if not available:
            return None
        
        return min(available, key=lambda eid: self.engine_loads[eid])
    
    def cleanup(self) -> None:
        """Periodic cleanup of stale data."""
        if time.time() - self.last_cleanup > 300:  # 5 minutes
            # Reset loads that might be stuck
            for engine_id in list(self.engine_loads.keys()):
                if self.engine_loads[engine_id] == 0:
                    del self.engine_loads[engine_id]
            self.last_cleanup = time.time()


class AdvancedRoutingManager:
    """Manages advanced routing features."""
    
    def __init__(self, redis: RedisBackend):
        self.redis = redis
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.ab_test_manager = ABTestManager(redis)
        self.load_balancer = LoadBalancer()
    
    def get_circuit_breaker(self, engine_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for engine."""
        if engine_id not in self.circuit_breakers:
            self.circuit_breakers[engine_id] = CircuitBreaker(engine_id=engine_id)
        return self.circuit_breakers[engine_id]
    
    async def apply_routing_policies(
        self,
        candidate_engines: List[str],
        user_id: Optional[str] = None,
        class_key: Optional[str] = None,
    ) -> List[str]:
        """Apply all routing policies to filter/reorder candidates."""
        with tracer.start_as_current_span("advanced_routing.apply_policies") as span:
            span.set_attribute("candidates_count", len(candidate_engines))
            
            # 1. Filter by circuit breaker
            healthy_engines = [
                eid for eid in candidate_engines
                if self.get_circuit_breaker(eid).can_attempt()
            ]
            span.set_attribute("after_circuit_breaker", len(healthy_engines))
            
            if not healthy_engines:
                return candidate_engines[:1]  # Fallback to first
            
            # 2. Apply A/B test if active
            if user_id:
                for test_id in self.ab_test_manager.active_tests:
                    variant = self.ab_test_manager.get_variant(test_id, user_id)
                    if variant and variant in healthy_engines:
                        span.set_attribute("ab_test_variant", variant)
                        return [variant]
            
            # 3. Load balancing
            self.load_balancer.cleanup()
            least_loaded = self.load_balancer.get_least_loaded(healthy_engines)
            if least_loaded:
                span.set_attribute("load_balanced_engine", least_loaded)
                # Reorder to put least loaded first
                healthy_engines.remove(least_loaded)
                healthy_engines.insert(0, least_loaded)
            
            return healthy_engines
    
    def record_execution_result(
        self,
        engine_id: str,
        success: bool,
        latency_ms: float,
        test_id: Optional[str] = None,
    ) -> None:
        """Record execution result for all systems."""
        # Circuit breaker
        cb = self.get_circuit_breaker(engine_id)
        if success:
            cb.record_success()
        else:
            cb.record_failure()
        
        # A/B test
        if test_id:
            self.ab_test_manager.record_result(test_id, engine_id, success, latency_ms)
        
        # Load balancer
        self.load_balancer.release(engine_id)
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all routing systems."""
        return {
            "circuit_breakers": {
                eid: {
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "success_count": cb.success_count,
                }
                for eid, cb in self.circuit_breakers.items()
            },
            "active_ab_tests": list(self.ab_test_manager.active_tests.keys()),
            "load_balancer": {
                "engine_loads": dict(self.load_balancer.engine_loads),
                "capacities": dict(self.load_balancer.engine_capacities),
            },
        }
