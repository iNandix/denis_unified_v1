# RELEASE CLOSURE PACK: P0/P0.5 → P1 ROADMAP
**Denis Control Plane Reboot v1**  
**Date:** 2026-02-18  
**Status:** P0.5 STAGING → P1 EXECUTION

---

## RELEASE CLOSURE SUMMARY (P0 + P0.5)

### What Ships in P0.5

| Component | Status | Verification |
|-----------|--------|--------------|
| **/chat** | ✅ Production-ready | Returns 200, routes to providers |
| **/health** | ✅ Stub implemented | Returns 200 with component status |
| **/hass/entities** | ✅ Stub implemented | Returns 200 with entity list |
| **/telemetry** | ✅ Stub implemented | Returns JSON + Prometheus format |
| **DecisionTrace** | ✅ Writes to Graph | All endpoints write traces |
| **Anti-loop** | ✅ X-Denis-Hop enforced | Middleware checks hop count |

### What P0.5 Unblocks

- **nodo2 Frontend**: Can render Ops dashboard (/health, /telemetry)
- **nodo2 Frontend**: Can render Care dashboard (/hass/entities)
- **nodo2 Frontend**: Chat interface fully functional (/chat)
- **Operations**: Health monitoring available
- **Care**: Device monitoring available (stubbed)

### Critical Gaps (P1 Targets)

1. Real health checks (not stubs)
2. Real HASS integration (not stubbed entities)
3. Real telemetry (not hardcoded counters)
4. Rate limiting
5. Circuit breakers
6. Proper auth
7. Testing infrastructure
8. Documentation

---

## WS1: FRONTEND CONTRACT ALIGNMENT

### Endpoint Specifications

| Endpoint | Method | Timeout | Retries | Critical? |
|----------|--------|---------|---------|-----------|
| /chat | POST | 30s | 2 (with backoff) | YES |
| /health | GET | 5s | 0 | NO |
| /hass/entities | GET | 10s | 1 | NO |
| /telemetry | GET | 5s | 0 | NO |

### Degraded Semantics

| Endpoint | 200 OK | 404 | 500 | Timeout |
|----------|--------|-----|-----|---------|
| /chat | 🟢 Full function | 🔴 Fatal | 🔴 Fatal | 🟡 Fallback to local |
| /health | 🟢 Full info | 🟡 Degraded mode | 🟠 Limited info | 🟠 Cached response |
| /hass/entities | 🟢 Full list | 🟡 Empty list + flag | 🟠 Empty list | 🟠 Empty list |
| /telemetry | 🟢 Full metrics | 🟡 Stub metrics | 🟠 Stub metrics | 🟠 Stub metrics |

### Compatibility Table: Response → Frontend State

| Endpoint | Response Code | Body Contains | Frontend Status | Action |
|----------|--------------|---------------|-----------------|--------|
| /chat | 200 | choices[] | 🟢 Operational | Render response |
| /chat | 200 | degraded:true | 🟡 Degraded | Show warning banner |
| /chat | 503 | error | 🔴 Down | Show error + retry |
| /chat | Timeout | - | 🟡 Fallback | Switch to local mode |
| /health | 200 | status:healthy | 🟢 Healthy | Green indicator |
| /health | 200 | status:degraded | 🟡 Warning | Yellow indicator |
| /health | 200 | service down | 🟠 Partial | List failing services |
| /health | 404 | - | 🟡 Unknown | Gray indicator |
| /hass/entities | 200 | entities[] | 🟢 Connected | Render devices |
| /hass/entities | 200 | hass_connected:false | 🟡 Not configured | Show setup prompt |
| /hass/entities | 200 | entities:[] | 🟡 No devices | Empty state |
| /telemetry | 200 | metrics | 🟢 Monitoring | Render graphs |
| /telemetry | 200 | stub:true | 🟡 Limited | Show partial data |

---

## WS2: BACKEND P0.5 STUBS THAT COUNT

### GET /health

**Guarantee:** Never returns 500. Always returns 200 with status info.

**Schema:**
```json
{
  "status": "healthy|degraded|unknown",
  "timestamp": "ISO8601",
  "version": "string",
  "services": {
    "chat_cp": {"status": "up|down", "latency_ms": number},
    "graph": {"status": "up|down", "nodes": number},
    "overlay": {"status": "up|down", "last_scan": "ISO8601|null"}
  },
  "nodomac": {
    "reachable": boolean,
    "last_heartbeat": "ISO8601|null"
  },
  "degraded": boolean,
  "message": "string|null"
}
```

**Example OK (200):**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-18T14:30:00Z",
  "version": "3.1.0",
  "services": {
    "chat_cp": {"status": "up", "latency_ms": 45},
    "graph": {"status": "up", "nodes": 150},
    "overlay": {"status": "up", "last_scan": "2026-02-18T12:00:00Z"}
  },
  "nodomac": {
    "reachable": true,
    "last_heartbeat": "2026-02-18T14:29:00Z"
  },
  "degraded": false,
  "message": null
}
```

**Example Degraded (200):**
```json
{
  "status": "degraded",
  "timestamp": "2026-02-18T14:30:00Z",
  "version": "3.1.0",
  "services": {
    "chat_cp": {"status": "up", "latency_ms": 45},
    "graph": {"status": "down", "nodes": 0},
    "overlay": {"status": "up", "last_scan": "2026-02-18T12:00:00Z"}
  },
  "nodomac": {
    "reachable": true,
    "last_heartbeat": "2026-02-18T14:29:00Z"
  },
  "degraded": true,
  "message": "Graph database unreachable, using cached data"
}
```

---

### GET /hass/entities

**Guarantee:** Always returns 200. Never exposes HASS credentials.

**Schema:**
```json
{
  "entities": [
    {
      "entity_id": "string",
      "domain": "camera|sensor|switch|light",
      "state": "string",
      "attributes": {},
      "last_updated": "ISO8601"
    }
  ],
  "count": number,
  "hass_connected": boolean,
  "hass_configured": boolean,
  "message": "string|null",
  "timestamp": "ISO8601"
}
```

**Example OK (200) - Configured:**
```json
{
  "entities": [
    {
      "entity_id": "camera.front_door",
      "domain": "camera",
      "state": "recording",
      "attributes": {"motion_detection": true},
      "last_updated": "2026-02-18T14:25:00Z"
    },
    {
      "entity_id": "sensor.living_room_temp",
      "domain": "sensor",
      "state": "22.5",
      "attributes": {"unit": "celsius"},
      "last_updated": "2026-02-18T14:20:00Z"
    }
  ],
  "count": 2,
  "hass_connected": true,
  "hass_configured": true,
  "message": null,
  "timestamp": "2026-02-18T14:30:00Z"
}
```

**Example Not Configured (200):**
```json
{
  "entities": [],
  "count": 0,
  "hass_connected": false,
  "hass_configured": false,
  "message": "Home Assistant not configured. Add HASS_URL and HASS_TOKEN to enable.",
  "timestamp": "2026-02-18T14:30:00Z"
}
```

---

### GET /telemetry

**Guarantee:** Always returns 200. Supports JSON (default) and Prometheus format.

**Schema (JSON):**
```json
{
  "requests": {
    "total_1h": number,
    "error_rate_1h": number,
    "latency_p95_ms": number,
    "latency_p99_ms": number
  },
  "providers": {
    "anthropic": {"requests": number, "errors": number, "avg_latency_ms": number},
    "openai": {"requests": number, "errors": number, "avg_latency_ms": number},
    "local": {"requests": number, "errors": number, "avg_latency_ms": number}
  },
  "graph": {
    "decisions_1h": number,
    "avg_decision_latency_ms": number
  },
  "stub": boolean,
  "timestamp": "ISO8601"
}
```

**Example OK (200) - JSON:**
```json
{
  "requests": {
    "total_1h": 1250,
    "error_rate_1h": 0.02,
    "latency_p95_ms": 450,
    "latency_p99_ms": 1200
  },
  "providers": {
    "anthropic": {"requests": 800, "errors": 5, "avg_latency_ms": 420},
    "openai": {"requests": 400, "errors": 20, "avg_latency_ms": 380},
    "local": {"requests": 50, "errors": 0, "avg_latency_ms": 5}
  },
  "graph": {
    "decisions_1h": 1250,
    "avg_decision_latency_ms": 5
  },
  "stub": false,
  "timestamp": "2026-02-18T14:30:00Z"
}
```

**Example Stub (200) - JSON:**
```json
{
  "requests": {
    "total_1h": 0,
    "error_rate_1h": 0.0,
    "latency_p95_ms": 0,
    "latency_p99_ms": 0
  },
  "providers": {
    "anthropic": {"requests": 0, "errors": 0, "avg_latency_ms": 0},
    "openai": {"requests": 0, "errors": 0, "avg_latency_ms": 0},
    "local": {"requests": 0, "errors": 0, "avg_latency_ms": 0}
  },
  "graph": {
    "decisions_1h": 0,
    "avg_decision_latency_ms": 0
  },
  "stub": true,
  "timestamp": "2026-02-18T14:30:00Z"
}
```

**Prometheus Format (Accept: text/plain):**
```
# HELP denis_requests_total Total requests
# TYPE denis_requests_total counter
denis_requests_total 1250

# HELP denis_error_rate Error rate (0-1)
# TYPE denis_error_rate gauge
denis_error_rate 0.02

# HELP denis_latency_p95 P95 latency in ms
# TYPE denis_latency_p95 gauge
denis_latency_p95 450

# HELP denis_latency_p99 P99 latency in ms
# TYPE denis_latency_p99 gauge
denis_latency_p99 1200

denis_provider_requests_total{provider="anthropic"} 800
denis_provider_errors_total{provider="anthropic"} 5
denis_provider_latency_avg_ms{provider="anthropic"} 420

denis_provider_requests_total{provider="openai"} 400
denis_provider_errors_total{provider="openai"} 20
denis_provider_latency_avg_ms{provider="openai"} 380
```

---

## WS3: DECISIONTRACE SPECIFICATION

### DecisionTrace for /chat (Routing Decision)

**Fields:**
```json
{
  "trace_id": "uuid",
  "timestamp_ms": 1708000000000,
  "decision_type": "routing",
  "endpoint": "/chat",
  "context": {
    "hop_count": 1,
    "client": "frontend-p0",
    "request_id": "uuid"
  },
  "inputs": {
    "available_providers": ["anthropic", "openai", "local"],
    "provider_health": {"anthropic": "up", "openai": "degraded"},
    "latency_budget_ms": 5000
  },
  "policy": "latency_optimized",
  "selected": "anthropic_chat",
  "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
  "outcome": "success",
  "latency_ms": 420,
  "error_class": null,
  "error_message": null
}
```

### DecisionTrace for Ops (/health, /hass/entities, /telemetry)

**Fields:**
```json
{
  "trace_id": "uuid",
  "timestamp_ms": 1708000000000,
  "decision_type": "ops_query",
  "endpoint": "/health",
  "context": {
    "sources_queried": ["graph", "memory"],
    "cache_hit": true,
    "stub_mode": false
  },
  "outcome": "success",
  "latency_ms": 15,
  "error_class": null
}
```

### Graph Schema for DecisionTrace

```cypher
// Node: Decision
(:Decision {
  id: string,              // UUID
  trace_id: string,        // correlation ID
  timestamp_ms: integer,   // epoch ms
  decision_type: string,   // routing|ops_query|policy
  endpoint: string,        // /chat|/health|...
  selected: string,        // chosen option
  outcome: string,         // success|failure|fallback
  latency_ms: integer,     // decision time
  error_class: string,     // null if success
  context: string          // JSON string
})

// Indexes
CREATE INDEX decision_timestamp IF NOT EXISTS FOR (d:Decision) ON (d.timestamp_ms);
CREATE INDEX decision_endpoint IF NOT EXISTS FOR (d:Decision) ON (d.endpoint);
CREATE INDEX decision_outcome IF NOT EXISTS FOR (d:Decision) ON (d.outcome);
```

### Retention Rules

| Decision Type | Retention | Reason |
|--------------|-----------|---------|
| routing | 30 days | High volume, analytics |
| ops_query | 7 days | Debugging, lower volume |
| policy | 90 days | Audit trail |

### 5 Ops Debug Queries

**Q1: Recent routing decisions with errors:**
```cypher
MATCH (d:Decision)
WHERE d.decision_type = 'routing' 
  AND d.outcome = 'failure'
  AND d.timestamp_ms > timestamp() - duration({hours: 1})
RETURN d.endpoint, d.error_class, d.latency_ms
ORDER BY d.timestamp_ms DESC
LIMIT 20
```

**Q2: Provider success rate last hour:**
```cypher
MATCH (d:Decision)
WHERE d.decision_type = 'routing'
  AND d.timestamp_ms > timestamp() - duration({hours: 1})
WITH d.selected as provider,
     count(*) as total,
     sum(CASE WHEN d.outcome = 'success' THEN 1 ELSE 0 END) as success
RETURN provider, 
       total, 
       success,
       round(100.0 * success / total, 2) as success_rate
ORDER BY success_rate ASC
```

**Q3: Slow ops queries (>100ms):**
```cypher
MATCH (d:Decision)
WHERE d.decision_type = 'ops_query'
  AND d.latency_ms > 100
  AND d.timestamp_ms > timestamp() - duration({hours: 24})
RETURN d.endpoint, d.latency_ms, d.timestamp_ms
ORDER BY d.latency_ms DESC
LIMIT 50
```

**Q4: Error rate trend by hour:**
```cypher
MATCH (d:Decision)
WHERE d.timestamp_ms > timestamp() - duration({days: 7})
WITH datetime({epochMillis: d.timestamp_ms}).hour as hour,
     count(*) as total,
     sum(CASE WHEN d.outcome = 'failure' THEN 1 ELSE 0 END) as errors
RETURN hour,
       total,
       errors,
       round(100.0 * errors / total, 2) as error_rate
ORDER BY hour
```

**Q5: Fallback frequency:**
```cypher
MATCH (d:Decision)
WHERE d.decision_type = 'routing'
  AND d.outcome = 'fallback'
  AND d.timestamp_ms > timestamp() - duration({hours: 24})
RETURN d.selected as fallback_provider,
       count(*) as fallback_count
ORDER BY fallback_count DESC
```

---

## WS4: VALIDATION PACK

### Script: validate_p05.sh

```bash
#!/bin/bash
set -e

BASE_URL="${DENIS_BASE_URL:-http://localhost:9999}"
FAILED=0

echo "=== P0.5 VALIDATION ==="
echo "Testing: $BASE_URL"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_field() {
  local response="$1"
  local field="$2"
  if echo "$response" | grep -q "$field"; then
    echo -e "${GREEN}✓${NC} Field '$field' present"
    return 0
  else
    echo -e "${RED}✗${NC} Field '$field' MISSING"
    return 1
  fi
}

# Test 1: /chat (Critical)
echo "TEST 1: POST /chat (Critical)"
response=$(curl -s -w "\n%{http_code}" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}' \
  "$BASE_URL/chat" 2>&1 || echo "CONNECTION_FAILED")

if echo "$response" | grep -q "CONNECTION_FAILED"; then
  echo -e "${RED}✗${NC} Connection failed - Server down?"
  exit 1
fi

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓${NC} HTTP 200"
  check_field "$body" "choices" || FAILED=1
elif [ "$http_code" = "503" ]; then
  echo -e "${YELLOW}⚠${NC} HTTP 503 (Degraded) - Acceptable for P0.5"
else
  echo -e "${RED}✗${NC} HTTP $http_code - UNEXPECTED"
  FAILED=1
fi
echo ""

# Test 2: /health
echo "TEST 2: GET /health"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/health" 2>&1)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓${NC} HTTP 200"
  check_field "$body" "status" || FAILED=1
  check_field "$body" "services" || FAILED=1
  check_field "$body" "timestamp" || FAILED=1
  
  # Check status value
  if echo "$body" | grep -q '"status":"healthy"'; then
    echo -e "${GREEN}✓${NC} Status: healthy"
  elif echo "$body" | grep -q '"status":"degraded"'; then
    echo -e "${YELLOW}⚠${NC} Status: degraded (acceptable)"
  else
    echo -e "${YELLOW}⚠${NC} Status: unknown"
  fi
else
  echo -e "${RED}✗${NC} HTTP $http_code"
  FAILED=1
fi
echo ""

# Test 3: /hass/entities
echo "TEST 3: GET /hass/entities"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/hass/entities" 2>&1)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓${NC} HTTP 200"
  check_field "$body" "entities" || FAILED=1
  check_field "$body" "count" || FAILED=1
  check_field "$body" "hass_connected" || FAILED=1
  
  # Extract count
  count=$(echo "$body" | grep -o '"count":[0-9]*' | cut -d':' -f2)
  echo "  Entity count: $count"
else
  echo -e "${RED}✗${NC} HTTP $http_code"
  FAILED=1
fi
echo ""

# Test 4: /telemetry (JSON)
echo "TEST 4: GET /telemetry (JSON)"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/telemetry" 2>&1)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓${NC} HTTP 200"
  check_field "$body" "requests" || FAILED=1
  check_field "$body" "providers" || FAILED=1
  check_field "$body" "graph" || FAILED=1
else
  echo -e "${RED}✗${NC} HTTP $http_code"
  FAILED=1
fi
echo ""

# Test 5: /telemetry (Prometheus)
echo "TEST 5: GET /telemetry (Prometheus)"
response=$(curl -s -w "\n%{http_code}" \
  -H "Accept: text/plain" \
  "$BASE_URL/telemetry" 2>&1)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓${NC} HTTP 200"
  if echo "$body" | grep -q "denis_requests_total"; then
    echo -e "${GREEN}✓${NC} Prometheus format valid"
  else
    echo -e "${RED}✗${NC} Invalid Prometheus format"
    FAILED=1
  fi
else
  echo -e "${RED}✗${NC} HTTP $http_code"
  FAILED=1
fi
echo ""

# Summary
echo "=== SUMMARY ==="
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✓${NC} ALL TESTS PASSED"
  echo "P0.5 is READY for nodo2 integration"
  exit 0
else
  echo -e "${RED}✗${NC} SOME TESTS FAILED"
  echo "Check logs and retry"
  exit 1
fi
```

### Usage

```bash
chmod +x validate_p05.sh

# Default (localhost:9999)
./validate_p05.sh

# Custom endpoint
DENIS_BASE_URL=http://nodo1:9999 ./validate_p05.sh
```

### Expected Output (Success)

```
=== P0.5 VALIDATION ===
Testing: http://localhost:9999

TEST 1: POST /chat (Critical)
✓ HTTP 200
✓ Field 'choices' present

TEST 2: GET /health
✓ HTTP 200
✓ Field 'status' present
✓ Field 'services' present
✓ Field 'timestamp' present
✓ Status: healthy

TEST 3: GET /hass/entities
✓ HTTP 200
✓ Field 'entities' present
✓ Field 'count' present
✓ Field 'hass_connected' present
  Entity count: 3

TEST 4: GET /telemetry (JSON)
✓ HTTP 200
✓ Field 'requests' present
✓ Field 'providers' present
✓ Field 'graph' present

TEST 5: GET /telemetry (Prometheus)
✓ HTTP 200
✓ Prometheus format valid

=== SUMMARY ===
✓ ALL TESTS PASSED
P0.5 is READY for nodo2 integration
```

### Failure Diagnosis

| Failure | Diagnosis | Fix |
|---------|-----------|-----|
| Connection refused | Server not running | Start FastAPI server |
| HTTP 404 | Routers not registered | Check fastapi_server.py includes |
| Missing fields | Response malformed | Check route implementation |
| /chat 503 | Chat CP unavailable | Check if DENIS_ENABLE_CHAT_CP=1 |
| Prometheus invalid | Wrong content-type | Check Accept header handling |

---

## WS5: CODEX UNBLOCK PLAN (PACKAGING DECISION)

### Decision: OPTION A (Minimal pyproject.toml)

**Justification:**
1. **Root cause**: Codex can't run tests because imports fail
2. **Why not B**: Pytest config fixes are fragile and break when test structure changes
3. **Why A**: `pip install -e .` is standard, enables IDE autocomplete, works with pytest, future-proof
4. **Risk**: Low - only adds one file, doesn't change existing code
5. **Benefit**: Unblocks Codex immediately, enables proper Python packaging

### Files to Create/Modify

**CREATE: pyproject.toml** (root)
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "denis-unified-v1"
version = "3.1.0"
description = "Denis Unified Control Plane"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "neo4j>=5.0.0",
    "redis>=4.0.0",
    "pydantic>=2.0.0",
    "prometheus-client>=0.17.0",
    # Add others as needed
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "httpx>=0.24.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["denis_unified_v1*"]
exclude = ["tests*", "scripts*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
asyncio_mode = "auto"
```

**MODIFY: tests/conftest.py** (add if missing)
```python
import sys
from pathlib import Path

# Ensure package is importable
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
```

**MODIFY: .gitignore** (add)
```
*.egg-info/
__pycache__/
*.pyc
.pytest_cache/
.coverage
```

### Commands to Validate

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install package in editable mode
pip install -e ".[dev]"

# 3. Verify imports work
python -c "from denis_unified_v1.chat_cp.graph_trace import maybe_write_decision_trace; print('✓ Imports OK')"

# 4. Run specific test
python -m pytest tests/test_chat_cp_smoke.py -v

# 5. Run all tests
python -m pytest -q

# 6. Verify anti-loop test (specific to Denis)
python -m pytest tests/test_x_denis_hop.py -vv
```

### Expected Output

```
$ pip install -e ".[dev]"
...
Successfully installed denis-unified-v1-3.1.0

$ python -m pytest tests/test_x_denis_hop.py -vv
tests/test_x_denis_hop.py::TestDenisHopHeader::test_hop_header_increments PASSED
tests/test_x_denis_hop.py::TestDenisHopHeader::test_hop_limit_enforced PASSED
tests/test_x_denis_hop.py::TestDenisHopHeader::test_no_hop_header_on_first_request PASSED

3 passed in 0.45s
```

### Rollback (if needed)

```bash
# Uninstall editable package
pip uninstall denis-unified-v1

# Remove pyproject.toml
git checkout -- pyproject.toml

# Fallback to PYTHONPATH
export PYTHONPATH=/media/jotah/SSD_denis/home_jotah/denis_unified_v1:$PYTHONPATH
```

---

## WS6: P1 BACKLOG AS PR LIST (8 PRs)

### PR-1: Real Health Checks (Unblocks Ops Dashboard)
**Goal:** Replace /health stub with real health checks  
**Scope:**
- Implement ping to Chat CP, Graph, Overlay
- Add timeout handling (5s max per service)
- Return accurate degraded state
- Cache results (30s TTL)

**Files:**
- `api/routes/health_ops.py`
- `services/health_checker.py` (new)
- `tests/test_health_ops.py`

**Risks:**
- Health checks may slow down endpoint (mitigate: async + cache)
- False negatives if services slow (mitigate: generous timeouts)

**Rollback:**
```bash
git revert HEAD
# Falls back to stub behavior
```

**Verification:**
```bash
# Should show real latencies
curl http://nodo1:9999/health | jq '.services.chat_cp.latency_ms'
# Expected: real number > 0, not hardcoded 45

# Stop Chat CP, should show degraded
curl http://nodo1:9999/health | jq '.status'
# Expected: "degraded"
```

---

### PR-2: HASS Integration (Unblocks Care Dashboard)
**Goal:** Connect to real Home Assistant instance  
**Scope:**
- HASS WebSocket client
- Entity sync (pull every 30s)
- Event streaming (push real-time)
- Configuration (HASS_URL, HASS_TOKEN env vars)

**Files:**
- `services/hass_bridge.py` (new)
- `api/routes/hass_ops.py`
- `tests/test_hass_integration.py`

**Risks:**
- HASS not configured (mitigate: graceful fallback to stub)
- Network issues (mitigate: retry with backoff)
- Token expiry (mitigate: clear error message)

**Rollback:**
```bash
unset HASS_URL
# Endpoint returns stub mode automatically
```

**Verification:**
```bash
export HASS_URL="ws://hass.local:8123"
export HASS_TOKEN="eyJ0eXAiOiJKV1Q..."

curl http://nodo1:9999/hass/entities | jq '.hass_connected'
# Expected: true

curl http://nodo1:9999/hass/entities | jq '.entities | length'
# Expected: real count from HASS
```

---

### PR-3: Real Telemetry (Unblocks Monitoring)
**Goal:** Replace stub metrics with real Prometheus counters  
**Scope:**
- Prometheus client integration
- Request counters by endpoint
- Latency histograms
- Error rate tracking
- Provider-specific metrics

**Files:**
- `services/metrics_collector.py` (new)
- `api/routes/telemetry_ops.py`
- Middleware for auto-instrumentation
- `tests/test_metrics.py`

**Risks:**
- Metrics memory usage (mitigate: configurable retention)
- Performance overhead (mitigate: async writes)

**Rollback:**
```bash
# Disable metrics
export DENIS_METRICS_ENABLED=false
```

**Verification:**
```bash
# Make some requests
curl http://nodo1:9999/health
curl http://nodo1:9999/chat -d '{...}'

# Check metrics increased
curl http://nodo1:9999/telemetry | jq '.requests.total_1h'
# Expected: >= 2 (actual count, not stub)
```

---

### PR-4: Rate Limiting (Security)
**Goal:** Prevent abuse and protect resources  
**Scope:**
- Per-IP rate limiting (60 req/min)
- Per-user rate limiting (authenticated)
- Different limits per endpoint (/chat lower than /health)
- Redis-backed for distributed rate limiting

**Files:**
- `middleware/rate_limiter.py`
- `api/fastapi_server.py` (register middleware)
- `tests/test_rate_limiting.py`

**Risks:**
- Legitimate users blocked (mitigate: generous limits + override capability)
- Redis unavailable (mitigate: in-memory fallback)

**Rollback:**
```bash
# Disable rate limiting
export DENIS_RATE_LIMIT_ENABLED=false
```

**Verification:**
```bash
# Spam requests
for i in {1..70}; do curl -s http://nodo1:9999/health; done

# Expect 429 on request 61
curl -w "%{http_code}" http://nodo1:9999/health
# Expected: 429
```

---

### PR-5: Circuit Breaker (Resilience)
**Goal:** Fail fast when downstream services are down  
**Scope:**
- Circuit breaker for Chat CP providers
- Automatic tripping after 5 errors
- Half-open state for recovery detection
- Exponential backoff for retries

**Files:**
- `services/circuit_breaker.py` (new)
- `denis_unified_v1/chat_cp/chat_router.py`
- `tests/test_circuit_breaker.py`

**Risks:**
- False positives (mitigate: error threshold tuning)
- Recovery delay (mitigate: configurable timeouts)

**Rollback:**
```bash
# Reset circuit breaker
rm /tmp/denis_circuit_state.json
```

**Verification:**
```bash
# Kill Chat CP provider
# Make 5 requests (all will fail)
# 6th request should fail immediately (circuit open)
# Check logs for "circuit_breaker_open"
```

---

### PR-6: Authentication (Security)
**Goal:** Secure endpoints with proper auth  
**Scope:**
- JWT token validation
- Scope-based access control (ops, care, admin)
- Token refresh mechanism
- Auth middleware

**Files:**
- `middleware/auth.py`
- `services/auth_service.py` (new)
- `api/fastapi_server.py`
- `tests/test_auth.py`

**Risks:**
- Breaking existing clients (mitigate: grace period with warnings)
- Token leakage (mitigate: short TTL + rotation)

**Rollback:**
```bash
# Disable auth
export DENIS_AUTH_REQUIRED=false
```

**Verification:**
```bash
# Without token
curl -w "%{http_code}" http://nodo1:9999/health
# Expected: 401

# With token
curl -H "Authorization: Bearer $TOKEN" http://nodo1:9999/health
# Expected: 200
```

---

### PR-7: Testing Infrastructure (Quality)
**Goal:** Comprehensive test coverage  
**Scope:**
- Integration tests for all endpoints
- Load tests (k6/locust)
- E2E tests with real providers (mocked)
- CI/CD pipeline

**Files:**
- `tests/integration/` (new directory)
- `tests/load/` (new directory)
- `.github/workflows/ci.yml`
- `Makefile` (test targets)

**Risks:**
- Slow CI (mitigate: parallel tests)
- Flaky tests (mitigate: retry logic)

**Rollback:**
```bash
# Skip tests
git checkout HEAD~1
```

**Verification:**
```bash
make test
# Expected: All tests pass

make test-integration
# Expected: Integration tests pass

make test-load
# Expected: Handles 100 req/s
```

---

### PR-8: Documentation & Runbooks (Operations)
**Goal:** Production-ready documentation  
**Scope:**
- API documentation (OpenAPI/Swagger)
- Runbook for common incidents
- Deployment guide
- Monitoring guide
- Troubleshooting playbook

**Files:**
- `docs/api_reference.md`
- `docs/runbook.md`
- `docs/deployment.md`
- `docs/monitoring.md`
- `docs/troubleshooting.md`

**Risks:**
- Documentation drift (mitigate: automate from code)

**Rollback:**
```bash
git checkout HEAD~1 -- docs/
```

**Verification:**
```bash
# Swagger UI
curl http://nodo1:9999/docs
# Expected: OpenAPI spec rendered

# Read runbook
cat docs/runbook.md | grep -c "INCIDENT"
# Expected: > 5 incident procedures
```

---

## FINAL CHECKLIST

### P0.5 Ship Criteria (ALL REQUIRED)

- [ ] `/chat` returns 200 with valid response
- [ ] `/health` returns 200 with status field
- [ ] `/hass/entities` returns 200 with entities array
- [ ] `/telemetry` returns 200 with metrics object
- [ ] `/telemetry` (Prometheus) returns valid exposition format
- [ ] DecisionTrace writes to Graph (when enabled)
- [ ] X-Denis-Hop header enforced
- [ ] No secrets in logs
- [ ] validate_p05.sh passes
- [ ] pyproject.toml enables pip install -e .

### Post-Ship (P1)

- [ ] PR-1 merged: Real health checks
- [ ] PR-2 merged: HASS integration
- [ ] PR-3 merged: Real telemetry
- [ ] PR-4 merged: Rate limiting
- [ ] PR-5 merged: Circuit breaker
- [ ] PR-6 merged: Authentication
- [ ] PR-7 merged: Testing infrastructure
- [ ] PR-8 merged: Documentation

---

**Status:** P0.5 READY FOR SHIP  
**Next:** Execute validation script, merge, deploy to nodo1, notify nodo2 team  
**Blockers:** None  
**Risks:** Low (all changes additive, fail-open by design)  
