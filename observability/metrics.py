"""Prometheus metrics for Denis."""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

# Request metrics
request_count = Counter(
    "denis_requests_total", "Total requests by intent", ["intent", "status"]
)

request_latency = Histogram(
    "denis_request_latency_seconds",
    "Request latency by phase",
    ["phase"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

ttft = Histogram(
    "denis_ttft_seconds", "Time to first token", buckets=[0.1, 0.3, 0.5, 0.8, 1.0, 2.0]
)

# SMX metrics
smx_motor_calls = Counter(
    "denis_smx_motor_calls_total", "SMX motor calls", ["motor", "status"]
)

smx_motor_latency = Histogram(
    "denis_smx_motor_latency_seconds",
    "SMX motor latency",
    ["motor"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# Metacognition metrics
cognitive_router_decisions = Counter(
    "denis_cognitive_router_decisions_total", "Router decisions", ["tool", "pattern_id"]
)

l1_pattern_usage = Counter(
    "denis_l1_pattern_usage_total", "L1 Pattern usage", ["pattern_id"]
)

# Health metrics
system_health = Gauge("denis_system_health_score", "System health score (0-1)")

metacognitive_coherence = Gauge(
    "denis_metacognitive_coherence_score", "Metacognitive coherence (0-1)"
)

# Inference Router metrics
inference_router_decisions = Counter(
    "denis_inference_router_decisions_total",
    "Inference router decisions",
    ["engine_id", "reason", "shadow_mode"],
)

inference_router_latency = Histogram(
    "denis_inference_router_latency_seconds",
    "Inference router decision latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

inference_engine_selection = Counter(
    "denis_inference_engine_selection_total",
    "Engine selected by bandit",
    ["engine_id", "class_key"],
)

inference_bandit_reward = Histogram(
    "denis_inference_bandit_reward",
    "Bandit reward signal",
    ["engine_id"],
    buckets=[-1.0, -0.5, 0.0, 0.5, 1.0],
)

inference_engine_health = Gauge(
    "denis_inference_engine_health",
    "Engine health status (0=unhealthy, 1=healthy)",
    ["engine_id"],
)

inference_shadow_mode_matches = Counter(
    "denis_inference_shadow_matches_total",
    "Cases where shadow mode decision matched primary",
    ["engine_id"],
)

inference_circuit_breaker_state = Gauge(
    "denis_inference_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["engine_id"],
)

inference_circuit_breaker_failures = Counter(
    "denis_inference_circuit_breaker_failures_total",
    "Circuit breaker failure count",
    ["engine_id"],
)

inference_ab_test_assignments = Counter(
    "denis_inference_ab_test_assignments_total",
    "A/B test variant assignments",
    ["test_id", "variant"],
)

inference_hedging_decisions = Counter(
    "denis_inference_hedging_decisions_total",
    "Hedging decisions (hedge vs direct)",
    ["engine_id", "hashed"],
)

# Gate hardening (Phase 10) metrics
gate_budget_exceeded = Counter(
    "denis_gate_budget_exceeded_total",
    "Number of times inference budgets were exceeded",
    ["budget"],
)

gate_rate_limited = Counter(
    "denis_gate_rate_limited_total",
    "Number of requests limited by Phase10 gate",
    ["scope"],
)

gate_prompt_injection = Counter(
    "denis_gate_prompt_injection_total",
    "Prompt injection risk classifications",
    ["risk"],
)

gate_output_blocked = Counter(
    "denis_gate_output_blocked_total",
    "Number of responses blocked or modified by output validation",
    ["reason"],
)

# Memory metrics
memory_consolidations = Counter(
    "denis_memory_consolidations_total",
    "Memory consolidation runs",
    ["status"],
)

memory_retrieval_total = Counter(
    "denis_memory_retrieval_total",
    "Memory retrieval requests",
    ["hit"],
)

memory_ingest_total = Counter(
    "denis_memory_ingest_total",
    "Memory ingest operations",
    ["type"],
)

memory_contradictions_detected = Counter(
    "denis_memory_contradictions_detected_total",
    "Contradictions detected",
    ["type"],
)

memory_contradictions_resolved = Counter(
    "denis_memory_contradictions_resolved_total",
    "Contradictions resolved",
)

memory_latency_seconds = Histogram(
    "denis_memory_latency_seconds",
    "Memory operation latency",
    ["stage"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

# Voice metrics
voice_stt_latency = Histogram(
    "denis_voice_stt_latency_seconds",
    "STT processing latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

voice_tts_latency = Histogram(
    "denis_voice_tts_latency_seconds",
    "TTS processing latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

voice_errors = Counter(
    "denis_voice_errors_total",
    "Voice pipeline errors",
    ["component"],
)


def setup_metrics(app):
    """Setup Prometheus metrics on FastAPI app."""
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics")

    return instrumentator
