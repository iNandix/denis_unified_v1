# WS4 — COST & CAPACITY GUARDRAILS

---

## Cost Drivers Principales

| Driver | Tipo | Costo Estimado | Notes |
|--------|------|----------------|-------|
| **Inference Providers** | Variable | $X,XXX/mês | Anthropic, OpenAI, Local |
| **Compute (API Workers)** | Fijo | $XXX/mês | Kubernetes pods |
| **Compute (Workers)** | Variable | $XX-XXX/mês | Celery workers scaling |
| **Redis** | Fijo | $XX/mês | Cache + rate limiting |
| **Neo4j** | Fijo | $XXX/mês | Graph DB |
| **Storage** | Variable | $XX/mês | Artifacts, logs |
| **Network** | Variable | $XX/mês | Egress, API calls |

---

## Budgets Mensuales

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MONTHLY BUDGET: $X,XXX/month                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Inference Providers    ████████████████████░░░░░░░░░░░  60%               │
│ Neo4j                 ██████░░░░░░░░░░░░░░░░░░░░░░  15%               │
│ API Workers           █████░░░░░░░░░░░░░░░░░░░░░░░░  10%               │
│ Redis                ██░░░░░░░░░░░░░░░░░░░░░░░░░░   5%               │
│ Storage              ██░░░░░░░░░░░░░░░░░░░░░░░░░░   5%               │
│ Other                █░░░░░░░░░░░░░░░░░░░░░░░░░░░   5%               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Hard Limits (Bloqueo Automático)

| Recurso | Límite | Acción Automática | Alert |
|---------|--------|-------------------|-------|
| **Inference spend/día** | $100/día | Bloquear nuevos requests | @ops |
| **Workers concurrent** | 20 | Bloquear auto-scale | @sre |
| **Graph writes/min** | 2000 | Drop writes no-críticos | @ops |
| **Storage used** | 50GB | Bloquear nuevos uploads | @ops |
| **Redis memory** | 2GB | Evict + alert | @ops |

### Implementación Hard Limits

```python
# denis_unified_v1/gates/cost_guardrail.py

class CostGuardrail:
    DAILY_INFERENCE_BUDGET = 100.00  # USD
    MAX_CONCURRENT_WORKERS = 20
    MAX_GRAPH_WRITES_PER_MIN = 2000
    MAX_STORAGE_GB = 50

    def check_inference_budget(self) -> bool:
        """Retorna True si hay budget disponible."""
        today_spend = self.get_today_inference_spend()
        if today_spend >= self.DAILY_INFERENCE_BUDGET:
            return False
        return True

    def check_worker_count(self) -> bool:
        """Retorna True si hay workers disponibles."""
        current = self.get_current_worker_count()
        return current < self.MAX_CONCURRENT_WORKERS
```

---

## Soft Limits (Degradación Automática)

| Recurso | Límite | Acción de Degradación | Alert |
|---------|--------|----------------------|-------|
| **Inference spend/hora** | $5/hora | Reducir candidatos de inferencia | @ops |
| **Queue depth** | 500 jobs | Drop oldest, requeue | @ops |
| **API concurrent** | 300 | Return 503 + retry-after | — |
| **Memory API** | 80% | Reducir cache | @ops |
| **Graph latency** | p99 > 2s | Legacy mode (no graph) | @sre |

### Implementación Soft Limits

```python
# denis_unified_v1/gates/cost_guardrail.py

class CostDegradation:
    def on_inference_budget_warning(self):
        """Reducir inferencia cuando > $5/hora."""
        # Reducir tool candidates de 5 a 2
        os.environ['MAX_TOOL_CANDIDATES'] = '2'
        # Notificar
        self.alert_slack("Inference budget warning: reducing candidates")

    def on_queue_growing(self, depth: int):
        """Drop oldest jobs when queue > 500."""
        if depth > 500:
            # Drop oldest 10%
            self.drop_oldest_jobs(percent=10)
            self.alert_slack(f"Queue growing: {depth}, dropping 10%")

    def on_memory_warning(self, percent: float):
        """Reducir cache cuando memory > 80%."""
        if percent > 80:
            # Clear non-essential caches
            self.clear_cache('decision_trace')
            self.clear_cache('intent_resolution')
            self.alert_slack(f"Memory warning: {percent}%, clearing caches")
```

---

## Runaway Cost Detection

### Señales de Runaway

| Señal | Threshold | Primera Acción |
|-------|-----------|---------------|
| **Inference spend rate** | > $10/hora por 10 min | Disable secondary engines |
| **Worker count** | > 15 por 30 min | Block auto-scale |
| **Queue growth rate** | +100/min por 10 min | Drop incoming jobs |
| **Graph write rate** | > 1500/min por 5 min | Batch writes |
| **Storage growth** | +1GB/hora | Delete old artifacts |

### Runaway Detection Query

```promql
# Inference spend rate
sum(inference_cost_per_minute) > 10

# Worker count
denis_workers_current > 15

# Queue growth
rate(celery_queue_length[10m]) > 100
```

### Acción Automática de Runaway

```bash
#!/bin/bash
# scripts/cost/runaway-prevention.sh

# Si inference spend > $10/hora por 10 min:
echo "🚨 RUNAWAY: Inference spend detected"
kubectl set env deployment denis DENIS_SECONDARY_ENGINES_ENABLED=false -n denis

# Si worker count > 15:
echo "🚨 RUNAWAY: Too many workers"
kubectl apply -f k8s/worker-max-scale.yaml

# Si queue growing:
echo "🚨 RUNAWAY: Queue growing"
curl -X POST http://localhost:8084/internal/drain-queue?percent=20
```

---

## Cost Alerts

```yaml
groups:
- name: denis.cost
  interval: 60s
  rules:
  - alert: InferenceBudgetWarning
    expr: inference_daily_spend > 80
    for: 5m
    labels:
      severity: high
    annotations:
      summary: "Inference spend > 80% of daily budget"

  - alert: InferenceBudgetCritical
    expr: inference_daily_spend > 100
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Inference budget exhausted"

  - alert: WorkerCountHigh
    expr: denis_workers_current > 15
    for: 10m
    labels:
      severity: high
    annotations:
      summary: "Worker count > 15 for 10 minutes"

  - alert: StorageNearLimit
    expr: storage_used_gb > 40
    for: 5m
    labels:
      severity: high
    annotations:
      summary: "Storage > 40GB (limit 50GB)"
```

---

## Capacity Planning

### Baseline (Mes actual)

| Recurso | Uso Actual | Capacidad | % Uso |
|---------|------------|-----------|-------|
| API workers | 4 | 8 | 50% |
| Celery workers | 4 | 20 | 20% |
| Redis memory | 500MB | 2GB | 25% |
| Neo4j memory | 2GB | 8GB | 25% |
| Storage | 10GB | 50GB | 20% |

### Proyección (3 meses)

```
                Month 1     Month 2     Month 3
─────────────────────────────────────────────────
API workers        4 → 6        6 → 8        8 → 10
Celery workers     4 → 8        8 → 12       12 → 16
Redis memory    500MB → 1GB   1GB → 1.5GB   1.5GB → 2GB
Storage          10GB → 20GB   20GB → 35GB   35GB → 50GB
```

### Scaling Triggers

| Recurso | Trigger | Acción |
|---------|---------|--------|
| API workers | CPU > 70% 5min | Scale +2 |
| Celery workers | Queue > 200 | Scale +2 |
| Redis | Memory > 1.5GB | Alert + consider upgrade |
| Neo4j | Memory > 6GB | Alert + upgrade |

---

## Cost Optimization

### Acciones de Optimización

| Área | Acción | Ahorro Estimado |
|------|--------|-----------------|
| Inference | Cache responses | 20-30% |
| Inference | Fallback a local | 40-60% |
| Workers | Right-size instances | 15-20% |
| Storage | Auto-delete > 30 días | 30-40% |
| Neo4j | Query optimization | 10-15% |

### Implementación

```python
# Cache de inferencia
@cache(ttl=3600)  # 1 hora
def cached_inference(prompt: str, model: str) -> str:
    return inference(prompt, model)

# Fallback a local
def get_inference(prompt: str) -> str:
    if cost_guardrail.check_inference_budget():
        return cloud_inference(prompt)
    else:
        return local_inference(prompt)  # Fallback más barato
```

---

## Budget Review Cadence

| Frecuencia | Qué | Quién |
|------------|-----|-------|
| Diario | Review spend vs budget | On-call |
| Semanal | Trend analysis | Ops Lead |
| Mensual | Forecast + adjustments | Finance + Tech |
| Trimestral | Strategic planning | Director |

---

## Emergency Cost Cutoff

### Procedimiento de Emergencia

```bash
# Emergency: Cortar costs inmediatamente
# 1. Deshabilitar inferencia cloud
kubectl set env deployment denis INFERENCE_CLOUD_ENABLED=false -n denis

# 2. Reducir workers al mínimo
kubectl scale deployment denis-workers --replicas=2 -n denis

# 3. Disable async
kubectl set env deployment denis ASYNC_ENABLED=false -n denis

# 4. Limpiar storage
find /data/artifacts -mtime +7 -delete

# 5. Notificar
curl -X POST $SLACK_WEBHOOK -d '{"text":"🚨 EMERGENCY: Cost cutoff activated"}'
```

### Tiempo de Activación
- **Total**: < 30 segundos
- **Efecto completo**: < 2 minutos
