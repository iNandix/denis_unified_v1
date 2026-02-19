# WS1 — LOAD PROFILES & BOTTLENECK ANALYSIS

## Perfiles de Carga

| Perfil | QPS /chat | Jobs Async/min | Writes Graph/min | Conexiones Redis | Conexiones Neo4j |
|--------|-----------|----------------|------------------|------------------|------------------|
| **BAJO** | 1-5 | 5-20 | 10-50 | 5-15 | 2-5 |
| **MEDIO** | 10-30 | 50-150 | 100-400 | 30-80 | 10-25 |
| **PICO** | 50-100 | 200-500 | 500-1500 | 100-200 | 30-60 |
| **TORMENTA** | 150+ | 800+ | 2000+ | 250+ | 80+ |

---

## Cuellos de Botella Identificados

### PRIORIDAD 1 — Graph (Neo4j)

| Métrica | Umbral Alerta | Impacto | Acción |
|---------|---------------|---------|--------|
| Query latency p99 > 2s | /chat p99 > 5s | Bloquea decisión de tool routing | Fallback a intent resolution local |
| Connection pool 80% | Timeouts en DecisionTrace | Pérdida de trazas | Circuit breaker: skip trace |
| Write queue > 100 pending | Mutations lentas | UI freeze en mutations | Degradar a batch async |

**Mitigación implementada:**
- Lazy driver con 2s timeout (`connections.py`)
- Fail-open si Neo4j no disponible → legacy mode

---

### PRIORIDAD 2 — Redis

| Métrica | Umbral Alerta | Impacto | Acción |
|---------|---------------|---------|--------|
| Latencia p99 > 50ms | Rate limiting lento | Requests permitted erróneos | Fallback in-memory TTL |
| Memory > 80% | Eviction keys | Pérdida rate limit state | Alertar + cleanup async |
| Conexiones > 16/20 pool | Conexión reject | /chat 500 | Escalar workers Redis |

**Mitigación implementada:**
- Fallback in-memory si Redis down (`rate_limiting.py`)
- Pool de 20 conexiones max

---

### PRIORIDAD 3 — Workers Async (Celery)

| Métrica | Umbral Alerta | Impacto | Acción |
|---------|---------------|---------|--------|
| Cola `tools_mut` > 500 jobs | Mutations bloqueadas | UI timeout | Alertar + auto-scale workers |
| Cola `graph_ingest` > 1000 | Intent resolution lenta | Mayor latency /chat | Drop writes no-críticos |
| Worker heartbeat > 5min | Worker morto | Jobs stuck | Restart worker pod |
| `tools_ro` latency p99 > 30s | Tool execution lenta | /chat timeout | Timeout + fallback sync |

**Colas definidas** (`celeryconfig.py`):
- `tools_ro` — Read-only, puede reintentarse
- `tools_mut` — Mutating, alta prioridad
- `tts` — Voice, puede batch
- `graph_ingest` — Batch-able
- `ha_playback` — Low priority
- `housekeeping` — Background

---

### PRIORIDAD 4 — API /chat

| Métrica | Umbral Alerta | Impacto | Acción |
|---------|---------------|---------|--------|
| Request p99 > 10s | User timeout | Abandono | 408 + suggest retry |
| WebSocket queue > 100 | Voice delay | Audio choppy | Drop frames o fallback TTS |
| Concurrent sessions > 500 | Memory pressure | OOM | Shed load 503 |

---

## Capacity Planning por Componente

```
                    BAJO    MEDIO    PICO     TORMENTA
--------------------------------------------------------------
API Workers           2       4       8         16+
Celery Workers        2       4       8         16+
Redis Connections    15      80     200        350+
Neo4j Connections     5      25      60        100+
Memory API (GB)       2       4       8         16+
Memory Workers(GB)    1       2       4          8+
```

---

## Reglas de Escalado

1. **Auto-escalar** cuando cola `tools_mut` > 200 por 2 min
2. **Escalar Redis** cuando conexión pool > 12 por 5 min
3. **Circuit breaker** en Neo4j cuando 5 queries fallan consecutively
4. **Load shed** cuando /chat p99 > 8s por 3 min

---

## Latency Budget

| Componente | Target p50 | Target p99 | Max Acceptable |
|------------|------------|------------|----------------|
| Rate Limit | 5ms | 50ms | 100ms |
| Intent Resolution | 100ms | 500ms | 2s |
| Tool Selection | 50ms | 200ms | 1s |
| Inference (engine) | 500ms | 3s | 10s |
| DecisionTrace write | 10ms | 100ms | 500ms |
| **Total /chat** | **1s** | **5s** | **15s** |
