# WS3 — FAILURE CONTAINMENT ZONES

## Mapa de Zonas

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                       │
│  (WebSocket /chat, Voice UI, Telemetry Display)                        │
│  ─────────────────────────────────────────────────────────────────────── │
│  FAIL: UI freeze, audio choppy                                          │
│  CONTAIN: Reconnect automático, fallback a polling                     │
│  NO PROPAGATE: Fallos backend → user-friendly messages                  │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP/WS
┌─────────────────────────────────▼───────────────────────────────────────┐
│                         SYNC PLANE                                       │
│  /chat endpoint (FastAPI) + Rate Limiting + Gates                      │
│  ─────────────────────────────────────────────────────────────────────── │
│  COMPONENTES:                                                            │
│    • service_8084.py (main chat)                                        │
│    • rate_limiting.py (Redis-first, fallback in-memory)                 │
│    • gates/ (budget, injection detection)                              │
│                                                                          │
│  FAIL: Timeout, 429, 500                                                │
│  CONTAIN: Retry-after header, fallback mode                            │
│  PROPAGA A: Async plane (via Celery), Graph (queries)                  │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ Celery / Direct
┌─────────────────────────────────▼───────────────────────────────────────┐
│                       ASYNC PLANE                                        │
│  Celery workers + File-based queue backend                              │
│  ─────────────────────────────────────────────────────────────────────── │
│  COLAS:                                                                  │
│    • tools_ro (read-only, reintentable)                                 │
│    • tools_mut (mutating, alta prioridad)                               │
│    • tts (voice, batch-able)                                            │
│    • graph_ingest (puede batch)                                         │
│    • ha_playback (low pri)                                              │
│    • housekeeping (background)                                          │
│                                                                          │
│  FAIL: Job stuck, worker down, queue growing                            │
│  CONTAIN: Dead letter queue, max retries, timeout                      │
│  PROPAGA A: Graph (writes), Redis (state), External APIs               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ Bolt / HTTP
┌─────────────────────────────────▼───────────────────────────────────────┐
│                          GRAPH                                           │
│  Neo4j + DecisionTrace                                                   │
│  ─────────────────────────────────────────────────────────────────────── │
│  USOS:                                                                   │
│    • Intent resolution                                                   │
│    • Tool routing                                                        │
│    • DecisionTrace (fire-and-forget)                                    │
│    • Policy storage                                                      │
│                                                                          │
│  FAIL: Query timeout, connection pool exhausted, write queue            │
│  CONTAIN: Fail-open (legacy mode), circuit breaker                      │
│  NO PROPAGA: Silently skip, usar cache local                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Zona 1: SYNC PLANE

### Qué puede romperse

| Componente | Modo de fallo | Señal |
|------------|---------------|-------|
| Rate limiter | Redis down → memory fallback | `rate_limit.redis_down` |
| Gate budget | Budget exceeded | `gate.budget_exceeded` |
| Injection detection | False positive block | `gate.injection_blocked` |
| /chat endpoint | Timeout > 15s | `chat.timeout` |
| WebSocket | Connection drop | `ws.disconnect_rate` |

### Cómo se contiene

```
[Request] → Rate Limit → Budget Check → Injection Check → [OK]
                                      ↓
                              [BLOCK] → 403 + reason
                                      ↓
[Timeout > 15s] → 408 + retry-after
```

- **Rate limit**: Fail-open → in-memory TTL
- **Budget**: Block + mensaje claro
- **Timeout**: 408 + suggest retry
- **Circuit breaker**: Si 5 errores consecutivos → fallback mode

### Qué NO debe propagarse

- Errores de rate limiting user → no debe romper /chat
- Fallos de gates → response clara, no 500
- Timeout → no debe dejar request colgada

---

## Zona 2: ASYNC PLANE

### Qué puede romperse

| Componente | Modo de fallo | Señal |
|------------|---------------|-------|
| Celery broker | Redis down | `celery.broker_down` |
| Worker | OOM, hung, crash | `celery.worker_down` |
| Queue | Growing unbounded | `celery.queue.len` |
| Job | Timeout, max retries | `celery.task.failed` |
| File queue | Disk full | `queue.disk_percent` |

### Cómo se contiene

```
[Job dispatch] → Check broker → [OK] → Queue job
                              ↓
              [Broker down] → Run sync (fail-open!)
                              ↓
[Job timeout] → Retry N → Dead letter → Alert
```

- **Fail-open**: Si Celery down → ejecutar sync (`dispatch_snapshot_hass()`)
- **Max retries**: 3 para tools_mut, 1 para tools_ro
- **Timeout**: 5 min por job
- **Dead letter**: Jobs fallen > 5 veces →cola separada

### Qué NO debe propagarse

- Worker crash → no debe tumbar API
- Job failure → no debe dar 500 al usuario
- Queue llena → no debe bloquear /chat

---

## Zona 3: GRAPH

### Qué puede romperse

| Componente | Modo de fallo | Señal |
|------------|---------------|-------|
| Neo4j driver | Connection timeout | `neo4j.connect_error` |
| Query | Timeout > 2s | `neo4j.query_timeout` |
| Write | Queue full | `neo4j.write_queue` |
| Connection pool | Exhausted | `neo4j.pool_exhausted` |
| DecisionTrace | Buffer full | `decisiontrace.dropped` |

### Cómo se contiene

```
[Graph Query] → Check driver → Execute
                            ↓
              [Timeout/Error] → Circuit breaker
                                 ↓
              [5 failures] → Mode: LEGACY
                             ↓
              [Legacy mode] → Skip graph ops, use local cache
```

- **Circuit breaker**: 5 failures → 30s timeout
- **Fail-open**: Si Neo4j down → legacy mode (sin graph)
- **DecisionTrace**: Fire-and-forget, si falla → log local
- **Connection pool**: 20 max, 2s timeout

### Qué NO debe propagarse

- Graph slow → no debe bloquear /chat
- Query fail → no debe dar 500
- DecisionTrace drop → no debe afectar user

---

## Zona 4: FRONTEND

### Qué puede romperse

| Componente | Modo de fallo | Señal |
|------------|---------------|-------|
| WebSocket | Server disconnect | `ws.server_disconnect` |
| Voice | TTS slow, STT fail | `voice.latency` |
| Telemetry | API slow | `telemetry.latency` |
| Reconnect | Storm de reconexión | `ws.reconnect_storm` |

### Cómo se contiene

- **WebSocket**: Auto-reconnect con backoff exponencial (1s, 2s, 4s, 8s, max 30s)
- **Voice**: Fallback a polling si WS > 5s latency
- **Telemetry**: Buffer local + batch upload
- **Reconnect storm**: Rate limit reconexiones (1/min max)

### Qué NO debe propagarse

- Fallo backend → mensaje genérico, no stack trace
- Latencia alta → no bloquear UI, mostrar estado

---

## Anti-Loop X-Denis-Hop

```
[X-Denis-Hop Prevention]
─────────────────────────
1. Cada zona tiene timeout independiente
2. Circuit breaker rompe ciclo
3. DecisionTrace no bloqueante (fire-and-forget)
4. Fail-open en cadena: API → Workers → Graph
5. Max hop count: 3 (para evitar loops de retry)
```

---

## Checklist de Containment

- [ ] Sync plane: fail-open rate limiter
- [ ] Async plane: fail-open Celery → sync
- [ ] Graph: fail-open → legacy mode
- [ ] Frontend: reconnect backoff
- [ ] Circuit breakers en todas las dependencias
- [ ] DecisionTrace nunca bloquea
- [ ] Timeouts en todos los niveles
