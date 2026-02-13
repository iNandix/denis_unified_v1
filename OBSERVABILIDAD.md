# Denis Unified V1 - Observabilidad Production-Grade

## Estado

| Servicio | Puerto | Estado |
|----------|--------|--------|
| Denis 8084 (canonical) | 8084 | ✅ Corriendo |
| Denis 8085 (unified+obs) | 8085 | ✅ Corriendo |
| Jaeger UI | 16686 | ✅ Corriendo |
| Prometheus | 9090 | ✅ Corriendo |
| Nginx LB | 8087 | ✅ Corriendo |

## Smoke Tests

```bash
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
python3 scripts/smoke_observability.py  # ✅ PASS
python3 scripts/smoke_migration.py      # ✅ PASS
```

## Dashboards

- **Jaeger** (traces): http://localhost:16686
- **Prometheus** (métricas): http://localhost:9090

## Métricas Disponibles

```bash
curl http://localhost:8085/metrics | grep "^denis_"
```

Métricas definidas en `observability/metrics.py`:
- `denis_requests_total` - Total requests por intent
- `denis_request_latency_seconds` - Latencia por fase
- `denis_ttft_seconds` - Time to first token
- `denis_smx_motor_calls_total` - Llamadas a motores SMX
- `denis_smx_motor_latency_seconds` - Latencia motores SMX
- `denis_cognitive_router_decisions_total` - Decisiones de routing
- `denis_l1_pattern_usage_total` - Uso de patterns L1
- `denis_system_health_score` - Health score (0-1)
- `denis_metacognitive_coherence_score` - Coherencia metacognitiva

## Alerting

```bash
curl http://localhost:8085/metacognitive/alerts
```

- Background task cada 60 segundos
- Detector de anomalías en TTFT, latencia, error rate
- Integración con L1PatternDetector
- Envío a Slack (configurar `SLACK_WEBHOOK_URL`)

## OpenTelemetry + Jaeger

Instrumentación en:
- `smx/client.py` - Spans en llamadas a motores
- `orchestration/cognitive_router.py` - Spans en decisiones de routing

Configuración en `observability/tracing.py`:
- Jaeger exporter en `localhost:6831`
- Auto-instrumentación FastAPI + httpx

## Migración Gradual

### Nginx Load Balancer

Puerto: **8087**

```nginx
upstream denis_backend {
    server 127.0.0.1:8085 weight=1;  # 10%
    server 127.0.0.1:8084 weight=9;  # 90%
}
```

### Script de Rollout

```bash
bash scripts/gradual_rollout.sh
```

Secuencia: 10% → 25% → 50% → 100%

### Comparación 8084 vs 8085

```bash
python3 scripts/compare_8084_8085.py
```

## Git Commits

- `0557a64` - Observabilidad Production-Grade + Migración Gradual
- `24171bf` - Fix: venv compatibility + observability

## Archivos Creados

```
observability/
├── tracing.py           # OpenTelemetry setup
├── metrics.py          # Prometheus metrics
└── anomaly_detector.py # Alerting + anomaly detection

scripts/
├── gradual_rollout.sh    # Rollout gradual
├── compare_8084_8085.py  # Benchmarking
├── smoke_observability.py # Test observabilidad
├── smoke_migration.py    # Test migración
└── nginx-denis-lb.conf  # Nginx config
```

## Iniciar 8085 Manualmente

```bash
cd /media/jotah/SSD_denis
source .venv_oceanai/bin/activate
python -c "
import sys; sys.path.insert(0, '/media/jotah/SSD_denis/home_jotah')
import uvicorn
from denis_unified_v1.api.fastapi_server import app
uvicorn.run(app, host='0.0.0.0', port=8085)
"
```

## Notas

- Puerto 8080 ocupado por Nextcloud → LB usa 8087
- Prometheus en Docker necesita IP del host (10.10.10.1)
- 8084 muestra "degraded" pero funciona
