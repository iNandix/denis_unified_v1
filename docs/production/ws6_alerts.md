# WS6 — "WHAT WILL PAGE YOU AT 3AM?"

## Top 7 Alertas Críticas

```
┌────────────────────────────────────────────────────────────────────────────┐
│ PRIORIDAD 1: CRÍTICO — RESPONDER INMEDIATAMENTE                           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #1 /chat LATENCY P99 > 15s                                                 │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Neo4j query timeout (pool exhausted)                                   │
│   • Inference provider down                                               │
│   • Workers colgados                                                      │
│                                                                            │
│ Primera acción:                                                            │
│   curl http://localhost:8084/metrics | grep -E "latency|timeout"          │
│   kubectl get pods -n denis                                               │
│   kubectl logs -l app=denis -n denis --tail=50                           │
│                                                                            │
│ Riesgo de datos: BAJO — Timeout preserva request                          │
│ Severidad: P1                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #2 API PODS DOWN / NO READY                                               │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • OOM killer                                                            │
│   • Crash loop (import error, config)                                     │
│   • Liveness probe failure                                                │
│                                                                            │
│ Primera acción:                                                            │
│   kubectl get pods -n denis -o wide                                       │
│   kubectl describe pod <name> -n denis                                   │
│   kubectl logs <pod> -n denis --previous                                 │
│                                                                            │
│ Riesgo de datos: ALTO — Requests falling                                  │
│ Severidad: P1                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #3 REDIS DOWN / UNREACHABLE                                                │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Redis pod down                                                        │
│   • Network partition                                                     │
│   • Memory limit exceeded                                                 │
│                                                                            │
│ Primera acción:                                                            │
│   redis-cli ping                                                          │
│   kubectl get pods -n denis | grep redis                                  │
│   kubectl logs redis-0 -n denis                                           │
│                                                                            │
│ Riesgo de datos: MEDIO — Rate limits en fallback                          │
│ Severidad: P1                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ PRIORIDAD 2: ALTO — RESPONDER EN 15 MIN                                    │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #4 NEO4J DOWN / CIRCUIT BREAKER ACTIVE                                    │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Neo4j out of memory                                                  │
│   • Connection pool exhausted                                            │
│   • Long running queries                                                  │
│                                                                            │
│ Primera acción:                                                            │
│   cypher-shell -u neo4j -p <pass> "RETURN 1"                            │
│   curl http://localhost:8084/metrics | grep graph_legacy                 │
│                                                                            │
│ Riesgo de datos: MEDIO — DecisionTrace no escribe                        │
│ Severidad: P2                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #5 CELERY QUEUE > 2000 (ANY QUEUE)                                        │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Workers no consumen                                                   │
│   • Productor > consumidor                                                │
│   • Workers crashed                                                       │
│                                                                            │
│ Primera acción:                                                            │
│   celery -A denis_unified_v1.async_min.celery_main:app inspect active   │
│   kubectl get pods -n denis | grep worker                                │
│                                                                            │
│ Riesgo de datos: MEDIO — Jobs pueden expirar                             │
│ Severidad: P2                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #6 WORKER HEARTBEAT MISSING (> 5 min)                                     │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Worker process hung                                                  │
│   • Worker OOM                                                            │
│   • Worker unreachable                                                    │
│                                                                            │
│ Primera acción:                                                            │
│   kubectl get pods -n denis | grep worker                                │
│   kubectl logs <worker-pod> -n denis                                     │
│   kubectl exec <worker-pod> -n denis -- top                             │
│                                                                            │
│ Riesgo de datos: BAJO — Fail-open ejecuta sync                            │
│ Severidad: P2                                                             │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ #7 ERROR RATE > 10% (ANY ENDPOINT)                                         │
│ ────────────────────────────────────────────────────────────────────────── │
│ Causa raíz típica:                                                         │
│   • Provider issues                                                       │
│   • Config problems                                                       │
│   • Recent deployment                                                      │
│                                                                            │
│ Primera acción:                                                            │
│   curl http://localhost:8084/metrics | grep http_requests_total         │
│   kubectl logs -l app=denis -n denis --tail=100 | grep -i error        │
│   git log --oneline -10                                                   │
│                                                                            │
│ Riesgo de datos: BAJO — Aislar causa raíz                                │
│ Severidad: P2                                                             │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Reglas de Alerting (Prometheus)

```yaml
groups:
- name: denis.critical
  interval: 30s
  rules:
  # P1: /chat latency
  - alert: ChatLatencyP99Critical
    expr: histogram_quantile(0.99, rate(chat_duration_seconds_bucket[5m])) > 15
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Chat p99 > 15s"
      runbook_url: "https://docs.denis.run/runbooks#1-chat-latency"

  # P1: API pods down
  - alert: APIPodsNotReady
    expr: kube_pod_status_ready{namespace="denis",condition="true",pod=~"denis-.*"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "API pods not ready"

  # P1: Redis down
  - alert: RedisDown
    expr: up{job="redis"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Redis unreachable"

  # P2: Neo4j circuit breaker
  - alert: Neo4jCircuitBreaker
    expr: denis_graph_legacy_mode == 1
    for: 1m
    labels:
      severity: high
    annotations:
      summary: "Graph in legacy mode"

  # P2: Queue growing
  - alert: CeleryQueueGrowing
    expr: celery_queue_length > 2000
    for: 5m
    labels:
      severity: high
    annotations:
      summary: "Celery queue > 2000"

  # P2: Worker heartbeat
  - alert: WorkerHeartbeatMissing
    expr: time() - denis_worker_last_seen > 300
    for: 5m
    labels:
      severity: high
    annotations:
      summary: "Worker heartbeat missing"

  # P2: Error rate
  - alert: ErrorRateHigh
    expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.1
    for: 3m
    labels:
      severity: high
    annotations:
      summary: "Error rate > 10%"
```

---

## On-Call Quick Reference

```
┌──────────────────────────────────────────────────────────────┐
│ PAGINAR SI:                                                  │
├──────────────────────────────────────────────────────────────┤
│ ✓ P1: API down, /chat timeout > 15s, Redis down            │
│ ✓ P2: Cualquier alerta por > 5 min sin resolución          │
│ ✓ P2: Múltiples alertas同一 tiempo                          │
├──────────────────────────────────────────────────────────────┤
│ NO PAGINAR (auto-resolve):                                  │
├──────────────────────────────────────────────────────────────┤
│ ○ Circuit breaker activo (30s timeout)                       │
│ ○ Fail-open mode activo                                     │
│ ○ Meta restart en proceso                                   │
├──────────────────────────────────────────────────────────────┤
│ CONTACTO:                                                   │
│ ○ Primary: @on-call                                         │
│ ○ Secondary: @sre-lead                                      │
│ ○ Emergency: pagerduty.com/incidents/new                   │
└──────────────────────────────────────────────────────────────┘
```

---

## SLA / SLO Targets

| Métrica | SLO | Crit |
|---------|-----|------|
| /chat availability | 99.9% | 8.76h downtime/año |
| /chat latency p99 | < 5s | 99% |
| /chat latency p50 | < 1s | 99.9% |
| DecisionTrace write | < 100ms | 99% |
| Async job completion | < 5 min | 99% |
| Telemetry freshness | < 30s | 99.9% |
