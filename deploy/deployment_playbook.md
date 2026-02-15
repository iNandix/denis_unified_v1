# Production Deployment Playbook
# Safe rollout procedure using verify + trace + contracts

## Prerequisites
- All integration tests pass (OpenAI contracts + internal contracts)
- Golden fixtures validated
- Contract canary script tested locally
- Rollback procedure documented
- Observability SLOs defined and monitored

## Phase 1: Pre-Deploy Validation (1-2 hours)
### 1.1 Run Full Integration Test Suite
```bash
# Run all contract and integration tests
export DENIS_TEST_MODE=0
pytest -m "contract or integration" --tb=short

# Validate golden fixtures exist and are current
python -c "
import json
fixtures = ['openai_chat_completions_golden.json']
for f in fixtures:
    with open(f'tests/fixtures/{f}') as fh:
        json.load(fh)  # Validate JSON
    print(f'✓ {f} valid')
"
```

### 1.2 Test Contract Canary Locally
```bash
# Test canary against local deployment
export CANARY_TARGET_URL=http://localhost:8000
python scripts/contract_canary.py
```

## Phase 2: Controlled Rollout (30-60 minutes)
### 2.1 Deploy with High Sampling (20% trace rate)
```bash
# Deploy new version
kubectl apply -f deploy/kubernetes/  # or your deployment method

# Set high trace sampling for monitoring
export TRACE_SAMPLE_RATE=0.2  # 20% of requests traced

# Enable observability metrics
export ENABLE_OBSERVABILITY=1
```

### 2.2 Monitor Initial Traffic (10 minutes)
```bash
# Watch key metrics
watch -n 30 '
echo "=== Health Checks ==="
curl -s http://your-service/health | jq .
echo

echo "=== Observability Status ==="
curl -s http://your-service/observability | jq .
echo

echo "=== Recent Errors ==="
kubectl logs -l app=denis --tail=10 -c app | grep -i error || echo "No recent errors"
'
```

### 2.3 Run Contract Canary in Production
```bash
# Run canary against production endpoint
export CANARY_TARGET_URL=https://your-production-endpoint.com
python scripts/contract_canary.py

# Expected: All tests PASS
```

### 2.4 Monitor SLO Compliance (20 minutes)
```bash
# Monitor key SLOs during rollout
watch -n 60 '
echo "=== Latency SLO ==="
# Check p95 latency from your monitoring system
curl -s https://your-monitoring-api.com/metrics/latency_p95 || echo "Check monitoring dashboard"

echo "=== Error Rate SLO ==="
# Check 5xx error rate
curl -s https://your-monitoring-api.com/metrics/error_rate || echo "Check monitoring dashboard"

echo "=== Budget Drift SLO ==="
# Check token usage anomalies
curl -s https://your-monitoring-api.com/metrics/budget_drift || echo "Check monitoring dashboard"
'
```

## Phase 3: Full Traffic & Validation (30-60 minutes)
### 3.1 Route 100% Traffic to New Version
```bash
# If using blue/green deployment, switch traffic
kubectl patch service denis-service -p '{"spec":{"selector":{"version":"new"}}}'

# If using canary, increase to 100%
kubectl scale deployment denis-new --replicas=10
kubectl scale deployment denis-old --replicas=0
```

### 3.2 Reduce Trace Sampling to Production Level
```bash
# Reduce to normal production sampling
export TRACE_SAMPLE_RATE=0.01  # 1% or your normal rate
```

### 3.3 Extended Monitoring (30 minutes)
```bash
# Monitor for 30 minutes with full traffic
# Watch for:
# - Latency regressions (>5s p95)
# - Error rate spikes (>1%)
# - Budget drift anomalies
# - Evidence availability drops (<80%)

# Check trace quality
echo "=== Trace Quality Check ==="
curl -s https://your-monitoring-api.com/trace_quality | jq .
```

## Phase 4: Stabilization & Cleanup
### 4.1 Final Validation
```bash
# Run contract canary one final time
python scripts/contract_canary.py

# Verify SLO compliance for last 30 minutes
# All SLOs should be green
```

### 4.2 Clean Up Old Resources
```bash
# Remove old deployment if blue/green
kubectl delete deployment denis-old

# Archive old trace files if needed
# Keep traces for post-mortem analysis
```

## Rollback Procedure (If Issues Detected)
### Immediate Rollback (<5 minutes)
```bash
# Roll back to previous version
kubectl rollout undo deployment/denis

# Restore old configuration
export TRACE_SAMPLE_RATE=0.01  # Production sampling
```

### Post-Rollback Analysis
```bash
# Analyze traces from failed deployment
echo "=== Analyze Failed Deployment Traces ==="
# Look for error patterns, latency spikes, budget anomalies
grep "error\|timeout\|budget" traces_*.jsonl | head -20

# Check contract canary results
# Identify which contract broke and why
```

## Success Criteria
- [ ] All integration tests pass
- [ ] Contract canary passes in production
- [ ] All SLOs within acceptable ranges for 30+ minutes
- [ ] No customer-impacting errors
- [ ] Trace quality metrics healthy

## Gotchas Addressed
### Contract Test Mode Security
```python
# Only enable in test environments
if os.getenv("ENV") != "production":
    DENIS_CONTRACT_TEST_MODE = os.getenv("DENIS_CONTRACT_TEST_MODE", "0")
```

### Extensions Field Compatibility
```python
# Use vendor-safe extension field
response["extensions"] = {
    "denis": {
        "attribution_flags": [...],
        "evidence_refs": [...],
        "disclaimers": [...]
    }
}
# Avoid top-level fields that might confuse OpenAI SDKs
```

## Monitoring Dashboard Queries
```sql
-- Latency SLO violations
SELECT count(*) as violations
FROM traces
WHERE total_duration_ms > 5000
AND timestamp > now() - interval '1 hour'

-- Budget drift anomalies
SELECT avg(budget_delta_total) as avg_drift
FROM traces
WHERE budget_planned_total > 0
AND timestamp > now() - interval '1 hour'

-- Evidence availability
SELECT
  count(*) as total_requests,
  sum(case when json_array_length(evidence_refs) > 0 then 1 else 0 end) as with_evidence
FROM traces
WHERE timestamp > now() - interval '1 hour'
```
