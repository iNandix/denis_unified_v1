# AUDITORÍA TÉCNICA + PLAN HARDENING PRE-PROD
**Denis Control Plane v3.1.0**  
**Fecha:** 2026-02-18  
**Arquitecto:** IZQUIERDA  
**Estado:** Pre-Producción

---

## WS1: THREAT MODEL & RISK REGISTER

| ID | Riesgo | Tipo | Impacto | Prob | Señales de Detección | Mitigación Específica |
|----|--------|------|---------|------|---------------------|----------------------|
| R01 | **Loop infinito** por X-Denis-Hop bypass | Seguridad | 🔴 Alto | 🟡 Media | `X-Denis-Hop: 99` en logs, CPU 100%, latencia exponencial | Middleware rechaza hop > 3; test automático de loops; alerta si hop count anómalo |
| R02 | **Inyección de prompts** vía /chat | Seguridad | 🔴 Alto | 🟢 Baja | Patrones de jailbreak en logs de chat; tokens anómalos | Sanitización de input; rate limiting por IP; shadow mode para patrones sospechosos |
| R03 | **Abuso de APIs** (DoS) | Seguridad | 🟠 Medio | 🟡 Media | 429s masivos en logs; requests > 1000/min por IP | Rate limiting Redis-backed (60 req/min IP, 300 req/min user); circuit breaker automático |
| R04 | **Secrets leak** en logs/graph | Seguridad | 🔴 Alto | 🟢 Baja | Regex scan de logs buscando `sk-`, `Bearer`; auditoría de DecisionTrace.context | Redactor automático en middleware; campos sensibles excluidos de DecisionTrace; alerta si token aparece en log |
| R05 | **SSRF** vía HASS integration | Seguridad | 🟠 Medio | 🟢 Baja | URLs internas (169.254, 10.0.0.0/8) en requests a HASS | Whitelist de dominios HASS permitidos; validación de URL antes de conexión; sandbox de red |
| R06 | **Graph down** - SSoT no disponible | Fiabilidad | 🔴 Alto | 🟡 Media | Neo4j connection errors; queries timeout > 5s; DecisionTrace no escribe | Cache TTL 60s de provider chain; fail-open a config local; alerta PagerDuty si graph caído > 30s |
| R07 | **HASS flapping** (conexión inestable) | Fiabilidad | 🟡 Bajo | 🟡 Media | Reconexiones WebSocket > 5/min; entidades aparecen/desaparecen | Exponential backoff en reconnect (max 5 min); modo "stub" automático si flapping > 3 ciclos; cache de último estado conocido 5 min |
| R08 | **Nodomac stale** - snapshot viejo | Fiabilidad | 🟠 Medio | 🟢 Baja | `last_scan` > 24h; overlay_scan no ejecutado; files not found | Alerta si last_scan > 6h; fallback a filesystem scan local si manifest stale; Control Room trigger automático de re-scan |
| R09 | **Overload** - throughput excesivo | Fiabilidad | 🔴 Alto | 🟡 Media | Latencia p95 > 2s; queue depth > 100; memory > 80% | Autoscaling (si k8s) o rate limiting estricto; degradación a local provider; 503 con Retry-After header |
| R10 | **Memory leak** en denis_agent | Fiabilidad | 🟠 Medio | 🟢 Baja | RSS crece > 100MB/hour; OOM kills en logs; GC pressure | Límite de memoria en systemd/docker (1GB); restart automático OOM; métricas de heap expuestas en /telemetry |
| R11 | **Config drift** - flags inconsistentes | Operación | 🟠 Medio | 🟢 Baja | FeatureFlag en Graph != env var; comportamiento inesperado | Preflight check en startup valida consistencia env vs graph; alerta si drift detectado; source of truth único (Graph) |
| R12 | **Silent failures** - errores no reportados | Operación | 🔴 Alto | 🟡 Media | Métricas de error rate bajas pero usuarios reportan problemas; DecisionTrace missing | Health check externo (synthetic) cada 1 min; correlación DecisionTrace vs requests totales; alerta si trace missing > 1% |

### Riesgos Priorizados (Top 5)
1. **R01** Loop infinito (Seguridad crítica)
2. **R06** Graph down (Fiabilidad core)
3. **R04** Secrets leak (Seguridad compliance)
4. **R12** Silent failures (Operación invisible)
5. **R09** Overload (Fiabilidad escalabilidad)

---

## WS2: FAILURE GAME DAYS (DRILLS)

### Game Day 1: Cloud Caído 24h
**Escenario:** ISP principal caído, solo nodomac conectado vía Tailscale

**Qué se rompe:**
- nodo1 inaccesible desde internet
- nodo2 (GPU) inaccesible
- Solo nodomac funciona localmente

**Comportamiento esperado:**
- denis_agent en nodomac entra modo "local only"
- /chat usa local_chat exclusivamente
- /health muestra "nodo1: down, nodo2: down"
- /hass/entities usa stub local

**Frontend muestra:**
- Banner rojo: "Modo supervivencia - Solo funcionalidad local"
- Chat funciona pero limitado (sin providers externos)
- Care dashboard vacío o modo demo

**Métricas/alertas:**
- 🔴 CRITICAL: `denis_node_offline{nodo="nodo1"} > 300` (5 min)
- 🔴 CRITICAL: `denis_node_offline{nodo="nodo2"} > 300`
- 🟡 WARNING: `denis_fallback_rate == 1.0` (100% local)

**Resolución:**
- ISP restaurado
- Health check pasa en nodo1/nodo2
- Gradual restoration de providers

---

### Game Day 2: Graph Lento / Inconsistencias
**Escenario:** Neo4j degradado, queries tardan 10s+, algunos timeouts

**Qué se rompe:**
- DecisionTrace writes fallan o tardan
- Provider chain reads lentos
- /health tarda en responder

**Comportamiento esperado:**
- Cache de provider chain (60s TTL) sirve requests
- DecisionTrace: fail-soft (no bloquea request)
- /health retorna cached state con "stale: true"

**Frontend muestra:**
- Banner amarillo: "Datos pueden estar desactualizados"
- Chat funciona (cache) pero más lento
- Ops dashboard marca "Graph degraded"

**Métricas/alertas:**
- 🔴 CRITICAL: `denis_graph_latency_p95 > 5000` (5s)
- 🟡 WARNING: `denis_graph_cache_hit_rate > 0.9` (excesivo caching)
- 🟡 WARNING: `denis_decision_trace_dropped > 0`

**Resolución:**
- Neo4j reiniciado / optimizado
- Cache hit rate vuelve a normal (< 0.5)
- DecisionTrace writes restaurados

---

### Game Day 3: Loop Storm con X-Denis-Hop
**Escenario:** Bug en frontend causa requests recursivos (A→B→A)

**Qué se rompe:**
- X-Denis-Hop incrementa indefinidamente
- CPU usage explota
- Latencia crece exponencialmente

**Comportamiento esperado:**
- Middleware detecta hop > 3, rechaza con 400
- Rate limiter bloquea IP después de 10 errores 400
- Alerta inmediata a seguridad

**Frontend muestra:**
- 400 Bad Request con mensaje: "Loop detected"
- Bloqueo temporal del usuario/IP

**Métricas/alertas:**
- 🔴 CRITICAL: `denis_loop_detected_rate > 0` (inmediato)
- 🔴 CRITICAL: `http_requests_400_total` spike
- 🔴 SECURITY: Alerta PagerDuty + email a security@denis

**Resolución:**
- Bug de frontend identificado y fixeado
- IP desbloqueado manualmente
- Post-mortem publicado

---

### Game Day 4: Nodomac Solo con Snapshot Viejo
**Escenario:** nodomac aislado, último overlay scan > 48h

**Qué se rompe:**
- Filesystem entries desactualizados
- Paths pueden no existir
- Manifests stale

**Comportamiento esperado:**
- /overlay/resolve intenta paths, falla silenciosamente
- Fallback a filesystem scan directo (lento pero funciona)
- Control Room intenta re-scan cada 1h

**Frontend muestra:**
- Banner amarillo: "Índice de archivos desactualizado"
- Búsquedas lentas (direct FS scan)
- Algunos archivos "not found" si fueron movidos

**Métricas/alertas:**
- 🟡 WARNING: `denis_overlay_scan_stale_hours > 24`
- 🟡 WARNING: `denis_overlay_fs_fallback_rate > 0.1`
- 🔴 CRITICAL: `denis_overlay_not_found_rate > 0.05` (5%)

**Resolución:**
- Conectividad restaurada
- Control Room ejecuta overlay_scan manual
- Snapshot regenerado

---

### Game Day 5: Explosión de Latencia
**Escenario:** Latencia p95 salta de 200ms a 5s subitamente

**Qué se rompe:**
- User experience degradado
- Timeouts en frontend
- Circuit breakers se activan

**Comportamiento esperado:**
- Circuit breaker abre después de 5 errores consecutivos
- Fallback a local provider
- Rate limiting se activa para proteger

**Frontend muestra:**
- Spinner largo → timeout → "Servicio lento, intentando modo local"
- Mensajes aparecen con delay
- Banner de degradación

**Métricas/alertas:**
- 🔴 CRITICAL: `denis_latency_p95 > 2000` (2s)
- 🔴 CRITICAL: `denis_circuit_breaker_open == 1`
- 🟡 WARNING: `denis_fallback_rate > 0.5` (50%)

**Resolución:**
- Identificar causa (provider lento, red congestionada)
- Ajustar timeouts o cambiar provider preferido
- Circuit breaker cierra gradualmente

---

### Game Day 6: Rate Limit Sostenido
**Escenario:** Usuario legítimo supera 60 req/min durante 10 minutos

**Qué se rompe:**
- Usuario bloqueado temporalmente
- Potencial pérdida de requests legítimos

**Comportamiento esperado:**
- HTTP 429 con Retry-After: 60 header
- Usuario puede continuar después de cooldown
- No afecta a otros usuarios

**Frontend muestra:**
- "Rate limit exceeded. Please slow down."
- Retry automático con backoff exponencial

**Métricas/alertas:**
- 🟡 WARNING: `http_requests_429_total` spike
- 🟡 INFO: `denis_rate_limit_hit{user="xxx"}` (no alerta, solo log)

**Resolución:**
- Usuario reduce frecuencia
- O: contacta Ops para aumentar límite (premium)

---

### Game Day 7: Secrets Flood
**Escenario:** Bug accidental loggea API keys en stdout

**Qué se rompe:**
- Potencial exposición de secrets
- Compliance violation
- Necesidad rotación de keys

**Comportamiento esperado:**
- Alerta inmediata por patrón `sk-` en logs
- Logs redirigidos a storage seguro (no stdout)
- Servicio NO se detiene (availability > secrecy)

**Frontend muestra:**
- Nada (transparente)

**Métricas/alertas:**
- 🔴 CRITICAL: `denis_secrets_detected_in_logs > 0`
- 🔴 SECURITY: PagerDuty inmediato
- 🔴 SECURITY: Email a security@denis

**Resolución:**
- Bug fixeado
- Logs sanitizados
- Rotación de API keys afectadas
- Post-mortem + proceso mejorado

---

### Game Day 8: Partial Brownout
**Escenario:** Degradación parcial - solo Chat CP funciona, resto lento

**Qué se rompe:**
- /chat funciona normal
- /health, /hass, /telemetry tardan 10s+
- Graph writes fallan intermitentemente

**Comportamiento esperado:**
- Chat prioritario (ingreso principal)
- Ops endpoints usan cache extendido (5 min)
- DecisionTrace: buffer en memoria, flush cuando Graph vuelva

**Frontend muestra:**
- Chat funciona perfecto
- Ops dashboard "stale data" warning
- Care dashboard "temporarily unavailable"

**Métricas/alertas:**
- 🟡 WARNING: `denis_partial_degradation == 1`
- 🟡 WARNING: `denis_graph_write_buffer_size > 100`
- 🟢 INFO: `denis_core_functional == 1` (chat OK)

**Resolución:**
- Graph restaurado
- Buffer de DecisionTrace flushado
- Cache TTL vuelve a normal (60s)

---

## WS3: CONFIG & FEATURE FLAGS STRATEGY

### Jerarquía de Configuración

```
┌─────────────────────────────────────┐
│         RUNTIME (máxima)           │  ← graph FeatureFlag (hot reload)
├─────────────────────────────────────┤
│         ENVIRONMENT                 │  ← env vars (restart required)
├─────────────────────────────────────┤
│         CONFIG FILE                 │  ← config.yaml (restart required)
├─────────────────────────────────────┤
│         DEFAULTS (mínima)          │  ← código fuente
└─────────────────────────────────────┘

Resolución de conflictos: runtime > env > file > defaults
```

### 10 Flags/Configs Críticos

| Config | Source | Default | Rango | Qué Rompe si Mal | Validación Preflight |
|--------|--------|---------|-------|------------------|---------------------|
| `DENIS_ENABLE_CHAT_CP` | env | false | bool | Chat no funciona | Check: chat module importable |
| `DENIS_CHAT_CP_SHADOW_MODE` | env | false | bool | No logs de debugging | Warning si true en prod |
| `DENIS_CHAT_CP_GRAPH_WRITE` | env | false | bool | Sin audit trail | Warning si false en prod |
| `DENIS_RATE_LIMIT_RPM` | env | 60 | 10-1000 | Abuso o bloqueo legítimo | Test: 61 req/min -> 429 |
| `DENIS_HOP_MAX_DEPTH` | env | 3 | 1-5 | Loops o rechazos falsos | Test: hop=4 -> 400 |
| `DENIS_CACHE_TTL_SECONDS` | graph | 60 | 0-300 | Stale data o performance | Check: cache hit rate < 0.8 |
| `DENIS_CIRCUIT_BREAKER_THRESHOLD` | graph | 5 | 1-20 | Falsa apertura o cascada | Test: 5 errores -> circuit open |
| `DENIS_PROVIDER_CHAIN` | graph | ["anthropic","openai","local"] | array | Routing incorrecto | Check: todos los providers existen |
| `DENIS_LOCAL_MODE_BUDGET` | graph | 1000 | 0-unlimited | Coste excesivo o denegación | Alerta si > 80% consumido |
| `DENIS_HASS_ENABLED` | env | false | bool | Intentos de conexión fallidos | Check: HASS_URL válido si true |

### Preflight / Doctor Checks

```python
# En startup de denis_agent
def preflight_checks():
    checks = []
    
    # 1. Graph connectivity
    checks.append(check_graph_connection())
    
    # 2. FeatureFlag consistency
    checks.append(check_flag_consistency())
    
    # 3. Secrets availability (sin loggear valores)
    checks.append(check_secrets_present())
    
    # 4. Provider chain valid
    checks.append(check_provider_chain())
    
    # 5. Hop middleware loaded
    checks.append(check_hop_middleware())
    
    # 6. Rate limiter functional
    checks.append(check_rate_limiter())
    
    # 7. Cache operational
    checks.append(check_cache())
    
    # 8. DecisionTrace writable
    checks.append(check_graph_write())
    
    # Resultado
    if all(c.passed for c in checks):
        logger.info("✅ All preflight checks passed")
        return True
    else:
        for c in checks:
            if not c.passed:
                logger.error(f"❌ Preflight failed: {c.name} - {c.error}")
        return False
```

---

## WS4: STARTUP, SHUTDOWN & DEGRADE PATHS

### Secuencia de Arranque

```
┌────────────────────────────────────────────────────────────┐
│                    STARTUP SEQUENCE                         │
└────────────────────────────────────────────────────────────┘

1. ENV LOADING (500ms)
   ├─ Load .env
   ├─ Validate critical vars present (not values!)
   └─ FAIL if NEO4J_URI missing (no puede funcionar sin Graph)

2. PREFLIGHT CHECKS (2s)
   ├─ Graph connectivity test
   ├─ FeatureFlag consistency check
   ├─ Secrets availability check
   └─ FAIL si check crítico falla

3. CORE INITIALIZATION (3s)
   ├─ Redis connection (cache)
   ├─ Graph schema validation
   ├─ Provider chain load
   └─ Middleware stack setup

4. SERVICE DISCOVERY (1s)
   ├─ nodomac heartbeat
   ├─ nodo2 health check
   └─ HASS connectivity (if enabled)

5. API SERVER START (1s)
   ├─ FastAPI app init
   ├─ Router registration
   ├─ Middleware binding
   └─ Listen on :9999

Total: ~8s max
```

### Shutdown Limpio

```
┌────────────────────────────────────────────────────────────┐
│                   SHUTDOWN SEQUENCE                         │
└────────────────────────────────────────────────────────────┘

1. SIGTERM received
   └─ Set shutdown flag

2. DRAIN CONNECTIONS (30s timeout)
   ├─ Stop accepting new requests
   ├─ Wait for in-flight requests
   └─ 503 on new requests during drain

3. FLUSH DECISIONTRACE BUFFER (5s)
   ├─ Write pending traces to Graph
   └─ Log "X traces flushed" or "Y traces dropped"

4. CLOSE CONNECTIONS
   ├─ Redis disconnect
   ├─ Graph disconnect
   └─ HASS WebSocket close

5. EXIT
   └─ Code 0 (clean) or 1 (dirty if timeout)
```

### Caminos de Degradación

```
┌────────────────────────────────────────────────────────────┐
│                 DEGRADATION PATHS                           │
└────────────────────────────────────────────────────────────┘

SANO (100%)
├─ Graph: ✅
├─ Providers: Todos disponibles
├─ Cache: Hit rate ~40%
└─ Estado: 🟢 Healthy

DEGRADADO NIVEL 1 (Graph lento/caché)
├─ Graph: ⚠️ Latencia > 1s
├─ Action: Cache TTL extendido a 5 min
├─ Providers: Normal
└─ Estado: 🟡 Degraded (cached)

DEGRADADO NIVEL 2 (Providers caídos)
├─ Graph: ✅
├─ Providers: 🔴 Todos caídos
├─ Action: Fallback a local_chat
└─ Estado: 🟡 Degraded (local mode)

DEGRADADO NIVEL 3 (Graph caído + local)
├─ Graph: 🔴 Unreachable
├─ Providers: 🔴 Todos caídos  
├─ Action: Local config + stub responses
└─ Estado: 🟠 Critical (survival mode)

BLOQUEADO (Loop detected)
├─ X-Denis-Hop: > 3
├─ Action: 400 Bad Request
└─ Estado: 🔴 Blocked (security)
```

### Señales de Sistema Sano vs Riesgo

**SANO 🟢:**
- /health retorna < 100ms
- Error rate < 1%
- Graph latency < 200ms
- DecisionTrace write success > 99%
- All providers healthy OR fallback rate < 10%

**RIESGO 🟡:**
- /health > 500ms
- Error rate 1-5%
- Graph latency 200-1000ms
- Cache hit rate > 80% (excesivo)
- Fallback rate 10-50%

**CRÍTICO 🔴:**
- /health > 2s o 503
- Error rate > 5%
- Graph down > 30s
- Fallback rate > 50%
- Circuit breaker open

---

## WS5: OPERABILITY CHECKLIST (PRE-PROD)

### Observabilidad

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **Logs estructurados** | `journalctl -u denis-agent -o json` | JSON con fields: timestamp, level, request_id, endpoint |
| **Métricas Prometheus** | `curl localhost:9999/metrics` | Output exposition format válido |
| **DecisionTrace en Graph** | `MATCH (d:Decision) RETURN count(d)` | Count > 0 después de requests |
| **Distributed tracing** | Headers X-Denis-Request-ID en logs | Mismo ID en todos los logs de un request |
| **Health endpoint** | `curl /health` | < 100ms, status field present |

### Alertas

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **PagerDuty integrado** | Trigger alerta de prueba | PD recibe alerta, responde ACK |
| **Slack integrado** | Trigger warning de prueba | Mensaje en #denis-alerts |
| **Alertas críticas** | Simular graph down | Alerta < 30s, incluye runbook link |
| **Alertas ruidosas** | Revisar últimas 24h | < 5 alertas falsas |
| **Escalation path** | Documento en wiki | Página "On-call playbook" existe |

### Logs

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **No PII en logs** | Grep por emails/nombres | 0 matches |
| **No secrets en logs** | Grep por `sk-`, `Bearer` | 0 matches |
| **Log rotation** | `ls -la /var/log/denis/` | Files < 100MB, timestamps recientes |
| **Log retention** | Política documentada | 30 días definido en Loki/Splunk |
| **Log levels** | Check ERROR/WARN ratio | < 1% ERROR, < 10% WARN |

### Backups/Snapshots

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **Graph backup** | `ls /backups/neo4j/` | Backup < 24h old |
| **SQLite backup** | `ls /backups/nodomac.db/` | Backup < 24h old |
| **Config backup** | `git log --oneline -5` | Último commit < 1 semana |
| **Snapshot test** | Restore en staging | Funciona en < 30 min |
| **Backup encryption** | `file backup.tar.gz` | GPG encrypted o similar |

### Runbooks

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **On-call playbook** | `docs/runbook.md` | Existe, tiene 5+ procedimientos |
| **Game Days ejecutados** | Log de ejercicios | 8/8 Game Days completados |
| **Incident response** | Template en wiki | Template con roles, comunicación, timeline |
| **Escalation contacts** | Página "Contacts" | Lista con phone/Slack/email |
| **Rollback procedures** | Por cada PR en backlog | PR-1..PR-8 tienen rollback section |

### Tests Críticos

| Ítem | Cómo Verificar | Evidencia |
|------|----------------|-----------|
| **Unit tests** | `pytest tests/unit/ -q` | Pass > 90% |
| **Integration tests** | `pytest tests/integration/ -q` | Pass > 80% |
| **E2E tests** | `pytest tests/e2e/ -q` | Pass > 70% |
| **Load test** | `k6 run load_test.js` | Soporta 100 req/s sin errores |
| **Failover test** | Script de Game Day 1 | Sistema funciona en modo local |
| **Anti-loop test** | Script de Game Day 3 | Rechaza hop > 3 correctamente |
| **Secrets redaction test** | Grep de logs | 0 secrets leaked |

---

## WS6: COST & TOKEN GOVERNANCE

### Política de Budgets

| Fase | Budget Mensual | Qué Incluye | Qué Excluye | Acción si Excedido |
|------|---------------|-------------|-------------|-------------------|
| **P0** | $0 (local only) | Local provider, cache hits | Todos los providers externos | Block all external calls |
| **P0.5** | $100 (shadow) | Shadow mode logging, minimal real calls | Full production traffic | Switch to shadow mode |
| **P1** | $1000 (production) | Full production traffic | Exceso por abuso | Rate limiting estricto + alerta |
| **P2+** | $5000+ (scale) | Multi-region, backups, analytics | Experimentos sin ROI review | Budget approval required |

### Egress Modes

| Mode | Descripción | Cuándo Usar | Cómo Activar |
|------|-------------|-------------|--------------|
| **OFF** | Solo local provider | Emergencia, incidente de coste | `DENIS_EGRESS_MODE=off` |
| **SHADOW** | Logs calls pero no ejecuta | Testing, validación | `DENIS_EGRESS_MODE=shadow` |
| **ON** | Operación normal | Producción normal | `DENIS_EGRESS_MODE=on` (default P1) |

### Overrides Manuales

```bash
# Emergencia: apagar todo egress inmediatamente
curl -X POST http://nodo1:9999/admin/egress \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"mode": "off", "reason": "budget exceeded", "duration_minutes": 60}'

# Resultado: 200 OK, mode: off, all external providers disabled
```

### Métricas de Coste

| Métrica | Tipo | Descripción | Alerta |
|---------|------|-------------|--------|
| `denis_cost_usd_today` | Gauge | Coste acumulado hoy | 🟡 > 80% budget daily |
| `denis_cost_usd_this_month` | Gauge | Coste acumulado mes | 🔴 > 90% budget monthly |
| `denis_tokens_consumed_total` | Counter | Tokens totales consumidos | 🟡 > 10M tokens/day |
| `denis_external_calls_total` | Counter | Calls a providers externos | 🟡 > 10k calls/hour |
| `denis_cost_per_request_usd` | Gauge | Coste promedio por request | 🟡 > $0.01/request |

### Kill Switch Operacional

```python
# En denis_agent, check cada minuto
if cost_today > DAILY_BUDGET * 0.9:
    logger.warning("Approaching daily budget limit, throttling...")
    enable_strict_rate_limiting()

if cost_today > DAILY_BUDGET:
    logger.critical("DAILY BUDGET EXCEEDED - EGRESS DISABLED")
    set_egress_mode("off")
    alert_pagerduty("Cost budget exceeded, egress disabled")
    
    # Auto-restore next day
    schedule_restore(next_day_utc)
```

### Dashboard en Nodo2 (Frontend)

```
┌─────────────────────────────────────────┐
│  COST DASHBOARD                         │
├─────────────────────────────────────────┤
│  Today: $45.20 / $100 (45%) 🟢          │
│  This Month: $890 / $1000 (89%) 🟡      │
│                                         │
│  Tokens: 2.3M consumed today            │
│  Avg cost/req: $0.003                   │
│                                         │
│  [🔴 EMERGENCY SHUTDOWN]                │
│  (Requires admin confirmation)          │
└─────────────────────────────────────────┘
```

---

## WS7: FRAGILITY ANALYSIS & QUICK WINS

### Top 5 Puntos Más Frágiles Hoy

1. **Graph es SPOF**
   - Por qué: Sin Graph, no hay provider chain, no hay DecisionTrace
   - Impacto: 🔴 Crítico
   - Quick Win: Cache extendido + fallback a config local

2. **Sin rate limiting**
   - Por qué: Cualquier IP puede hacer DoS
   - Impacto: 🔴 Crítico
   - Quick Win: In-memory rate limit (60 req/min)

3. **Secrets en código/env**
   - Por qué: Riesgo de leak en logs/repos
   - Impacto: 🔴 Crítico
   - Quick Win: Migración a keyring/os.environ solo

4. **No circuit breaker**
   - Por qué: Cascada de fallos si provider lento
   - Impacto: 🟠 Medio
   - Quick Win: Simple threshold (5 errores -> open)

5. **Observabilidad débil**
   - Por qué: Silent failures posibles
   - Impacto: 🟠 Medio
   - Quick Win: Health check sintético cada 1 min

### 5 Small Wins Técnicos de Alto Impacto

| # | Win | Tiempo | Impacto | Cómo Verificar |
|---|-----|--------|---------|----------------|
| 1 | **Cache provider chain 5 min** | 2h | 🟢 Alto | Graph down, chat sigue funcionando |
| 2 | **Rate limiting 60 req/min** | 4h | 🟢 Alto | 61 requests -> 429 |
| 3 | **Health check sintético** | 3h | 🟢 Alto | Alerta si /health tarda > 5s |
| 4 | **Log redaction regex** | 2h | 🟢 Alto | `sk-xxx` nunca aparece en logs |
| 5 | **Circuit breaker threshold=5** | 6h | 🟡 Medio | 5 errores -> fallback automático |

---

## GO/NO-GO CRITERIA FOR P1

### MUST HAVE (Sin esto, NO vamos a P1)

- [ ] **R01** Loop protection testeado y pasando
- [ ] **R04** Secrets redaction implementado
- [ ] **R06** Graph fail-open con cache > 5 min
- [ ] **Rate limiting** activo (60 req/min)
- [ ] **Health checks** reales (no stubs)
- [ ] **DecisionTrace** escribiendo 100% requests
- [ ] **Alertas críticas** configuradas (PagerDuty)
- [ ] **Runbooks** para 8 Game Days
- [ ] **Backup strategy** documentada y testeada
- [ ] **Cost monitoring** dashboard funcional

### SHOULD HAVE (Mejor tener, pero no bloquea)

- [ ] Circuit breaker (R04)
- [ ] HASS integration real (PR-2)
- [ ] Métricas Prometheus reales (PR-3)
- [ ] JWT auth (PR-6)
- [ ] Testing automatizado CI/CD (PR-7)

### NICE TO HAVE (P2+)

- [ ] Multi-region
- [ ] Advanced analytics
- [ ] ML-based anomaly detection
- [ ] Automated rollback
- [ ] Chaos engineering automatizado

---

## DECISIÓN FINAL

**Estado actual:** P0.5 STAGING ✅  
**Próximo milestone:** P1 PRODUCTION  
**Bloqueadores críticos:** 0 (con small wins implementados)  

**Recomendación:** 
- Implementar 5 small wins (1-2 días)
- Ejecutar 8 Game Days (1 semana)
- Validar Go/No-Go checklist
- **Go para P1** si todos los MUST HAVE pasan

**Riesgo residual:** Medio-Bajo con mitigaciones implementadas

**Firma:** IZQUIERDA  
**Fecha:** 2026-02-18  
**Versión:** v1.0
