# Production Observability SLOs
# Monitor these metrics post-deployment to ensure system health

## Latency SLOs
# P95 total request latency should be < 5 seconds for standard prompts
latency_slo_p95_ms = 5000

# P99 total request latency should be < 10 seconds
latency_slo_p99_ms = 10000

## Budget SLOs
# Token usage should not exceed planned by more than 50%
budget_drift_slo_max_ratio = 1.5

# Absolute token drift should be < 1000 tokens per request
budget_drift_slo_max_absolute = 1000

## Safety SLOs
# Strict mode requests should always include SAFETY_MODE_STRICT_APPLIED
strict_verify_slo_compliance_rate = 1.0  # 100%

# Evidence availability should be > 80% for non-trivial requests
evidence_availability_slo_min_rate = 0.8

## Error SLOs
# 5xx error rate should be < 1%
error_rate_slo_max_percentage = 1.0

# Contract validation should never fail (0% failure rate)
contract_validation_slo_max_failures = 0

## Trace Quality SLOs
# All traces should have complete phase information
trace_completeness_slo_min_rate = 1.0

# Span trees should be valid (no cycles, proper parent relationships)
trace_validity_slo_min_rate = 1.0

# Trace emission success rate should be > 99%
trace_emission_slo_min_rate = 0.99
