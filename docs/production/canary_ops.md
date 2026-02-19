# Canary Operations

## Overview

This document describes how to manage canary deployments using the canary toggle script.

## Feature Flags

The system uses environment variables for feature flags:

| Flag | Description | Values |
|------|-------------|--------|
| `DENIS_MATERIALIZERS_ENABLED` | Enable materializers | `true`, `false` |
| `DENIS_MATERIALIZERS_PCT` | Traffic percentage | `0`, `1`, `10`, `50`, `100` |
| `ASYNC_ENABLED` | Enable async workers | `true`, `false` |
| `RUNS_ENABLED` | Enable async runs | `true`, `false` |
| `DENIS_SECONDARY_ENGINES` | Enable secondary inference engines | `true`, `false` |

## Using the Canary Script

### Set Canary Percentage

```bash
# Dry run (show what would change)
./scripts/canary_set.sh 10 --dry-run

# Apply 1% canary
./scripts/canary_set.sh 1

# Apply 10% canary
./scripts/canary_set.sh 10

# Apply 50%
./scripts/canary_set.sh 50

# Full rollout (100%)
./scripts/canary_set.sh 100

# Disable (0%)
./scripts/canary_set.sh 0
```

### Manual Toggle

```bash
# Via environment variable
DENIS_MATERIALIZERS_PCT=10 ./scripts/production_preflight.sh

# Via Kubernetes
kubectl set env deployment/denis DENIS_MATERIALIZERS_PCT=10 -n denis
kubectl rollout restart deployment/denis -n denis
```

## Verification

### Check Metrics

```bash
# Check materializer percentage
curl -s http://localhost:8084/metrics | grep materializer

# Check async status
curl -s http://localhost:8084/metrics | grep async
```

### Check Environment

```bash
# In pod
kubectl exec -it deployment/denis -n denis -- env | grep -E 'MATERIALIZERS|ASYNC'

# Via describe
kubectl describe deployment denis -n denis | grep -A5 "Environment"
```

## Rollback

```bash
# Immediate rollback
./scripts/canary_set.sh 0

# Or via Kubernetes
kubectl set env deployment/denis DENIS_MATERIALIZERS_ENABLED=false -n denis
kubectl rollout restart deployment/denis -n denis
```

## Kill Switch

```bash
# Emergency stop all async
kubectl scale deployment/denis-workers --replicas=0 -n denis
```

## Monitoring

### Grafana Dashboard

Track these metrics:
- `materializer_success_rate`
- `materializer_latency_p99`
- `async_queue_depth`
- `error_rate`

### Alerts

| Metric | Threshold | Action |
|--------|-----------|--------|
| `materializer_success_rate` | < 90% | Rollback |
| `error_rate` | > 5% | Rollback |
| `queue_depth` | > 500 | Scale workers |

## Canary Phases

| Phase | Percentage | Duration | Purpose |
|-------|------------|----------|---------|
| 1 | 1% | 4 hours | Initial observation |
| 2 | 10% | 24 hours | Stability check |
| 3 | 50% | 48 hours | Capacity test |
| 4 | 100% | Ongoing | Full production |
