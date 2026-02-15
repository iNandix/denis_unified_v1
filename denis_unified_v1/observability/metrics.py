"""Minimal no-op metrics stubs for import compatibility.

Replace with real prometheus_client counters when observability stack is wired.
"""


class Counter:
    def inc(self, amount=1):
        pass

    def labels(self, **kwargs):
        return self


class Histogram:
    def observe(self, value):
        pass

    def labels(self, **kwargs):
        return self


class Gauge:
    def set(self, value):
        pass

    def inc(self, amount=1):
        pass

    def dec(self, amount=1):
        pass

    def labels(self, **kwargs):
        return self


# Cognitive router
cognitive_router_decisions = Counter()
l1_pattern_usage = Counter()

# Inference router
inference_router_decisions = Counter()
inference_router_latency = Histogram()
inference_engine_selection = Counter()

# Circuit breaker / hedging (engine_broker.py)
inference_circuit_breaker_state = Gauge()
inference_circuit_breaker_failures = Counter()
inference_hedging_decisions = Counter()

# Gates
gate_budget_exceeded = Counter()
gate_rate_limited = Counter()
gate_output_blocked = Counter()
gate_prompt_injection = Counter()

# Rate limiter (gates/rate_limiter.py)
denis_gate_rate_limited_total = Counter()
denis_gate_rate_limit_redis_errors = Counter()
