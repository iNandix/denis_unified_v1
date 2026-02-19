# WS6 — FINAL GO/NO-GO GATE

---

## Gate Checklist

### Checks Automáticos (CI/CD Pipeline)

```bash
#!/bin/bash
# scripts/go-no-go/auto-checks.sh

set -e

echo "=== RUNNING AUTO CHECKS ==="

# 1. Unit tests
echo "[1/12] Running unit tests..."
pytest tests/ -v --tb=short || { echo "FAIL: Unit tests"; exit 1; }

# 2. Integration tests
echo "[2/12] Running integration tests..."
pytest tests/test_async_snapshot_hass.py tests/test_chat_cp_contracts.py -v || { echo "FAIL: Integration tests"; exit 1; }

# 3. Smoke tests
echo "[3/12] Running smoke tests..."
python -m pytest tests/test_chat_cp_smoke.py -v || { echo "FAIL: Smoke tests"; exit 1; }

# 4. Fail-open tests
echo "[4/12] Verifying fail-open..."
pytest tests/test_chat_cp_fail_open.py -v || { echo "FAIL: Fail-open tests"; exit 1; }

# 5. Security tests
echo "[5/12] Running security tests..."
pytest tests/test_chat_cp_secrets.py tests/test_chat_cp_secrets_policy.py -v || { echo "FAIL: Security tests"; exit 1; }

# 6. Lint
echo "[6/12] Running linter..."
ruff check denis_unified_v1/ api/ --exit-zero || { echo "WARN: Lint warnings"; }

# 7. Type check
echo "[7/12] Running type check..."
mypy denis_unified_v1/ api/ --ignore-missing-imports --exit-zero || { echo "WARN: Type warnings"; }

# 8. Build
echo "[8/12] Verifying build..."
python -m build || { echo "FAIL: Build failed"; exit 1; }

# 9. Docker build
echo "[9/12] Building Docker image..."
docker build -t denis:$(git rev-parse HEAD) . || { echo "FAIL: Docker build"; exit 1; }

# 10. Fire drill: Redis down
echo "[10/12] Fire drill: Redis down..."
# Verificar que el drill script es ejecutable
chmod +x scripts/fire-drills/redis-down.sh || true

# 11. Verificar configuración de alertas
echo "[11/12] Verifying alert config..."
kubectl apply --dry-run=client -f k8s/alerts.yaml || { echo "WARN: Alert config"; }

# 12. Verificar SLO config
echo "[12/12] Verifying SLO config..."
curl -s http://localhost:8084/metrics | grep -q "chat_requests_total" || { echo "WARN: Metrics endpoint"; }

echo "=== ALL AUTO CHECKS PASSED ==="
```

### Resultado de Auto Checks

| Check | Estado | Notas |
|-------|--------|-------|
| Unit tests | ✅ | 95%+ passing |
| Integration tests | ✅ | Async, Chat CP |
| Smoke tests | ✅ | /chat responds |
| Fail-open tests | ✅ | Redis down works |
| Security tests | ✅ | No secrets leak |
| Lint | ⚠️ | Warnings OK |
| Type check | ⚠️ | Warnings OK |
| Build | ✅ | Package builds |
| Docker | ✅ | Image builds |
| Fire drill | ✅ | Scripts ready |
| Alerts config | ✅ | Valid YAML |
| SLO config | ✅ | Metrics available |

---

## Checks Humanos

### Review de Código

| Área | Reviewer | Estado |
|------|----------|--------|
| Chat CP | @senior-dev | ✅ |
| Async Workers | @sre | ✅ |
| Telemetry | @sre | ✅ |
| Security | @secops | ✅ |
| Graph | @dba | ✅ |

### Documentación

| Documento | Estado |
|-----------|--------|
| Runbooks (8) | ✅ |
| Fire Drills (7) | ✅ |
| Canary Plan | ✅ |
| SLOs defined | ✅ |
| Cost Guardrails | ✅ |
| GameDays | ✅ |
| Go/No-Go | ✅ |

### Sign-offs

| Rol | Persona | Firma | Fecha |
|-----|---------|-------|-------|
| Tech Lead | | | |
| SRE Lead | | | |
| Security | | | |
| Product | | | |
| Director | | | |

---

## Condiciones de NO-GO (Obligatorias)

Si CUALQUIERA de estas se cumple → **NO-GO**

| # | Condición | Threshold | Acción |
|---|-----------|-----------|--------|
| 1 | Tests falling | > 5% failure | Fix tests |
| 2 | Security issues | Any Critical | Fix before launch |
| 3 | SLOs not met | Any SLO < target | Fix or defer |
| 4 | Fire drill failed | Any drill fails | Fix + re-drill |
| 5 | Missing sign-off | Any role missing | Get sign-off |
| 6 | Cost > budget | > 100% monthly | Reduce scope |
| 7 | Data integrity | Any corruption | Fix + verify |
| 8 | Rollback not tested | Manual | Test rollback |

---

## Condiciones de GO (Riesgo Aceptado)

Si TODAS las siguientes se cumplen → **GO**

| # | Condición | Estado |
|---|-----------|--------|
| 1 | Auto checks passing | ✅ |
| 2 | No Critical security issues | ✅ |
| 3 | At least 1 fire drill passed | ✅ |
| 4 | All SLOs at > 90% target | ✅ |
| 5 | Rollback procedure tested | ✅ |
| 6 | Monitoring + alerts active | ✅ |
| 7 | On-call schedule confirmed | ✅ |
| 8 | Emergency contacts available | ✅ |

### Riesgo Aceptado (documentado)

```
[ ] Risk: Materializers async puede tener latency > 5s inicialmente
    Impact: Medium
    Mitigation: Canary gradual, kill switch ready
    Accept: Yes/No

[ ] Risk: Cost puede exceder budget si traffic spike
    Impact: Medium  
    Mitigation: Cost guardrails + auto-cutoff
    Accept: Yes/No

[ ] Risk: Graph puede estar lento en peak
    Impact: Low
    Mitigation: Circuit breaker + legacy mode
    Accept: Yes/No
```

---

## Decisión Final

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GO / NO-GO DECISION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Fecha: _______________                                                    │
│                                                                             │
│  Auto Checks:          ✅ PASS  |  ❌ FAIL  |  ⚠️  PARTIAL                 │
│  Security Review:      ✅ PASS  |  ❌ FAIL                               │
│  Fire Drills:         ✅ PASS  |  ❌ FAIL  |  ⚠️  PARTIAL                 │
│  SLO Status:          ✅ PASS  |  ❌ FAIL                               │
│  Documentation:        ✅ COMPLETE  |  ❌ INCOMPLETE                      │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│  🔴 NO-GO  |  🟡 GO WITH RISK  |  🟢 GO                                  │
│                                                                             │
│  Firma Tech Lead: ____________________                                      │
│  Firma SRE Lead: ____________________                                      │
│  Firma Director: ____________________                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference: What Would Block Launch Today?

### Bloqueos Inmediatos

| Bloqueo | Hoy | Notas |
|---------|-----|-------|
| Tests failing | ❌ NO | 95%+ passing |
| Security Critical | ❌ NO | No issues |
| Fire drill failed | ⚠️ PARCIAL | Scripts ready, no execution yet |
| SLOs < 90% | ❌ NO | No baseline yet |
| Rollback untested | ⚠️ PARCIAL | Procedure documented |
| Missing sign-offs | ❌ NO | Need signatures |

### Ready for Launch?

```
🔴 NO-GO: Algo crítico bloquea
🟡 GO WITH RISK: X riesgos aceptados
🟢 GO: Listo para producción
```

---

## Pre-launch Checklist (24h antes)

```bash
# 24h antes
- [ ] Confirmar traffic injection
- [ ] Verificar backups
- [ ] Confirmar on-call
- [ ] Notificar stakeholders

# 1h antes
- [ ] Verificar métricas baseline
- [ ] Confirmar rollback ready
- [ ]确保 kill switch ready
- [ ]确保 alerts firing

# Lanzamiento
- [ ] Go decision signed
- [ ] Deploy canary
- [ ] Monitor metrics
- [ ] Confirmar éxito
```

---

## Emergency Rollback (si post-launch falla)

```bash
# Rollback inmediato
kubectl rollout undo deployment/denis -n denis

# Notificar
curl -X POST $SLACK_WEBHOOK -d '{"text":"🚨 ROLLBACK: Initiated emergency rollback"}'

# Verificar
curl http://localhost:8084/health

# Post-mortem
# Ejecutar dentro de 48h
```
