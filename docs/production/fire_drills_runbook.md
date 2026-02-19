# Fire Drills Runbook

## Overview

This runbook describes how to execute the fire drills in the `scripts/drills/` directory.

## Prerequisites

- `curl` installed
- Access to DENIS_BASE_URL
- For some drills: `redis-cli`, `cypher-shell`, `celery` CLI

## Running Drills

### Individual Drills

```bash
# Run a specific drill
./scripts/drills/drill_redis_down.sh
./scripts/drills/drill_worker_missing.sh
./scripts/drills/drill_graph_slow.sh
./scripts/drills/drill_chat_flood.sh
./scripts/drills/drill_job_replay.sh
./scripts/drills/drill_artifact_tamper.sh

# With custom base URL
DENIS_BASE_URL=http://denis.internal:8084 ./scripts/drills/drill_redis_down.sh
```

### Run All Drills

```bash
# Run all drills
./scripts/drills/run_all_drills.sh

# Run safe drills only (no infrastructure changes)
SAFE_ONLY=true ./scripts/drills/run_all_drills.sh
```

## Drill Descriptions

### 1. Redis Down (`drill_redis_down.sh`)

Validates fail-open when Redis is unavailable.

**Expected:**
- Rate limiting falls back to in-memory
- /chat still responds with 200

**Artifacts:**
- `artifacts/drills/redis_down_<timestamp>/`

### 2. Worker Missing (`drill_worker_missing.sh`)

Validates queue behavior when Celery workers are unavailable.

**Expected:**
- Jobs queue up
- /chat continues working (async is non-critical)

**Artifacts:**
- `artifacts/drills/worker_missing_<timestamp>/`

### 3. Graph Slow (`drill_graph_slow.sh`)

Validates circuit breaker when Neo4j is slow.

**Expected:**
- Graph legacy mode activates
- /chat continues with degraded features

**Artifacts:**
- `artifacts/drills/graph_slow_<timestamp>/`

### 4. Chat Flood (`drill_chat_flood.sh`)

Validates system under high load.

**Expected:**
- Rate limiting activates
- Graceful degradation

**Config:**
- `REQUESTS=50` - Number of requests
- `RATE_LIMIT=10` - Max requests per second

**Artifacts:**
- `artifacts/drills/chat_flood_<timestamp>/`

### 5. Job Replay (`drill_job_replay.sh`)

Validates async job retry mechanism.

**Expected:**
- Failed jobs can be retried
- No data loss

**Artifacts:**
- `artifacts/drills/job_replay_<timestamp>/`

### 6. Artifact Tamper (`drill_artifact_tamper.sh`)

Validates artifact integrity checks.

**Expected:**
- Corrupted artifacts detected
- /chat unaffected

**Artifacts:**
- `artifacts/drills/artifact_tamper_<timestamp>/`

## Interpreting Results

### Pass
- Drill succeeded
- System handled the failure gracefully

### Fail
- Drill failed
- Review artifacts in `artifacts/drills/`

### Skip
- Drill could not run (missing dependencies)
- Not necessarily a problem

## Automation

### CI/CD Integration

```yaml
# .github/workflows/fire-drills.yaml
name: Fire Drills

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  drills:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Preflight
        run: ./scripts/production_preflight.sh
        
      - name: Run Fire Drills
        run: ./scripts/drills/run_all_drills.sh
        env:
          DENIS_BASE_URL: ${{ secrets.DENIS_BASE_URL }}
```

## Troubleshooting

### Server Unreachable

```bash
# Check if server is running
ps aux | grep uvicorn

# Check port
ss -tlnp | grep 8084
```

### Drill Fails

1. Review artifacts in `artifacts/drills/<drill_name>/`
2. Check `result.txt` for pass/fail
3. Check metrics before/after in `before_metrics.txt` and `after_metrics.txt`

### False Positives

Some drills may skip if infrastructure is not available. This is expected and not a failure.
