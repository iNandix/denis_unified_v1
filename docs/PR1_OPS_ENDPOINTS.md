# PR-1 Implementation Summary: Ops Endpoints

## Overview
Implementation of 3 Ops endpoints to unblock Frontend (Care/Ops dashboards).

## Files Created/Modified

### New Files
1. `api/routes/health_ops.py` - GET /health endpoint
2. `api/routes/hass_ops.py` - GET /hass/entities endpoint
3. `api/routes/telemetry_ops.py` - GET /telemetry endpoint
4. `scripts/validate_pr1_ops.sh` - Validation script

### Modified Files
1. `api/fastapi_server.py` - Registered 3 new routers
2. `denis_unified_v1/chat_cp/graph_trace.py` - Added maybe_write_decision_trace()

## Endpoints Implemented

### GET /health
Returns system health status (P0 stub).

**Response:**
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
  }
}
```

### GET /hass/entities
Returns Home Assistant entities (P0 stub with hardcoded data).

**Response:**
```json
{
  "entities": [
    {
      "entity_id": "camera.front_door",
      "domain": "camera",
      "state": "recording",
      "attributes": {"motion_detection": true, "resolution": "1080p"},
      "last_updated": "2026-02-18T14:25:00Z"
    }
  ],
  "count": 3,
  "hass_connected": false,
  "timestamp": "2026-02-18T14:30:00Z"
}
```

### GET /telemetry
Returns metrics in JSON or Prometheus format.

**JSON Response (default):**
```json
{
  "requests": {
    "total_1h": 1250,
    "error_rate_1h": 0.02,
    "latency_p95_ms": 450
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
  "timestamp": "2026-02-18T14:30:00Z"
}
```

**Prometheus Response (Accept: text/plain):**
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
```

## DecisionTrace

All endpoints write DecisionTrace to Graph (if DENIS_CHAT_CP_GRAPH_WRITE=1):

```json
{
  "trace_id": "uuid",
  "endpoint": "/health",
  "decision_type": "ops_query",
  "outcome": "success",
  "latency_ms": 15,
  "context": {
    "sources_queried": ["memory"],
    "cache_hit": true
  }
}
```

## Validation

### Run Tests
```bash
chmod +x scripts/validate_pr1_ops.sh
./scripts/validate_pr1_ops.sh
```

### Expected Output
```
=== PR-1 Validation: Ops Endpoints ===

Test 1: GET /health
✅ Status: 200 OK
✅ Required fields present

Test 2: GET /hass/entities
✅ Status: 200 OK
✅ Required fields present
Entity count: 3

Test 3: GET /telemetry (JSON)
✅ Status: 200 OK
✅ Required fields present

Test 4: GET /telemetry (Prometheus format)
✅ Status: 200 OK
✅ Prometheus format valid

=== All tests passed! ===
```

### Verify DecisionTrace
```bash
# Enable graph writes
export DENIS_CHAT_CP_GRAPH_WRITE=1

# Run a request
curl http://localhost:9999/health

# Query graph
cypher-shell -u neo4j -p password "MATCH (d:Decision) WHERE d.endpoint = '/health' RETURN count(d)"
```

## Invariantes Cumplidas

✅ **Fail-open**: Si Graph no disponible, endpoints funcionan igual
✅ **No secretos**: No se loggean secrets en ningún endpoint
✅ **DecisionTrace**: Todos escriben trace si está habilitado
✅ **Persona→Agent**: Frontend (Persona) → denis_agent (Agent) → Servicios
✅ **P0 válido**: Stubs funcionales que evolucionan a P1

## Próximos Pasos (P1)

1. **PR-2**: Health checks reales (ping a servicios)
2. **PR-3**: HASS integration (WebSocket a HASS real)
3. **PR-4**: Métricas reales (Prometheus client)

## Estado

✅ **READY FOR TESTING**

Endpoints implementados y registrados en FastAPI.
Frontend puede comenzar integración inmediata.
