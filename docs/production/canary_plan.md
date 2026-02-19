# WS2 — CANARY ROLLOUT PLAN

## Target: Materializers Async (1% → 100%)

---

## Fases del Canary

```
┌────────────────────────────────────────────────────────────────────────────┐
│ CANARY: Materializers Async                                               │
├────────────────────────────────────────────────────────────────────────────┤
│ Fase 1:  1%  (Día 1)    — Observación inicial                            │
│ Fase 2: 10%  (Día 2-3)  — Estabilidad                                    │
│ Fase 3: 50%  (Día 4-5)  — Capacity test                                  │
│ Fase 4: 100% (Día 6+)   — Full rollout                                   │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Fase 1: 1% Traffic

### Duración
- **Ventana**: 4 horas mínimo
- **Horario**: 8:00 AM - 12:00 PM (horario laboral para observación)

### Métricas de Promoción

| Métrica | Límite | Tipo | Acción |
|---------|--------|------|--------|
| `materializer_success_rate` | > 95% | hard | **PROMOTE** si pasa |
| `materializer_latency_p99` | < 10s | soft | Advert if exceeded |
| `error_rate` (global) | < 2% | hard | **ROLLBACK** si pasa |
| `/chat_latency_p99` | +10% vs baseline | soft | Advert if exceeded |
| `queue_depth` (tools_mut) | < 100 | soft | Advert if exceeded |

### Scripts de Verificación
```bash
# 1. Aplicar 1% traffic
kubectl set env deployment denis DENIS_MATERIALIZERS_PCT=1 -n denis

# 2. Verificar tráfico
curl -s http://localhost:8084/metrics | grep materializer_pct

# 3. Monitor métricas
watch -n 10 'curl -s http://localhost:8084/metrics | grep -E "materializer|error_rate"'

# 4. Verificar jobs completing
celery -A denis_unified_v1.async_min.celery_main:app inspect active | grep materializer
```

### Kill Switch (Fase 1)
```bash
# Kill switch inmediato
kubectl set env deployment denis DENIS_MATERIALIZERS_ENABLED=false -n denis
kubectl rollout restart deployment/denis -n denis
```

### Criterios de Rollback Automático
| Condición | Acción |
|-----------|--------|
| `materializer_success_rate` < 90% | Rollback automático |
| `error_rate` > 5% | Rollback automático |
| `/chat` down | Rollback automático |

### Resultado Esperado
- 🟢 **PROMOTE** si todas las métricas hard pasan
- 🔴 **ROLLBACK** si cualquier métrica hard falla

---

## Fase 2: 10% Traffic

### Duración
- **Ventana**: 24 horas
- **Horario**: Día completo de operación

### Métricas de Promoción

| Métrica | Límite | Tipo | Acción |
|---------|--------|------|--------|
| `materializer_success_rate` | > 97% | hard | **PROMOTE** si pasa |
| `materializer_latency_p99` | < 8s | soft | Advert if exceeded |
| `error_rate` (global) | < 1% | hard | **ROLLBACK** si pasa |
| `/chat_latency_p99` | +5% vs baseline | soft | Advert if exceeded |
| `queue_depth` (tools_mut) | < 200 | soft | Advert if exceeded |
| `worker_seen` freshness | < 2 min | hard | Advert if stale |
| `decisiontrace_drops` | < 10/min | soft | Advert if exceeded |

### Scripts de Verificación
```bash
# 1. Escalar a 10%
kubectl set env deployment denis DENIS_MATERIALIZERS_PCT=10 -n denis
kubectl rollout restart deployment/denis -n denis

# 2. Dashboard check (Grafana)
# Open: https://grafana.denis.run/d/materializers-canary

# 3. Query de validación
curl -s http://localhost:8084/metrics | grep -E \
  "materializer_success_rate|materializer_latency_p99|error_rate"

# 4. Revisar logs de errores
kubectl logs -l app=denis -n denis --tail=100 | grep -i error | grep -i materializer
```

### Criterios de Rollback Automático
| Condición | Acción |
|-----------|--------|
| `materializer_success_rate` < 93% | Rollback |
| `error_rate` > 3% | Rollback |
| Queue > 500 por 10 min | Rollback |
| Worker OOM | Rollback |

### Resultado Esperado
- 🟢 **PROMOTE** si métricas hard pasan
- 🟡 **HOLD** si métricas soft pasan pero no hard
- 🔴 **ROLLBACK** si métricas hard fallan

---

## Fase 3: 50% Traffic

### Duración
- **Ventana**: 48 horas
- **Horario**: 2 días completos de operación

### Métricas de Promoción

| Métrica | Límite | Tipo | Acción |
|---------|--------|------|--------|
| `materializer_success_rate` | > 98% | hard | **PROMOTE** |
| `materializer_latency_p99` | < 5s | hard | **PROMOTE** |
| `error_rate` (global) | < 0.5% | hard | **PROMOTE** |
| `/chat_latency_p99` | < baseline + 10% | soft | Advert |
| `queue_depth` (tools_mut) | < 300 | soft | Advert |
| `graph_write_latency_p99` | < 1s | soft | Advert |
| Memory usage API | < 80% | soft | Advert |
| Memory usage workers | < 70% | soft | Advert |

### Scripts de Verificación
```bash
# 1. Escalar a 50%
kubectl set env deployment denis DENIS_MATERIALIZERS_PCT=50 -n denis
kubectl rollout restart deployment/denis -n denis

# 2. Load test de 1 hora
./scripts/load-test/chat-flood.sh --requests=1000 --duration=60

# 3. Verificación de integridad de Graph
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (m:Materializer) WHERE m.created > datetime() - duration('PT1H') RETURN count(m)"

# 4. Verificación de DecisionTrace
curl -s "http://localhost:8084/internal/decision_trace/stats" | jq '.write_success_rate'
```

### Criterios de Rollback Automático
| Condición | Acción |
|-----------|--------|
| `materializer_success_rate` < 95% | Rollback |
| Latencia /chat +30% baseline | Rollback |
| Memory > 90% cualquier componente | Rollback |

---

## Fase 4: 100% Traffic (Full Rollout)

### Duración
- **Ventana**: 72 horas (3 días)
- **Horario**: Operación completa

### Métricas de Estabilización

| Métrica | Target | Tipo |
|---------|--------|------|
| `materializer_success_rate` | > 99% | hard |
| `materializer_latency_p99` | < 3s | hard |
| `error_rate` (global) | < 0.1% | hard |
| `/chat_latency_p99` | < baseline + 5% | soft |
| Uptime | 99.9% | hard |

### Scripts de Verificación
```bash
# 1. Full rollout
kubectl set env deployment denis DENIS_MATERIALIZERS_PCT=100 -n denis
kubectl set env deployment denis DENIS_MATERIALIZERS_ENABLED=true -n denis

# 2. Disable async flag for final state
# (optional: leave enabled for production)

# 3. Monitoreo de 72h
# - Verificar Grafana dashboard cada 8h
# - Verificar alerts cada 4h

# 4. Final check
curl -s http://localhost:8084/metrics | grep materializer
```

---

## Kill Switch Global

### Cómo Accionarlo

```bash
# Método 1: Environment variable (inmediato)
kubectl set env deployment denis DENIS_MATERIALIZERS_ENABLED=false -n denis

# Método 2: Feature flag en Redis
redis-cli SET denis:feature:materializers:enabled 0

# Método 3: API kill switch
curl -X POST http://localhost:8084/internal/kill-switch/materializers

# Método 4: Emergency stop (deshabilita todo async)
kubectl scale deployment/denis-workers --replicas=0 -n denis
```

### Verificación Post-Kill
```bash
# Verificar que no hay jobs nuevos
curl -s http://localhost:8084/metrics | grep materializer_new

# Verificarqueue vacía
celery -A denis_unified_v1.async_min.celery_main:app inspect active | grep materializer

# Verificar /chat sigue funcionando
curl -s -w "\n%{http_code}\n" http://localhost:8084/chat \
  -d '{"message":"test post kill","user_id":"post-kill-test"}'
```

### Tiempo de Activación
- **Kill switch**: < 10 segundos
- **Jobs paran**: < 30 segundos
- **Queue drain**: depende de jobs en cola (max 5 min con workers)

---

## Métricas Dashboard Template

```json
{
  "panels": [
    {"title": "Materializer Success Rate", "target": ">98%"},
    {"title": "Materializer Latency p99", "target": "<5s"},
    {"title": "Queue Depth (tools_mut)", "target": "<200"},
    {"title": "Error Rate Global", "target": "<0.5%"},
    {"title": "Chat Latency p99", "target": "+0% baseline"}
  ]
}
```

---

## Decision Matrix

```
                    │ SUCCESS >98% │ SUCCESS <98% │ ERROR >5%
────────────────────┼──────────────┼───────────────┼───────────
1% PHASE            │   PROMOTE    │    HOLD       │  ROLLBACK
10% PHASE           │   PROMOTE    │    HOLD (24h) │  ROLLBACK
50% PHASE           │   PROMOTE    │    ROLLBACK   │  ROLLBACK
100% PHASE          │   MONITOR    │    ROLLBACK   │  EMERGENCY
```

---

## Post-Rollout Validation

```bash
# 1. Verificar que todas las métricas están en verde
curl -s http://localhost:8084/metrics | grep -E \
  "materializer_success_rate|materializer_latency_p99|error_rate"

# 2. Verificar Graph integrity
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (m:Materializer) RETURN count(m) as total, \
   avg(duration.between(m.created, datetime())) as avg_age"

# 3. Verificar DecisionTrace
curl -s http://localhost:8084/internal/decision_trace/stats | jq

# 4. Notificar éxito
curl -X POST $SLACK_WEBHOOK -d '{"text":"Materializers 100% rollout complete"}'
```
