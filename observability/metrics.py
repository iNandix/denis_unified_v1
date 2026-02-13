"""Prometheus metrics for Denis."""
from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

# Request metrics
request_count = Counter(
    "denis_requests_total",
    "Total requests by intent",
    ["intent", "status"]
)

request_latency = Histogram(
    "denis_request_latency_seconds",
    "Request latency by phase",
    ["phase"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ttft = Histogram(
    "denis_ttft_seconds",
    "Time to first token",
    buckets=[0.1, 0.3, 0.5, 0.8, 1.0, 2.0]
)

# SMX metrics
smx_motor_calls = Counter(
    "denis_smx_motor_calls_total",
    "SMX motor calls",
    ["motor", "status"]
)

smx_motor_latency = Histogram(
    "denis_smx_motor_latency_seconds",
    "SMX motor latency",
    ["motor"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)

# Metacognition metrics
cognitive_router_decisions = Counter(
    "denis_cognitive_router_decisions_total",
    "Router decisions",
    ["tool", "pattern_id"]
)

l1_pattern_usage = Counter(
    "denis_l1_pattern_usage_total",
    "L1 Pattern usage",
    ["pattern_id"]
)

# Health metrics
system_health = Gauge(
    "denis_system_health_score",
    "System health score (0-1)"
)

metacognitive_coherence = Gauge(
    "denis_metacognitive_coherence_score",
    "Metacognitive coherence (0-1)"
)

def setup_metrics(app):
    """Setup Prometheus metrics on FastAPI app."""
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics")
    
    return instrumentator
