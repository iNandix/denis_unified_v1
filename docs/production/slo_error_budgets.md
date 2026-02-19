# WS3 — SLOs & ERROR BUDGETS

---

## SLO Definitions

### SLO 1: /chat Availability

| Atributo | Valor |
|----------|-------|
| **Métrica** | `http_requests_total{endpoint="/chat",status="200"} / http_requests_total{endpoint="/chat"}` |
| **Objetivo** | 99.9% |
| **Ventana** | 30 días |
| **Error Budget** | 0.1% = 43.8 minutos/mes |
| **Critical Threshold** | 99.5% (21.6 min/mes) |

### SLO 2: /chat Latency p95

| Atributo | Valor |
|----------|-------|
| **Métrica** | `histogram_quantile(0.95, rate(chat_duration_seconds_bucket[5m]))` |
| **Objetivo** | < 3 segundos |
| **Ventana** | 30 días |
| **Error Budget** | 5% del tiempo > 3s |
| **Critical Threshold** | > 5 segundos |

### SLO 3: Materializer Freshness

| Atributo | Valor |
|----------|-------|
| **Métrica** | `rate(materializer_fresh_total) / rate(materializer_request_total)` |
| **Objetivo** | > 95% completan en < 5 min |
| **Ventana** | 30 días |
| **Error Budget** | 5% jobs > 5 min |
| **Critical Threshold** | > 10% jobs > 10 min |

### SLO 4: Graph Integrity

| Atributo | Valor |
|----------|-------|
| **Métrica** | `graph_write_success_total / graph_write_total` |
| **Objetivo** | > 99% writes succeed |
| **Ventana** | 30 días |
| **Error Budget** | 1% writes fail |
| **Critical Threshold** | < 95% success rate |

### SLO 5: Telemetry Availability

| Atributo | Valor |
|----------|-------|
| **Métrica** | `up{job="denis-api"}` |
| **Objetivo** | 99.9% |
| **Ventana** | 30 días |
| **Error Budget** | 43.8 minutos/mes |
| **Critical Threshold** | < 99.5% |

---

## Error Budget Calculations

```
Monthly Budget (30 days)
══════════════════════════════════════════════════════════════

/chat Availability (99.9%)
─────────────────────────────
Total requests/month:     ~2,592,000 (30d × 24h × 60m × 60 req/min)
Allowed downtime:         43.8 minutes
Allowed failed requests:   ~2,592 (0.1%)

/chat Latency p95 (<3s)
────────────────────────
Total windows:            8,640 (30d × 24h × 12 windows/hr)
Allowed slow windows:     432 (5%)
Critical slow windows:    864 (10%)

Materializer Freshness (>95% in <5min)
───────────────────────────────────────
Total jobs/month:         ~432,000 (30d × 24h × 60min × 10 jobs/min)
Allowed stale jobs:       21,600 (5%)
Critical stale jobs:      43,200 (10%)

Graph Integrity (>99% writes)
─────────────────────────────
Total writes/month:       ~1,296,000 (30d × 24h × 60m × 30 writes/min)
Allowed failed writes:    12,960 (1%)
Critical failed writes:   64,800 (5%)
```

---

## Error Budget Actions

### Level 1: Warning (Budget < 80% remaining)

| Trigger | Acción |
|---------|--------|
| Cualquier SLO < 80% budget | Notificar en #denis-alerts |
| Review semanal | Añadir a agenda semanal |

### Level 2: Alert (Budget < 50% remaining)

| Trigger | Acción |
|---------|--------|
| Cualquier SLO < 50% budget | Page on-call |
| Review daily | Daily standup review |
| Feature freeze | Bloquear features no-críticos |

### Level 3: Critical (Budget < 20% remaining)

| Trigger | Acción |
|---------|--------|
| Cualquier SLO < 20% budget | Page SRE Lead + Director |
| Emergency review | Reunión de emergencia en 2h |
| Disable async | Deshabilitar features async |
| Rollback | Rollback a versión estable |

### Level 4: Exhausted (Budget = 0%)

| Trigger | Acción |
|---------|--------|
| SLO budget agotado | Incident P1 |
| Full rollback | Rollback a última versión estable |
| Post-mortem | Post-mortem obligatorio en 48h |
| Launch delay | Retrasar launch hasta resolución |

---

## SLO Tracking Queries

### Prometheus Queries

```promql
# /chat availability (last 5m)
sum(rate(chat_requests_total{status="200"}[5m])) / sum(rate(chat_requests_total[5m]))

# /chat latency p95
histogram_quantile(0.95, rate(chat_duration_seconds_bucket[5m]))

# Materializer freshness
sum(rate(materializer_complete_total[5m])) / sum(rate(materializer_total[5m]))

# Graph integrity
sum(rate(graph_write_success_total[5m])) / sum(rate(graph_write_total[5m]))

# Error budget remaining (30d)
(1 - (error_count / total_count)) * 100
```

### Grafana Dashboard

```
Dashboard: SLO Overview
───────────────────────
Panel 1: /chat availability (gauge, target 99.9%)
Panel 2: /chat latency p95 (time series, target <3s)
Panel 3: Materializer freshness (gauge, target >95%)
Panel 4: Graph integrity (gauge, target >99%)
Panel 5: Error budget burn rate (time series)
Panel 6: Time to budget exhaustion (prediction)
```

---

## Alert Rules for SLOs

```yaml
groups:
- name: denis.slo
  interval: 30s
  rules:
  # SLO 1: /chat availability
  - alert: ChatAvailabilitySLOViolation
    expr: |
      (sum(rate(chat_requests_total{status="200"}[5m])) / sum(rate(chat_requests_total[5m]))) < 0.995
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "/chat availability < 99.5%"
      description: "Error budget burning fast"

  # SLO 2: /chat latency
  - alert: ChatLatencySLOViolation
    expr: histogram_quantile(0.95, rate(chat_duration_seconds_bucket[5m])) > 5
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "/chat p95 latency > 5s"

  # SLO 3: Materializer freshness
  - alert: MaterializerFreshnessSLOViolation
    expr: |
      (sum(rate(materializer_complete_total[5m])) / sum(rate(materializer_total[5m]))) < 0.90
    for: 10m
    labels:
      severity: high
    annotations:
      summary: "Materializer freshness < 90%"

  # SLO 4: Graph integrity
  - alert: GraphIntegritySLOViolation
    expr: |
      (sum(rate(graph_write_success_total[5m])) / sum(rate(graph_write_total[5m]))) < 0.95
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Graph integrity < 95%"
```

---

## Error Budget Policy

### When Budget is Healthy ( > 80%)
- Deploy new features freely
- Continue canary rollouts
- No restrictions

### When Budget is Burning (50-80%)
- Require 2 approvals for deploys
- Pause non-critical experiments
- Increase monitoring frequency

### When Budget is Critical (20-50%)
- Require 3 approvals for deploys
- Freeze new features
- Daily SLO review

### When Budget Exhausted
- Immediate incident declaration
- Full rollback to last stable
- Emergency post-mortem
- No deploys until resolved

---

## Burn Rate Alerts

| Burn Rate | Time to Exhaustion | Acción |
|-----------|-------------------|--------|
| > 10x | < 3 días | Page immediately |
| 3-10x | 10 días | Alert within 1h |
| 1-3x | 30 días | Alert within 24h |
| < 1x | > 30 días | Normal monitoring |

```promql
# Burn rate calculation (7d window)
error_rate_7d / (error_budget_30d / 30)
```

---

## SLO Report Template

```markdown
# SLO Report: [FECHA]

## Resumen Ejecutivo
- Estado general: 🟢🟡🔴
- Error budget remaining: [X]%

## Métricas

| SLO | Target | Actual | Budget | Status |
|-----|--------|--------|--------|--------|
| /chat availability | 99.9% | 99.95% | 85% | 🟢 |
| /chat latency p95 | <3s | 2.5s | 70% | 🟢 |
| Materializer freshness | >95% | 92% | 40% | 🟡 |
| Graph integrity | >99% | 99.5% | 90% | 🟢 |
| Telemetry availability | 99.9% | 99.9% | 95% | 🟢 |

## Incidents this Month
- [List incidents affecting SLOs]

## Next Actions
- [Action items]
```
