# WS2 — CAPACITY LIMITS & DEGRADATION ACTIONS

## Tabla de Límites → Acción → Señal → UI

| Recurso | Límite Soft | Límite Hard | Acción | Señal | Mensaje UI |
|---------|-------------|-------------|--------|-------|------------|
| **Cola tools_mut** | 200 jobs | 500 jobs | Alertar + auto-scale workers | `celery.queue.tools_mut.len` | "Alta demanda, tiempo estimado mayor" |
| **Cola tools_ro** | 500 jobs | 1000 jobs | Drop oldest, requeue | `celery.queue.tools_ro.len` | "Procesando en background" |
| **Cola graph_ingest** | 500 jobs | 2000 jobs | Batch writes, skip non-critical | `celery.queue.graph_ingest.len` | "Actualización de contexto tardía" |
| **Writes Graph/min** | 400 | 1500 | Circuit breaker + batch | `neo4j.write.latency_p99` | "某些操作延迟" (_ops delayed_) |
| **Reads Graph/min** | 2000 | 5000 | Cache aggressively | `neo4j.read.latency_p99` | — |
| **DecisionTrace queue** | 1000 | 5000 | Drop trace, log locally | `decisiontrace.queue_len` | — |
| **Redis memory** | 1GB | 2GB | Evict rate limit state | `redis.memory_percent` | "Rate limits reset" |
| **Concurrent /chat** | 300 | 500 | Shed load 503 | `api.concurrent_sessions` | "Servidor ocupado, intente más tarde" |
| **WebSocket queue** | 50 | 200 | Drop frames | `ws.queue_len` | "Audio quality reduced" |
| **Art retention** | 1000 | 5000 | Auto-delete oldest | `artifacts.count` | — |

---

## Acciones de Degradación

### Nivel 1 — Graceful Degradation

| Trigger | Acción | Recovery |
|---------|--------|----------|
| Neo4j p99 > 2s | Skip DecisionTrace, usar in-memory | Auto cuando p99 < 1s |
| Redis p99 > 50ms | Fallback in-memory rate limit | Auto cuando Redis healthy |
| Workers busy > 80% | Queue `tools_ro` to `housekeeping` | Auto cuando queue < 50% |
| /chat p99 > 8s | Reducir candidatos de tool selection | Auto cuando p99 < 5s |

### Nivel 2 — Hard Limit

| Trigger | Acción | Recovery |
|---------|--------|----------|
| Cola tools_mut > 500 | 503 + retry-after | Manual clear o scale |
| Redis down | Fail-open total, sin rate limit | Manual restart |
| Neo4j down | Modo legacy (sin graph) | Manual restart |
| Memory > 90% | OOM killer prevention: kill workers | Manual intervention |

### Nivel 3 — Circuit Breaker

| Componente | Fallas consecutively | Timeout | Acción |
|------------|---------------------|---------|--------|
| Neo4j | 5 | 30s | Skip all graph ops |
| Redis | 3 | 60s | Use in-memory only |
| Inference engine | 3 | 120s | Fallback to next engine |
| External API | 5 | 60s | Return cached or error |

---

## Rate Limiting Actual (del código)

```python
# Default: 100 requests / 60s per client
# Gate: 10 RPS
, burst 20# API Gateway: 100 RPM read, 50 RPM write
```

**Recomendación nuevos límites:**

| Endpoint | Rate | Window | Burst |
|----------|------|--------|-------|
| /chat | 60 | 60s | 100 |
| /chat (authenticated) | 200 | 60s | 300 |
| /internal/* | 1000 | 60s | 2000 |
| /telemetry | 5000 | 60s | 10000 |

---

## Artifacts Retention

| Tipo | Retención | Max Size | Acción al límite |
|------|-----------|----------|------------------|
| DecisionTrace | 7 días | 50MB | Delete oldest |
| Chat history | 30 días | 100MB | Archive to cold storage |
| TTS audio | 24h | 10GB | Delete immediately |
| Tool logs | 7 días | 1GB | Compress + delete |

---

## Memory Limits

| Componente | Soft | Hard | OOM Action |
|-----------|------|------|-------------|
| API worker | 1GB | 2GB | Graceful shutdown + respawn |
| Celery worker | 512MB | 1GB | Kill task + respawn |
| Redis | 2GB | 4GB | Evict + alert |
| Neo4j (JVM) | 4GB | 8GB | Query kill + alert |
