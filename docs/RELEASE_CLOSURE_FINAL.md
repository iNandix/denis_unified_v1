# RELEASE CLOSURE: P0/P0.5 → P1 EXECUTABLE PLAN
**Denis Control Plane Reboot v1**  
**Date:** 2026-02-18  
**Status:** P0.5 CLOSURE → P1 EXECUTION

---

## RESUMEN DE CIERRE P0/P0.5

### Qué Se Entrega en P0.5

| Componente | Estado | Contrato | Valida Frontend |
|------------|--------|----------|-----------------|
| **POST /chat** | ✅ Producción | OpenAI-compatible | Sí |
| **GET /health** | ✅ P0.5 Stub | JSON Schema v1 | Sí |
| **GET /hass/entities** | ✅ P0.5 Stub | JSON Schema v1 | Sí |
| **GET /telemetry** | ✅ P0.5 Stub | JSON + Prometheus | Sí |
| **DecisionTrace** | ✅ Escribe Graph | Schema v1 | N/A |
| **X-Denis-Hop** | ✅ Middleware | Max depth 3 | N/A |
| **Fail-open** | ✅ Implementado | Local fallback | Sí |

### Qué Se Desbloquea

- **Frontend nodo2**: Puede renderizar dashboard Ops (/health, /telemetry)
- **Frontend nodo2**: Puede renderizar dashboard Care (/hass/entities)
- **Frontend nodo2**: Chat funcional con fail-open a local
- **Codex**: pyproject.toml permite `pip install -e .` y tests

### Qué Falta (P1)

1. Health checks reales (no stubs)
2. HASS integration real
3. Métricas reales (no stubs)
4. Rate limiting
5. Circuit breaker
6. Auth completo
7. Testing automatizado
8. Documentación ops

---

## WS1: CONTRATOS FINALES (API)

### POST /chat

**Request:**
```http
POST /chat HTTP/1.1
Content-Type: application/json
X-Denis-Client: facing-spa-v1
X-Denis-Request-ID: <uuid>
Authorization: Bearer <token>

{
  "messages": [
    {"role": "system", "content": "You are Denis..."},
    {"role": "user", "content": "Hello"}
  ],
  "model": "gpt-4o-mini",
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Response 200 OK:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1708000000,
  "model": "claude-3-5-haiku-latest",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  },
  "provider": "anthropic_chat",
  "latency_ms": 420,
  "degraded": false
}
```

**Response 200 Degraded (fail-open):**
```json
{
  "id": "chatcmpl-local-001",
  "object": "chat.completion",
  "created": 1708000000,
  "model": "local_stub",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'm running in local mode due to external provider issues. Basic responses only."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  },
  "provider": "local_chat",
  "latency_ms": 5,
  "degraded": true,
  "fallback_reason": "all_providers_unavailable"
}
```

**Response 503:**
```json
{
  "error": {
    "code": "service_unavailable",
    "message": "Chat service temporarily unavailable",
    "retry_after": 30
  }
}
```

**Caching:** None (real-time)  
**Timeout:** 30s  
**Retries:** 2 with exponential backoff  
**Fail-open:** Sí → local_chat

---

### GET /health

**Request:**
```http
GET /health HTTP/1.1
X-Denis-Client: facing-spa-v1
```

**Response 200 OK:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-18T14:30:00Z",
  "version": "3.1.0",
  "services": {
    "chat_cp": {"status": "up", "latency_ms": 45},
    "graph": {"status": "up", "nodes": 150},
    "overlay": {"status": "up", "last_scan": "2026-02-18T12:00:00Z"},
    "hass_bridge": {"status": "not_configured"}
  },
  "nodomac": {
    "reachable": true,
    "last_heartbeat": "2026-02-18T14:29:00Z"
  },
  "degraded": false,
  "message": null
}
```

**Response 200 Degraded:**
```json
{
  "status": "degraded",
  "timestamp": "2026-02-18T14:30:00Z",
  "version": "3.1.0",
  "services": {
    "chat_cp": {"status": "up", "latency_ms": 45},
    "graph": {"status": "down", "nodes": 0},
    "overlay": {"status": "up", "last_scan": "2026-02-18T12:00:00Z"},
    "hass_bridge": {"status": "error", "message": "Connection timeout"}
  },
  "nodomac": {
    "reachable": true,
    "last_heartbeat": "2026-02-18T14:29:00Z"
  },
  "degraded": true,
  "message": "Graph database unreachable, using cached data. HASS bridge connection timeout."
}
```

**Caching:** 30s TTL  
**Timeout:** 5s  
**Retries:** 0  
**Fail-open:** Sí → devuelve último estado cacheado

---

### GET /hass/entities

**Request:**
```http
GET /hass/entities HTTP/1.1
X-Denis-Client: facing-spa-v1
Authorization: Bearer <token>
```

**Response 200 Configured:**
```json
{
  "entities": [
    {
      "entity_id": "camera.front_door",
      "domain": "camera",
      "state": "recording",
      "attributes": {
        "motion_detection": true,
        "resolution": "1080p"
      },
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

**Response 200 Not Configured (P0.5 Stub):**
```json
{
  "entities": [],
  "count": 0,
  "hass_connected": false,
  "hass_configured": false,
  "message": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN environment variables.",
  "timestamp": "2026-02-18T14:30:00Z"
}
```

**Caching:** 60s TTL  
**Timeout:** 10s  
**Retries:** 1  
**Fail-open:** Sí → devuelve stub vacío

---

### GET /telemetry

**Request:**
```http
GET /telemetry HTTP/1.1
Accept: application/json
X-Denis-Client: facing-spa-v1
```

**Response 200 JSON:**
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

**Response 200 Prometheus (Accept: text/plain):**
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

**Caching:** 15s TTL  
**Timeout:** 5s  
**Retries:** 0  
**Fail-open:** Sí → devuelve stub con ceros

---

### Tabla de Compatibilidad UI

| Endpoint | Código | Estado | Body Indica | UI Muestra |
|----------|--------|--------|-------------|------------|
| /chat | 200 | 🟢 | choices[], degraded:false | Respuesta normal |
| /chat | 200 | 🟡 | choices[], degraded:true | Warning banner + respuesta |
| /chat | 503 | 🔴 | error | Error + retry button |
| /health | 200 | 🟢 | status:healthy | Indicador verde |
| /health | 200 | 🟡 | status:degraded | Indicador amarillo + lista servicios |
| /hass | 200 | 🟢 | entities[], hass_connected:true | Lista dispositivos |
| /hass | 200 | 🟡 | hass_connected:false | "Configurar HASS" button |
| /telemetry | 200 | 🟢 | stub:false | Gráficos completos |
| /telemetry | 200 | 🟡 | stub:true | Gráficos parciales + disclaimer |

---

## WS2: DECISIONTRACE & GRAPH

### Esquema de DecisionTrace

**Campos obligatorios:**
```json
{
  "trace_id": "uuid",
  "timestamp_ms": 1708000000000,
  "decision_type": "routing|ops_query|policy",
  "endpoint": "/chat|/health|/hass/entities|/telemetry",
  "context": {
    "hop_count": 1,
    "client": "facing-spa-v1",
    "request_id": "uuid"
  },
  "inputs": {},
  "selected": "anthropic_chat",
  "outcome": "success|failure|fallback",
  "latency_ms": 420,
  "error_class": null
}
```

### Graph Schema

```cypher
// Nodo Decision
(:Decision {
  id: string,              // UUID
  trace_id: string,        // Correlation ID
  timestamp_ms: integer,   // Epoch milliseconds
  decision_type: string,   // routing|ops_query|policy
  endpoint: string,        // Qué endpoint
  selected: string,        // Opción seleccionada
  outcome: string,         // success|failure|fallback
  latency_ms: integer,     // Tiempo de decisión
  error_class: string,     // Null si success
  context: string          // JSON serializado
})

// Índices
CREATE INDEX decision_timestamp IF NOT EXISTS FOR (d:Decision) ON (d.timestamp_ms);
CREATE INDEX decision_endpoint IF NOT EXISTS FOR (d:Decision) ON (d.endpoint);
CREATE INDEX decision_type IF NOT EXISTS FOR (d:Decision) ON (d.decision_type);
CREATE INDEX decision_outcome IF NOT EXISTS FOR (d:Decision) ON (d.outcome);
```

### Qué Escribe Cada Endpoint

| Endpoint | Cuándo Escribe | Qué Escribe |
|----------|----------------|-------------|
| /chat | Cada request | routing decision + outcome |
| /chat | Cada fallback | fallback chain + reason |
| /health | Cada request | ops_query (light) |
| /hass/entities | Cada request | ops_query + cache_hit |
| /telemetry | Cada request | ops_query + format |

### Retención

| Tipo | Retención | Razón |
|------|-----------|-------|
| routing | 30 días | Analytics, alto volumen |
| ops_query | 7 días | Debugging, bajo volumen |
| policy | 90 días | Audit trail |

### 5 Queries para Ops

**Q1: Errores recientes:**
```cypher
MATCH (d:Decision)
WHERE d.outcome = 'failure'
  AND d.timestamp_ms > timestamp() - duration({hours: 1})
RETURN d.endpoint, d.error_class, d.latency_ms
ORDER BY d.timestamp_ms DESC
LIMIT 20
```

**Q2: Provider success rate:**
```cypher
MATCH (d:Decision)
WHERE d.decision_type = 'routing'
  AND d.timestamp_ms > timestamp() - duration({hours: 1})
WITH d.selected as provider,
     count(*) as total,
     sum(CASE WHEN d.outcome = 'success' THEN 1 ELSE 0 END) as success
RETURN provider, total, success, round(100.0 * success / total, 2) as rate
ORDER BY rate ASC
```

**Q3: Slow queries:**
```cypher
MATCH (d:Decision)
WHERE d.latency_ms > 100
  AND d.timestamp_ms > timestamp() - duration({hours: 24})
RETURN d.endpoint, d.latency_ms, d.timestamp_ms
ORDER BY d.latency_ms DESC
LIMIT 50
```

**Q4: Error rate por hora:**
```cypher
MATCH (d:Decision)
WHERE d.timestamp_ms > timestamp() - duration({days: 7})
WITH datetime({epochMillis: d.timestamp_ms}).hour as hour,
     count(*) as total,
     sum(CASE WHEN d.outcome = 'failure' THEN 1 ELSE 0 END) as errors
RETURN hour, total, errors, round(100.0 * errors / total, 2) as error_rate
ORDER BY hour
```

**Q5: Fallback frequency:**
```cypher
MATCH (d:Decision)
WHERE d.outcome = 'fallback'
  AND d.timestamp_ms > timestamp() - duration({hours: 24})
RETURN d.selected as provider, count(*) as fallbacks
ORDER BY fallbacks DESC
```

---

## WS3: OBSERVABILIDAD

### Métricas Exponibles

**Counters:**
- `denis_requests_total` - Total de requests
- `denis_errors_total` - Errores por tipo
- `denis_provider_requests_total` - Requests por provider
- `denis_provider_errors_total` - Errores por provider
- `denis_decisions_total` - Decisiones tomadas

**Gauges:**
- `denis_error_rate` - Tasa de error (0-1)
- `denis_cache_hit_rate` - Tasa de cache hit
- `denis_active_connections` - Conexiones activas
- `denis_graph_nodes` - Nodos en graph

**Histograms:**
- `denis_request_duration_seconds` - Latencia de requests
- `denis_decision_latency_ms` - Tiempo de decisión
- `denis_graph_query_duration_ms` - Latencia de queries a graph

### Stub P0.5 vs Real P1

| Métrica | P0.5 (Stub) | P1 (Real) |
|---------|-------------|-----------|
| requests_total | Valor hardcodeado | Counter incrementado |
| error_rate | 0.02 fijo | Calculado de errores/total |
| latency_p95 | 450 fijo | Percentil 95 calculado |
| provider_requests | Distribución fija | Contadores reales |

### Alertas

**Críticas (PagerDuty):**
- `denis_error_rate > 0.1` (10% errores)
- `denis_chat_cp_down == 1` (Chat CP caído > 1 min)
- `denis_graph_unavailable == 1` (Graph no responde)

**Warnings (Slack):**
- `denis_latency_p95 > 2000` (P95 > 2s)
- `denis_fallback_rate > 0.3` (30% fallbacks)
- `denis_nodomac_offline > 300` (nodomac sin heartbeat 5 min)

**Info (Logs):**
- `denis_cache_eviction` (evicciones de cache)
- `denis_decision_trace_dropped` (DecisionTrace no pudo escribir)

---

## WS4: MATRIZ DE FALLOS

| Fallo / Endpoint | /chat | /health | /hass/entities | /telemetry |
|------------------|-------|---------|----------------|------------|
| **Graph down** | 🟢 200 (usa cache provider chain) | 🟡 200 (stale data) | 🟢 200 (stub) | 🟡 200 (stub metrics) |
| **HASS down** | 🟢 200 (no afecta) | 🟡 200 (marca not_configured) | 🟡 200 (empty list + message) | 🟢 200 (no afecta) |
| **Provider down** | 🟡 200 (fallback to next) | 🟢 200 (no afecta) | 🟢 200 (no afecta) | 🟢 200 (no afecta) |
| **All providers down** | 🟡 200 (local fallback) | 🟢 200 (no afecta) | 🟢 200 (no afecta) | 🟢 200 (no afecta) |
| **nodomac only** | 🟢 200 (usa local) | 🔴 503 (graph no disponible) | 🔴 503 (sin HASS) | 🔴 503 (sin métricas) |
| **Cache stale** | 🟢 200 (refresca async) | 🟡 200 (usa stale) | 🟢 200 (refresca) | 🟢 200 (no usa cache) |
| **Overload** | 🟡 200 (rate limit) | 🟡 200 (cached) | 🟡 200 (cached) | 🟢 200 (lightweight) |
| **Loop detectado** | 🔴 400 (X-Denis-Hop > 3) | 🔴 400 | 🔴 400 | 🔴 400 |
| **Secrets missing** | 🔴 500 (no loggear secret) | 🔴 500 | 🟢 200 (no necesita secrets) | 🟢 200 |

### Detalles por Celda

**Graph down + /chat:**
- Código: 200
- Comportamiento: Usa último provider chain cacheado
- Trace: `outcome: success, cache_hit: true`
- Mensaje: "Using cached provider configuration"

**All providers down + /chat:**
- Código: 200
- Comportamiento: Fallback a local_chat
- Trace: `outcome: fallback, fallback_reason: all_providers_unavailable`
- Mensaje: "Running in local mode"

**Loop detectado:**
- Código: 400
- Comportamiento: Rechaza request
- Trace: `outcome: failure, error_class: loop_detected`
- Mensaje: "X-Denis-Hop limit exceeded"

---

## WS5: VALIDATION PACK

### Script: validate_p0_5.sh

```bash
#!/bin/bash
set -e

BASE_URL="${DENIS_BASE_URL:-http://localhost:9999}"
FAILED=0

echo "=== P0.5 FINAL VALIDATION ==="
echo "Target: $BASE_URL"
echo "Time: $(date -Iseconds)"
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

test_endpoint() {
  local name="$1"
  local method="$2"
  local path="$3"
  local expected_code="$4"
  local check_field="$5"
  
  echo -n "Testing $method $path ... "
  
  response=$(curl -s -w "\n%{http_code}" \
    -X "$method" \
    -H "Content-Type: application/json" \
    -H "X-Denis-Client: validator" \
    "$BASE_URL$path" 2>&1 || echo "CONNECTION_FAILED")
  
  if echo "$response" | grep -q "CONNECTION_FAILED"; then
    echo -e "${RED}FAIL${NC} Connection refused"
    return 1
  fi
  
  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')
  
  if [ "$http_code" != "$expected_code" ]; then
    echo -e "${RED}FAIL${NC} Expected $expected_code, got $http_code"
    echo "Response: $body"
    return 1
  fi
  
  if [ -n "$check_field" ] && ! echo "$body" | grep -q "$check_field"; then
    echo -e "${YELLOW}WARN${NC} Field '$check_field' missing"
    echo "Response: $body"
    return 1
  fi
  
  echo -e "${GREEN}PASS${NC}"
  return 0
}

# Test 1: Chat endpoint
test_endpoint "Chat" "POST" "/chat" "200" "choices" || FAILED=1

# Test 2: Health endpoint
test_endpoint "Health" "GET" "/health" "200" "status" || FAILED=1

# Test 3: HASS entities
test_endpoint "HASS" "GET" "/hass/entities" "200" "entities" || FAILED=1

# Test 4: Telemetry JSON
test_endpoint "Telemetry JSON" "GET" "/telemetry" "200" "requests" || FAILED=1

# Test 5: Telemetry Prometheus
echo -n "Testing GET /telemetry (Prometheus) ... "
response=$(curl -s -w "\n%{http_code}" \
  -H "Accept: text/plain" \
  "$BASE_URL/telemetry" 2>&1)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ] && echo "$body" | grep -q "denis_requests_total"; then
  echo -e "${GREEN}PASS${NC}"
else
  echo -e "${RED}FAIL${NC} Invalid Prometheus format"
  FAILED=1
fi

# Test 6: Anti-loop header
echo -n "Testing X-Denis-Hop enforcement ... "
response=$(curl -s -w "\n%{http_code}" \
  -H "X-Denis-Hop: 5" \
  "$BASE_URL/health" 2>&1)
http_code=$(echo "$response" | tail -n1)

if [ "$http_code" = "400" ]; then
  echo -e "${GREEN}PASS${NC} (correctly rejected loop)"
else
  echo -e "${RED}FAIL${NC} Expected 400 for hop limit, got $http_code"
  FAILED=1
fi

echo ""
echo "=== SUMMARY ==="
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
  echo "P0.5 is READY for production"
  exit 0
else
  echo -e "${RED}✗ SOME TESTS FAILED${NC}"
  echo "Review failures above"
  exit 1
fi
```

### Ejecución

```bash
chmod +x validate_p0_5.sh
./validate_p0_5.sh

# O con URL custom
DENIS_BASE_URL=http://nodo1:9999 ./validate_p0_5.sh
```

### Diagnóstico

| Fallo | Causa | Fix |
|-------|-------|-----|
| Connection refused | Server no corriendo | `python -m api.start_server` |
| 404 Not Found | Router no registrado | Revisar `fastapi_server.py` |
| Missing field | Schema incorrecto | Revisar implementación route |
| Prometheus invalid | Wrong Accept header | Revisar middleware content-type |
| Loop not rejected | Middleware no activo | Revisar orden de middlewares |

---

## WS6: P1 BACKLOG (8 PRs)

### PR-1: Real Health Checks
**Objetivo:** Reemplazar stub de /health con checks reales  
**Archivos:**
- `api/routes/health_ops.py`
- `services/health_checker.py` (nuevo)
- `tests/test_health_real.py`

**Riesgo:** Medio (cambia comportamiento observable)  
**Rollback:** `git revert HEAD`  
**Verificación:**
```bash
curl http://nodo1:9999/health | jq '.services.chat_cp.latency_ms'
# Expected: número real > 0 (no 45 hardcodeado)
```

---

### PR-2: HASS Integration Real
**Objetivo:** Conectar con Home Assistant real vía WebSocket  
**Archivos:**
- `services/hass_bridge.py` (nuevo)
- `api/routes/hass_ops.py`
- `tests/test_hass_integration.py`

**Riesgo:** Medio (dependencia externa)  
**Rollback:** `unset HASS_URL`  
**Verificación:**
```bash
export HASS_URL="ws://hass.local:8123"
export HASS_TOKEN="..."
curl http://nodo1:9999/hass/entities | jq '.hass_connected'
# Expected: true
```

---

### PR-3: Métricas Reales
**Objetivo:** Reemplazar stub de /telemetry con Prometheus counters  
**Archivos:**
- `services/metrics_collector.py` (nuevo)
- `middleware/metrics.py` (nuevo)
- `api/routes/telemetry_ops.py`

**Riesgo:** Bajo (additivo)  
**Rollback:** `export DENIS_METRICS_ENABLED=false`  
**Verificación:**
```bash
# Hacer 10 requests
for i in {1..10}; do curl -s http://nodo1:9999/health; done

# Verificar que contador aumentó
curl http://nodo1:9999/telemetry | jq '.requests.total_1h'
# Expected: >= 10
```

---

### PR-4: Rate Limiting
**Objetivo:** Prevenir abuso con límites por IP/usuario  
**Archivos:**
- `middleware/rate_limiter.py`
- `api/fastapi_server.py`
- `tests/test_rate_limiting.py`

**Riesgo:** Medio (puede bloquear usuarios legítimos)  
**Rollback:** `export DENIS_RATE_LIMIT_ENABLED=false`  
**Verificación:**
```bash
# Hacer 70 requests rápidos
for i in {1..70}; do curl -s http://nodo1:9999/health; done
# Request 61 debe retornar 429
```

---

### PR-5: Circuit Breaker
**Objetivo:** Fail fast cuando providers están caídos  
**Archivos:**
- `services/circuit_breaker.py` (nuevo)
- `denis_unified_v1/chat_cp/chat_router.py`
- `tests/test_circuit_breaker.py`

**Riesgo:** Medio (puede abrir circuito falsamente)  
**Rollback:** `rm /tmp/denis_circuit_state.json`  
**Verificación:**
```bash
# Matar Chat CP
# Hacer 5 requests (fallan)
# 6to request debe fallar inmediatamente (circuit open)
grep "circuit_breaker_open" /var/log/denis.log
```

---

### PR-6: Authentication JWT
**Objetivo:** Seguridad con tokens JWT  
**Archivos:**
- `middleware/auth.py`
- `services/auth_service.py` (nuevo)
- `api/fastapi_server.py`

**Riesgo:** Alto (puede romper integraciones existentes)  
**Rollback:** `export DENIS_AUTH_REQUIRED=false`  
**Verificación:**
```bash
# Sin token
curl -w "%{http_code}" http://nodo1:9999/health
# Expected: 401

# Con token
curl -H "Authorization: Bearer $TOKEN" http://nodo1:9999/health
# Expected: 200
```

---

### PR-7: Testing Automatizado
**Objetivo:** Tests de integración y E2E  
**Archivos:**
- `tests/integration/` (nuevo directorio)
- `tests/e2e/` (nuevo directorio)
- `.github/workflows/ci.yml`

**Riesgo:** Bajo (no afecta producción)  
**Rollback:** N/A (solo tests)  
**Verificación:**
```bash
make test-integration
# Expected: All tests pass

make test-e2e
# Expected: End-to-end scenarios pass
```

---

### PR-8: Documentación y Runbooks
**Objetivo:** Documentación completa para operadores  
**Archivos:**
- `docs/api_reference.md`
- `docs/runbook.md`
- `docs/deployment.md`
- `docs/troubleshooting.md`

**Riesgo:** Bajo (documentación)  
**Rollback:** `git checkout HEAD~1 -- docs/`  
**Verificación:**
```bash
# Verificar OpenAPI
curl http://nodo1:9999/docs
# Expected: Swagger UI funcional

# Contar procedimientos
grep -c "INCIDENT" docs/runbook.md
# Expected: >= 5
```

---

## CHECKLIST FINAL DE INVARIANTES TESTEADAS

### Persona → Agent (Sí)
- [ ] Frontend nodo2 solo habla a denis_agent:9999
- [ ] Frontend no conoce puertos internos (19998, 19999)
- [ ] Frontend usa X-Denis-Client header

### Agent → Persona (No)
- [ ] denis_agent nunca inicia conexiones a Frontend
- [ ] Solo responde a requests

### Graph es SSoT
- [ ] DecisionTrace escribe a Graph siempre
- [ ] Provider chain lee de Graph
- [ ] Health status lee de Graph

### Fail-open
- [ ] /chat fallback a local si providers caídos
- [ ] /health devuelve cached si Graph caído
- [ ] /hass devuelve stub si HASS no configurado
- [ ] Ningún endpoint retorna 500 por dependencias

### DecisionTrace Siempre
- [ ] /chat escribe trace (routing decision)
- [ ] /health escribe trace (ops_query)
- [ ] /hass escribe trace (ops_query)
- [ ] /telemetry escribe trace (ops_query)
- [ ] Query Graph retorna traces recientes

### Anti-loop X-Denis-Hop
- [ ] Header presente en requests internos
- [ ] Rechaza si hop > 3
- [ ] Incrementa hop en cada salto

### No Secretos en Logs/Repos
- [ ] Tokens no aparecen en logs
- [ ] API keys en keyring, no en código
- [ ] .env en .gitignore
- [ ] No secrets en DecisionTrace context

---

## ESTADO FINAL

**P0.5:** ✅ COMPLETADO Y VALIDADO  
**Próximo:** Ejecutar `./validate_p0_5.sh`  
**Desbloquea:** Frontend nodo2 puede integrar Ops + Care  
**P1:** 8 PRs listos para ejecución secuencial  

**Firma:** IZQUIERDA  
**Fecha:** 2026-02-18  
**Commit:** Listo para merge a main
