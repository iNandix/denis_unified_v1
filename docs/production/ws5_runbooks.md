# WS5 — OPERATION RUNBOOKS

---

## RUNBOOK #1: Redis Caído

### Síntomas
- `redis.ping` error
- Rate limiting usa fallback in-memory
- `celery.broker_down` si Redis = broker
- `ConnectionError` en logs

### Qué mirar en Ops UI

```
Grafana Dashboard: Redis Overview
├── Connection errors > 0
├── Memory used > 80%
├── CPU > 50%
└── Keyspace hits/misses ratio

Kibana: denis* | redis error
```

### Comandos/Acciones

```bash
# 1. Verificar estado Redis
redis-cli ping
redis-cli info clients

# 2. Verificar uso memoria
redis-cli info memory | grep used

# 3. Si está caído: reiniciar
kubectl rollout restart statefulset/redis -n denis

# 4. Verificar reconexión
redis-cli ping
# PONG = OK

# 5. Verificar rate limiting
curl http://localhost:8084/metrics | grep rate_limit
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| Redis down > 5 min | Escalar a SRE |
| Memory > 90% | Escalar a ops + cleanup |
| Reconnect fallando | Escalar a SRE |
| Datos perdidos | Rollback + restore backup |

---

## RUNBOOK #2: Workers Colgados

### Síntomas
- Cola creciendo: `celery.queue.len` > 500
- `worker_seen` no actualiza > 5 min
- Jobs con `STARTED` > 10 min sin completar

### Qué mirar en Ops UI

```
Grafana: Celery Workers
├── Active workers = 0
├── Queue length (per queue)
├── Task duration p99
└── Failed tasks rate

Kibana: denis* | "worker_down" OR "celery"
```

### Comandos/Acciones

```bash
# 1. Ver estado workers
celery -A denis_unified_v1.async_min.celery_main:app inspect active
celery -A denis_unified_v1.async_min.celery_main:app inspect stats

# 2. Ver colas
celery -A denis_unified_v1.async_min.celery_main:app inspect active_queues

# 3. Restart workers
kubectl rollout restart deployment/denis-workers -n denis

# 4. Ver jobs en retry
celery -A denis_unified_v1.async_min.celery_main:app inspect reserved

# 5. Force purge stuck jobs (ÚLTIMO RECURSO)
celery -A denis_unified_v1.async_min.celery_main:app purge -f
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| Cola > 1000 por 10 min | Escalar a SRE |
| Workers no inician | Escalar a ops |
| Jobs se acumulan | Restart workers |
| Memoria workers > 1GB | Kill + restart |

---

## RUNBOOK #3: Graph (Neo4j) Lento

### Síntomas
- `/chat` latency > 5s
- `neo4j.query_timeout` errores
- `neo4j.pool_exhausted` errores
- DecisionTrace no escribe

### Qué mirar en Ops UI

```
Grafana: Neo4j Overview
├── Query duration p99 > 2s
├── Active connections > 80%
├── Write queue length
└── Cache hit ratio

Kibana: neo4j error OR graph timeout
```

### Comandos/Acciones

```bash
# 1. Verificar conexión
cypher-shell -u neo4j -p <pass> "RETURN 1"

# 2. Ver queries lentas
cypher-shell -u neo4j -p <pass> "CALL dbms.listQueries() YIELD query, elapsedTimeMs WHERE elapsedTimeMs > 5000 RETURN query, elapsedTimeMs"

# 3. Ver conexiones
cypher-shell -u neo4j -p <pass> "CALL dbms.listConnections() YIELD connectionId, clientAddress"

# 4. Restart driver (si circuit breaker activo)
# El código ya tiene fail-open, verificar modo:
curl http://localhost:8084/metrics | grep graph_legacy

# 5. Aumentar timeout temporal
# Editar connections.py: timeout=5s
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| p99 > 10s por 5 min | Escalar a SRE |
| Queries bloqueadas | Kill long-running queries |
| Pool exhausted | Restart Neo4j |
| Datos corruptos | Restore backup |

---

## RUNBOOK #4: Cola Creciendo Sin Consumir

### Síntomas
- `celery.queue.*.len` creciendo sostenidamente
- `celery.worker.utilization` < 30%
- Jobs esperando > 10 min

### Qué mirar en Ops UI

```
Grafana: Celery Queue Growth
├── Queue length trend (último 1h)
├── Consumption rate
├── Producer rate
└── Worker count

Kibana: "job received" - "job completed"
```

### Comandos/Acciones

```bash
# 1. Identificar cola problemática
celery -A denis_unified_v1.async_min.celery_main:app inspect active_queues

# 2. Ver si workers consumen esa cola
celery -A denis_unified_v1.async_min.celery_main:app inspect active | grep -A5 <queue>

# 3. Si no hay workers para la cola: añadir
kubectl scale deployment/denis-workers --replicas=6 -n denis

# 4. Si workers atascados: restart
kubectl rollout restart deployment/denis-workers -n denis

# 5. Rate limiting de producers
# Reducir ASYNC_DISPATCH_RATE si está configurado

# 6. Emergency: drain cola
# Mover jobs a dead letter
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| Cola > 2000 por 30 min | Escalar a SRE |
| Workers no consumen | Reasignar colas |
| Productor > consumidor | Rate limit producer |
| Datos perdidos | Re-process desde logs |

---

## RUNBOOK #5: Mutations Bloqueadas por Policy

### Síntomas
- Usuario reporta "acción no permitida"
- `gate.policy_block` metric subir
- `tools_mut` cola vacía pero user blocked
- Mutations retornan 403

### Qué mirar en Ops UI

```
Grafana: Gate Decisions
├── policy_block count
├── budget_exceeded count
├── injection_detected count
└── Blocked by policy type

Kibana: denis* | "BLOCKED" OR "policy"
```

### Comandos/Acciones

```bash
# 1. Ver tipo de bloqueo
curl http://localhost:8084/metrics | grep gate

# 2. Ver logs de política específica
kubectl logs -l app=denis -n denis --tail=50 | grep -i "policy"

# 3. Ver policy actual (Neo4j)
cypher-shell -u neo4j -p <pass> "MATCH (p:Policy) RETURN p LIMIT 10"

# 4. Unlockear usuario temporalmente (si es false positive)
# Buscar en rate_limiting.py función de unlock

# 5. Deshabilitar policy temporalmente (ÚLTIMO RECURSO)
# Editar gates/ y redeploy
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| Múltiples users bloqueados | Escalar a SRE |
| Falso positivo confirmado | Disable policy |
| Policy no carga | Check Neo4j |
| Datos perdidos | Restore policy |

---

## RUNBOOK #6: Telemetry Inconsistente

### Síntomas
- Métricas en Grafana no actualizan
- DecisionTrace vacío
- `/metrics` retorna error
- Trace spans incompletos

### Qué mirar en Ops UI

```
Grafana: Telemetry Health
├── /metrics HTTP 200 rate
├── Prometheus scrape success
├── Jaeger spans per minute
└── DecisionTrace writes

Kibana: "telemetry" OR "metrics" OR "trace"
```

### Comandos/Acciones

```bash
# 1. Verificar /metrics endpoint
curl -s http://localhost:8084/metrics | head -20
curl -s http://localhost:8084/metrics | wc -l

# 2. Verificar Prometheus target
curl -s http://prometheus:9090/api/v1/targets | grep denis

# 3. Verificar Jaeger connection
curl -s http://jaeger:14268/api/traces | head

# 4. Restart telemetry si necesario
kubectl rollout restart deployment/denis -n denis

# 5. Ver DecisionTrace writes
cypher-shell -u neo4j -p <pass> "MATCH (d:Decision) RETURN count(d) LIMIT 1"
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| /metrics down > 5 min | Escalar a SRE |
| Jaeger no recibe | Check network |
| DecisionTrace no escribe | Check Neo4j |
| Dashboard vacío | Check Prometheus scrape |

---

## RUNBOOK #7: API /chat Timeout

### Síntomas
- `chat.latency.p99` > 10s
- Usuarios reportan "sin respuesta"
- `chat.timeout` metric subir

### Qué mirar en Ops UI

```
Grafana: Chat Latency
├── p50, p95, p99
├── Por step del pipeline
├── Inference time
└── Graph query time

Kibana: denis* | timeout OR 408
```

### Comandos/Acciones

```bash
# 1. Verificar /health
curl http://localhost:8084/health

# 2. Ver workers de API
kubectl get pods -l app=denis -n denis

# 3. Ver inference providers
curl http://localhost:8084/metrics | grep inference

# 4. Restart API si stuck
kubectl rollout restart deployment/denis -n denis

# 5. Verificar circuit breakers
curl http://localhost:8084/metrics | grep circuit
```

### Cuándo escalar

| Condición | Acción |
|-----------|--------|
| p99 > 30s | P1 - Escalar inmediatamente |
| /chat down | P1 - Escalar inmediatamente |
| Solo un provider down | Verificar fallback |

---

## RUNBOOK #8: WebSocket Desconexiones

### Síntomas
- `ws.disconnect_rate` alto
- Usuarios reportan "conexión perdida"
- Voice calls cortadas

### Qué mirar en Ops UI

```
Grafana: WebSocket
├── Connected clients
├── Reconnect rate
├── Message queue length
└── Latency

Kibana: websocket disconnect OR close
```

### Comandos/Acciones

```bash
# 1. Ver clientes conectados
curl http://localhost:8084/metrics | grep ws

# 2. Ver logs de desconexión
kubectl logs -l app=denis -n denis --tail=100 | grep -i "ws\|websocket"

# 3. Restart API (WebSocket state)
kubectl rollout restart deployment/denis -n denis

# 4. Verificar red (LoadBalancer)
kubectl get svc -n denis | grep websocket
```

---

## Checklist General de Escalamiento

```
┌─────────────────────────────────────────────────────┐
│ ESCALAR SI:                                         │
├─────────────────────────────────────────────────────┤
│ • P1: /chat down, data loss, security breach       │
│ • > 5 min downtime sin recovery                    │
│ • Error rate > 10%                                 │
│ • Múltiples componentes caídos                      │
│ • Sin rollback disponible                           │
├─────────────────────────────────────────────────────┤
│ CONTACTO:                                           │
│ • SRE Lead: @sre-lead                              │
│ • On-call: @on-call                               │
│ • Emergency: +1-555-0199                           │
└─────────────────────────────────────────────────────┘
```
