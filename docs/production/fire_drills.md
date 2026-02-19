# WS1 — FIRE DRILLS EXECUTABLES

## Ejecutar Drills

```bash
# Ubicación: scripts/fire-drills/
# Prerrequisito: kubectl, redis-cli, cypher-shell configurados
```

---

## DRILL #1: Redis Down 5 Min

### Objetivo
Validar fail-open de rate limiting y que el sistema opera con fallback in-memory.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/redis-down.sh

NAMESPACE="denis"
REDIS_POD=$(kubectl get pods -n $NAMESPACE | grep redis | awk '{print $1}' | head -1)

echo "[1/4] Killing Redis pod..."
kubectl delete pod $REDIS_POD -n $NAMESPACE --grace-period=0 --force

echo "[2/4] Waiting 5 minutes (sleeping)..."
sleep 300

echo "[3/4] Verificando fallback in-memory..."
curl -s http://localhost:8084/metrics | grep rate_limit_fallback

echo "[4/4] Restaurando Redis..."
kubectl rollout restart statefulset/redis -n $NAMESPACE
kubectl rollout status statefulset/redis -n $NAMESPACE

echo "Drill completo. Verificar:"
echo "  - rate_limit_fallback == 1 durante outage"
echo "  - /chat respondiendo con 200 durante outage"
```

### Métricas a Monitorear
| Métrica | Before | During | After |
|---------|--------|--------|-------|
| `rate_limit_fallback` | 0 | 1 | 0 |
| `http_requests_total{status="200"}` | baseline | sin drop | baseline |
| `http_requests_total{status="429"}` | baseline | <5% increase | baseline |

### Estado UI Esperado
- **During**: 🟡 Yellow — "Rate limits may be relaxed"
- **After**: 🟢 Green — Sistema normal

### Criterio de Éxito
```
✓ /chat returns 200 throughout (no 500s)
✓ rate_limit_fallback metric = 1 during outage
✓ No data loss
```

---

## DRILL #2: Workers Colgados (Celery)

### Objetivo
Verificar que jobs se reintentan y que hay observabilidad del deadlock.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/workers-hung.sh

NAMESPACE="denis"

echo "[1/5] Simulando workers colgados (env vars)..."
# Poner workers en modo "stuck" temporalmente
kubectl get pods -n $NAMESPACE -l app=denis-worker -o name | \
  while read pod; do
    kubectl exec $pod -n $NAMESPACE -- sh -c "kill -STOP 1" &
  done
sleep 60

echo "[2/5] Enviando jobs de prueba..."
for i in {1..10}; do
  curl -s -X POST http://localhost:8084/internal/test/job \
    -d '{"task":"snapshot_hass","payload":{"test":true}}' &
done
wait

echo "[3/5] Verificando cola creciendo..."
curl -s http://localhost:8084/metrics | grep celery_queue

echo "[4/5] Recuperando workers..."
kubectl get pods -n $NAMESPACE -l app=denis-worker -o name | \
  while read pod; do
    kubectl exec $pod -n $NAMESPACE -- sh -c "kill -CONT 1" &
  done

echo "[5/5] Verificando recuperación..."
sleep 30
curl -s http://localhost:8084/metrics | grep celery_queue

echo "Drill completo."
```

### Métricas a Monitorear
| Métrica | Before | During | After |
|---------|--------|--------|-------|
| `celery_queue_tools_mut_len` | <50 | >200 | <50 |
| `celery_tasks_pending` | 0 | >10 | 0 |
| `worker_seen` timestamp | current | stale | current |

### Estado UI Esperado
- **During**: 🟠 Orange — "Some operations delayed"
- **After**: 🟢 Green — Jobs completados

### Criterio de Éxito
```
✓ Jobs se completan después de recuperación
✓ Cola vuelve a <100 en 5 min post-recovery
✓ No jobs perdidos (verificar dead letter queue)
```

---

## DRILL #3: Graph Lento (Latencia Artificial)

### Objetivo
Validar circuit breaker y fallback a legacy mode cuando Neo4j está lento.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/graph-slow.sh

NAMESPACE="denis"
NEO4J_POD=$(kubectl get pods -n $NAMESPACE | grep neo4j | awk '{print $1}' | head -1)

echo "[1/5] Aplicando latencia artificial a Neo4j..."
# Inject network delay via tc (requiere privileged container)
kubectl exec $NEO4J_POD -n $NAMESPACE -- \
  tc qdisc add dev eth0 root netem delay 5000ms 1000ms 2>&1 || true

echo "[2/5] Enviando requests de prueba..."
for i in {1..20}; do
  curl -s -w "\n%{http_code}\n" http://localhost:8084/chat \
    -d '{"message":"test","user_id":"fire-drill"}' -o /dev/null &
done
wait

echo "[3/5] Verificando circuit breaker..."
curl -s http://localhost:8084/metrics | grep graph_legacy

echo "[4/5] Removiendo latencia..."
kubectl exec $NEO4J_POD -n $NAMESPACE -- \
  tc qdisc del dev eth0 root netem 2>&1 || true

echo "[5/5] Verificando recuperación..."
sleep 10
curl -s http://localhost:8084/metrics | grep graph_legacy

echo "Drill completo."
```

### Métricas a Monitorear
| Métrica | Before | During | After |
|---------|--------|--------|-------|
| `graph_legacy_mode` | 0 | 1 | 0 |
| `neo4j_query_duration_p99` | <500ms | >5s | <500ms |
| `chat_duration_p99` | <5s | <8s (fallback) | <5s |

### Estado UI Esperado
- **During**: 🟡 Yellow — "Context updates may be delayed"
- **After**: 🟢 Green — Sistema normal

### Criterio de Éxito
```
✓ graph_legacy_mode = 1 dentro de 30s de latencia alta
✓ /chat still returns 200 (no 500)
✓ Recovery dentro de 10s post-removal
```

---

## DRILL #4: Flood de Requests /chat

### Objetivo
Validar rate limiting, queueing behavior y graceful degradation bajo carga.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/chat-flood.sh

echo "[1/6] Generando flood de 500 requests en 30 segundos..."
START=$(date +%s)
SUCCESS=0
FAIL_429=0
FAIL_5XX=0

for i in $(seq 1 500); do
  RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/chat_resp_$i.json \
    http://localhost:8084/chat \
    -d "{\"message\":\"load test $i\",\"user_id\":\"fire-drill-$i\"}")
  
  if [ "$RESPONSE" = "200" ]; then
    ((SUCCESS++))
  elif [ "$RESPONSE" = "429" ]; then
    ((FAIL_429++))
  else
    ((FAIL_5XX++))
  fi
  
  if [ $((i % 50)) -eq 0 ]; then
    echo "  Progreso: $i/500 requests sent"
  fi
done

END=$(date +%s)
DURATION=$((END - START))

echo "[2/6] Results:"
echo "  Success (200): $SUCCESS"
echo "  Rate limited (429): $FAIL_429"
echo "  Errors (5xx): $FAIL_5XX"
echo "  Duration: ${DURATION}s"

echo "[3/6] Verificando métricas de rate limit..."
curl -s http://localhost:8084/metrics | grep -E "rate_limit|chat"

echo "[4/6] Verificando memoria workers..."
kubectl top pods -n denis 2>/dev/null || echo "Metrics server not available"

echo "[5/6] Esperando recuperación..."
sleep 30

echo "[6/6] Métricas post-flood..."
curl -s http://localhost:8084/metrics | grep -E "rate_limit|chat"

echo "Drill completo."
```

### Métricas a Monitorear
| Métrica | Target | Dril Result |
|---------|--------|-------------|
| `success_rate` | >90% | >90% = 🟢 |
| `rate_limited_rate` | <10% | <10% = 🟢 |
| `error_5xx_rate` | <1% | <1% = 🟢 |
| `memory_after` | <baseline+10% | OK |

### Criterio de Éxito
```
✓ Success rate > 90%
✓ Error 5xx < 1%
✓ Rate limiting работает (429s seen)
✓ Sistema estable post-flood (30s)
```

---

## DRILL #5: Replay de Jobs Async

### Objetivo
Verificar que jobs en dead letter queue pueden re-procesarse.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/async-replay.sh

NAMESPACE="denis"

echo "[1/5] Verificando dead letter queue..."
# Ver jobs en estado failure
celery -A denis_unified_v1.async_min.celery_main:app inspect failed 2>/dev/null | head -20

echo "[2/5] Obteniendo IDs de jobs fallidos..."
FAILED_JOBS=$(celery -A denis_unified_v1.async_min.celery_main:app inspect failed 2>/dev/null | \
  grep -oP 'job_id=\K[a-f0-9-]+' | head -5)

echo "[3/5] Reenviando jobs (retry)..."
for JOB_ID in $FAILED_JOBS; do
  echo "  Retry job: $JOB_ID"
  # El retry real depende del task; aquí simulamos
  celery -A denis_unified_v1.async_min.celery_main:app \
    control revoke $JOB_ID 2>/dev/null || true
done

echo "[4/5] Enviando jobs de prueba para verificar replay..."
# Dispatch nuevo job
curl -s -X POST http://localhost:8084/internal/test/job \
  -d '{"task":"snapshot_hass","payload":{"test":true,"replay_test":true}}'

echo "[5/5] Verificando completación..."
sleep 30
celery -A denis_unified_v1.async_min.celery_main:app inspect active 2>/dev/null | head -10

echo "Drill completo."
```

### Métricas a Monitorear
| Métrica | Before | After |
|---------|--------|-------|
| `celery_tasks_failed_total` | baseline | baseline+5 |
| `celery_tasks_retry_total` | baseline | baseline+5 |
| `dead_letter_size` | N | N |

### Criterio de Éxito
```
✓ Jobs reintentados exitosamente
✓ No jobs perdidos
✓ Dead letter queue no crece indefinidamente
```

---

## DRILL #6: Corruption Attempt de Artifact

### Objetivo
Validar que artifacts corruptos son detectados y no rompen el sistema.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/artifact-corruption.sh

ARTIFACT_ID="test-corrupt-$(date +%s)"

echo "[1/6] Subiendo artifact corrupto de prueba..."
# Crear artifact con checksum inválido
echo "CORRUPTED_DATA" > /tmp/corrupt.json

curl -s -X POST http://localhost:8084/internal/artifacts \
  -F "file=@/tmp/corrupt.json" \
  -F "artifact_id=$ARTIFACT_ID" \
  -F "expected_checksum=invalid_checksum"

echo "[2/6] Intentando usar artifact en /chat..."
curl -s http://localhost:8084/chat \
  -d "{\"message\":\"use artifact $ARTIFACT_ID\",\"user_id\":\"fire-drill\"}"

echo "[3/6] Verificando métricas de verificación..."
curl -s http://localhost:8084/metrics | grep artifact_verify

echo "[4/6] Verificando logs de rechazo..."
kubectl logs -l app=denis -n denis --tail=20 | grep -i "artifact\|checksum\|invalid"

echo "[5/6] Verificando que /chat sigue operativo..."
curl -s -w "\n%{http_code}\n" http://localhost:8084/chat \
  -d '{"message":"hello","user_id":"fire-drill"}'

echo "[6/6] Limpiendo artifact de prueba..."
curl -s -X DELETE http://localhost:8084/internal/artifacts/$ARTIFACT_ID

echo "Drill completo."
```

### Métricas a Monitorear
| Métrica | Expected |
|---------|----------|
| `artifact_verification_failed` | +1 |
| `artifact_rejected_total` | +1 |
| `/chat_error` | 0 (fail-open) |

### Criterio de Éxito
```
✓ Artifact corrupto rechazado
✓ /chat no devuelve 500
✓ Métrica de rejection incremento
✓ Fail-open funcionó
```

---

## DRILL #7: DecisionTrace Inconsistency

### Objetivo
Verificar que DecisionTrace drop no afecta /chat.

### Comando Ejecución
```bash
#!/bin/bash
# scripts/fire-drills/decision-trace-drop.sh

NAMESPACE="denis"

echo "[1/5] Llenando DecisionTrace buffer para forzar drop..."
# Enviar muchas decisions rapidamente
for i in $(seq 1 200); do
  curl -s -X POST http://localhost:8084/internal/decision_trace \
    -d "{\"kind\":\"test\",\"mode\":\"PRIMARY\",\"session_id\":\"fire-drill-$i\"}" \
    -w "%{http_code}\n" -o /dev/null &
done
wait

echo "[2/5] Verificando drops..."
curl -s http://localhost:8084/metrics | grep decisiontrace_dropped

echo "[3/5] Enviando /chat request..."
curl -s http://localhost:8084/chat \
  -d '{"message":"test decision trace","user_id":"fire-drill"}'

echo "[4/5] Verificando que /chat respondió..."
curl -s http://localhost:8084/metrics | grep chat_requests_total

echo "[5/5] Verificando recovery..."
sleep 10
curl -s http://localhost:8084/metrics | grep decisiontrace_dropped

echo "Drill completo."
```

### Criterio de Éxito
```
✓ decisiontrace_dropped > 0 (drops occur)
✓ /chat returns 200 (no impact)
✓ Fire-and-forget confirmado
```

---

## Ejecución Programada

```bash
# Agregar a crontab para ejecución semanal
# 0 2 * * 0 /media/jotah/SSD_denis/home_jotah/denis_unified_v1/scripts/fire-drills/redis-down.sh
# 0 3 * * 0 /media/jotah/SSD_denis/home_jotah/denis_unified_v1/scripts/fire-drills/workers-hung.sh
# 0 4 * * 1 /media/jotah/SSD_denis/home_jotah/denis_unified_v1/scripts/fire-drills/chat-flood.sh
```

---

## Summary de Drills

| # | Drill | Duración | Frecuencia | Owner |
|---|-------|----------|------------|-------|
| 1 | Redis Down | 5 min | Semanal | SRE |
| 2 | Workers Hung | 5 min | Semanal | SRE |
| 3 | Graph Slow | 3 min | Mensual | SRE |
| 4 | Chat Flood | 2 min | Mensual | SRE |
| 5 | Async Replay | 5 min | Mensual | SRE |
| 6 | Artifact Corruption | 3 min | Mensual | SecOps |
| 7 | DecisionTrace Drop | 2 min | Mensual | SRE |
