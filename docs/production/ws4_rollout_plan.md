# WS4 — ROLLOUT & MIGRATION PLAN

## Fases de Rollout

```
FASE 0: Current State (STUB)
────────────────────────────
• Materializers: stub / dummy
• Telemetry: básica (counts only)
• Crew runs: manuales via CLI
• Fail-open: implementado

FASE 1: Materializers Live (Semana 1-2)
────────────────────────────────────────
Meta: Materializers stub → reales, observabilidad básica

Step 1.1: Deploy materializer stubs con logs
├── Flag: DENIS_MATERIALIZERS_ENABLED=false
├── Deploy code
├── Ver logs en staging
└── Rollback: flag = false

Step 1.2: Canary 1% traffic
├── Flag: DENIS_MATERIALIZERS_ENABLED=true
├── Traffic: 1% /chat requests
├── Metrics: success rate, latency
└── Rollback: flag = false

Step 1.3: Expand to 10%
├── Traffic: 10%
├── Alert threshold: error > 5%
└── Rollback: flag = false

Step 1.4: Full rollout
├── Traffic: 100%
├── Monitor 24h
└── Enable by default

Métricas "ok para avanzar":
✓ Materializer success rate > 95%
✓ Latency p99 < 5s overhead
✓ No increase in /chat errors
✓ worker_seen heartbeat visible
```

```
FASE 2: Telemetry Complete (Semana 3-4)
────────────────────────────────────────
Meta: Básica → Completa (Prometheus + OTel + DecisionTrace)

Step 2.1: Prometheus metrics
├── Deploy /observability/metrics.py
├── Verify /metrics endpoint
├── Configure Grafana dashboards
└── Rollback: disable endpoint

Step 2.2: OpenTelemetry tracing
├── Deploy /observability/tracing.py
├── Connect to Jaeger
├── Trace /chat flow
└── Rollback: disable exporter

Step 2.3: DecisionTrace enabled
├── Enable DecisionTrace writes
├── Verify Neo4j writes
├── Build audit dashboard
└── Rollback: disable trace.kind

Métricas "ok para avanzar":
✓ /metrics returning 200
✓ Traces visible in Jaeger
✓ DecisionTrace visible in Neo4j
✓ No latency overhead > 100ms
```

```
FASE 3: Async Workers Auto (Semana 5-6)
────────────────────────────────────────
Meta: Crew runs manuales → automáticos

Step 3.1: Celery workers en staging
├── Deploy workers con flag off
├── Verify queues created
├── Test manual dispatch
└── Rollback: kill workers

Step 3.2: Auto-dispatch enabled
├── Flag: ASYNC_ENABLED=true
├── Route non-critical to Celery
├── Monitor queue health
└── Rollback: flag = false

Step 3.3: Scale workers
├── Add 2 workers (total 4)
├── Verify auto-scale triggers
├── Load test at 2x expected
└── Rollback: reduce workers

Métricas "ok para avanzar":
✓ Jobs complete < 5 min
✓ Queue length stable < 100
✓ No jobs in dead letter
✓ Worker CPU < 70%
```

---

## Feature Flags

| Flag | Default | Phase | Description |
|------|---------|-------|-------------|
| `DENIS_MATERIALIZERS_ENABLED` | `false` | F1 | Enable real materializers |
| `ASYNC_ENABLED` | `false` | F3 | Enable Celery async |
| `DECISION_TRACE_ENABLED` | `false` | F2 | Enable DecisionTrace |
| `TELEMETRY_ENABLED` | `false` | F2 | Enable full telemetry |
| `GRAPH_LEGACY_MODE` | `false` | Any | Force legacy (no graph) |
| `RATE_LIMIT_STRICT` | `false` | F3 | Enforce rate limits |
| `VOICE_ENABLED` | `false` | F3 | Enable voice features |

**Gestión de flags**: Base de datos Redis o configmap K8s.

---

## Rollback Procedures

### Rollback Inmediato (60s)

```bash
# 1. Deshabilitar flag
kubectl set env deployment DENIS_MATERIALIZERS_ENABLED=false -n denis

# 2. Verificar tráfico sin materializers
curl -s http://localhost:8084/metrics | grep materializer

# 3. Si hay errores, revisar logs
kubectl logs -l app=denis -n denis --tail=100 | grep ERROR
```

### Rollback Completo (5min)

```bash
# 1. Revertir a release anterior
kubectl rollout undo deployment/denis -n denis

# 2. Esperar a que esté listo
kubectl rollout status deployment/denis -n denis

# 3. Verificar salud
curl http://localhost:8084/health
```

### Emergency Stop (30s)

```bash
# Matar todos los workers
kubectl scale deployment/denis-workers --replicas=0 -n denis

# Bloquear tráfico
kubectl patch ingress denis -n denis -p '{"spec":{"rules":[{"http":{"paths":[{"backend":{"service":{"name":"null"}}}]}}]}}'

# Notificar
curl -X POST $PAGERDUTY_WEBHOOK -d '{"event":"emergency_stop"}'
```

---

## Criteria de Avance por Fase

| Fase | Criterio | Threshold | Checkpoint |
|------|----------|-----------|------------|
| F1 | Materializer success | > 95% | 24h sin incidentes |
| F1 | Latency overhead | < 500ms p99 | 1h monitoring |
| F2 | Metrics available | /metrics 200 | Verify Grafana |
| F2 | Traces complete | span /chat < 5 | Sample 10 requests |
| F2 | DecisionTrace | writes visible | Verify Neo4j |
| F3 | Job completion | < 5 min | 100 jobs |
| F3 | Queue stability | < 100 pending | 4h |
| F3 | Worker health | CPU < 70% | 24h |

---

## Runbook de Release

```
PRE-RELEASE (30 min antes)
──────────────────────────
1. Verificar CI/CD pipeline verde
2. Review changelog + PRs merged
3. Notify #denis-releases
4. Backup config: `kubectl get all -n denis -o yaml > backup.yaml`

DURANTE RELEASE
────────────────
1. Deploy canary: 1%
2. Monitor métricas: errors, latency
3. Si OK: scale to 10%, 50%, 100%
4. Si ERROR > threshold: rollback

POST-RELEASE
────────────────
1. Monitor 1h mínimo
2. Verificar telemetry
3. Close #denis-releases
4. Documentar Issues
```

---

## Tráfico Phasing

```
Canary Schedule:
───────────────
Day 1:  1%  (8:00 - 12:00)
Day 1:  5%  (12:00 - 18:00)
Day 1: 10%  (18:00 - 24:00)
Day 2: 25%  (full day)
Day 3: 50%  (full day)
Day 4: 100% (full day)

Rollback triggers:
──────────────────
• Error rate > 5%
• Latency p99 > 2x baseline
• Memory > 90%
• Any P1 incident
```
