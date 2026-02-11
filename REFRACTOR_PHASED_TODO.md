# DENIS Unified Engine - Plan Maestro Faseado + TODO

Estado del documento: `v1`  
Última actualización: `2026-02-11`  
Modo: `Refactor incremental augmentativo (sin romper legacy)`

## 1) Mapa de fases (como tu entrega)
Este plan respeta tu estructura por fases y la ejecuta en modo incremental:

1. `Fase 0`: Preparación y bootstrap seguro.
2. `Fase 1`: World Cortex (conexión mundo real).
3. `Fase 2`: Quantum Cognitive Substrate.
4. `Fase 3`: Meta-grafo e introspección.
5. `Fase 4`: Autopoiesis supervisada.
6. `Fase 5`: Orchestration Engine.
7. `Fase 6`: API e interfaces productivas.
8. `Fase 7`: Inference Router inteligente.
9. `Fase 8`: Voice pipeline completo.
10. `Fase 9`: Memory systems unificados.

## 2) Estado global actual (real)
- `[x]` `Fase 0` implementada y validada.
- `[~]` `Fase 1` implementada parcialmente (infra OK, HASS bloqueado por token inválido).
- `[x]` `Fase 2` (parte Neo4j quantum augmentation) implementada y ejecutada en real.
- `[ ]` `Fase 3` pendiente.
- `[ ]` `Fase 4` pendiente.
- `[ ]` `Fase 5` pendiente.
- `[ ]` `Fase 6` pendiente.
- `[ ]` `Fase 7` pendiente.
- `[ ]` `Fase 8` pendiente.
- `[ ]` `Fase 9` pendiente.

## 3) Evidencia resumida (ya ejecutada)
- Baseline actual: `denis_unified_v1/baseline_report.json`  
  Resultado: core en `8084` y STT en `8086` saludables.
- Quantum execute: `denis_unified_v1/phase1_augment_execute.json`  
  Resultado: `status=success`, nodos augmentados idempotentemente.
- Cortex smoke execute: `denis_unified_v1/phase2_cortex_smoke_execute.json`  
  Resultado: `node1/node2` OK, HASS conectado pero `Invalid HA API token`.

## 4) TODO maestro por fase

## Fase 0 - Preparación y bootstrap seguro
Objetivo: baseline + flags + evidencia antes de cambios de runtime.

Checklist:
- `[x]` Crear `feature_flags.py` con defaults seguros.
- `[x]` Crear baseline check y reportes (`DENIS_BASELINE.md`, JSON).
- `[x]` Ajustar baseline al core real `8084` (no `9999`).
- `[x]` Documentar rollback de scaffold.

Verificación:
- `python3 /home/jotah/denis_unified_v1/scripts/unified_v1_baseline_check.py --out-md /home/jotah/denis_unified_v1/DENIS_BASELINE.md --out-json /home/jotah/denis_unified_v1/baseline_report.json`

Rollback:
- `rm -rf /home/jotah/denis_unified_v1`

Riesgo:
- Bajo.

---

## Fase 1 - World Cortex (conexión mundo real) incremental
Objetivo: wrapper sobre integraciones reales (sin reimplementar).

Checklist:
- `[x]` Crear `cortex/world_interface.py`.
- `[x]` Crear `cortex/entity_registry.py`.
- `[x]` Crear `cortex/adapters/infrastructure_adapter.py`.
- `[x]` Crear `cortex/adapters/home_assistant_adapter.py`.
- `[x]` Añadir `cortex/config_resolver.py` para auto-carga de config existente (`.env*`, inventario red, JSON Denis HASS).
- `[~]` Validar `perceive_hass` en `ok` (pendiente token HASS válido).
- `[x]` Validar `perceive` infraestructura (node1/node2) en ejecución real.

Verificación:
- `python3 /home/jotah/denis_unified_v1/scripts/phase2_cortex_smoke.py --execute --out-json /home/jotah/denis_unified_v1/phase2_cortex_smoke_execute.json`

Bloqueo actual:
- Token HASS cargado automáticamente pero rechazado por HA (`Invalid HA API token`).

Rollback:
- `rm -rf /home/jotah/denis_unified_v1/cortex`
- `rm -f /home/jotah/denis_unified_v1/scripts/phase2_cortex_smoke.py`

Riesgo:
- Bajo-medio (I/O de red real).

---

## Fase 2 - Quantum Cognitive Substrate (Neo4j incremental)
Objetivo: augmentar nodos existentes sin romper queries legacy.

Checklist:
- `[x]` Crear `quantum/entity_augmentation.py`.
- `[x]` Crear mapping en `config/quantum_mapping.yaml`.
- `[x]` Crear CLI de execute y rollback.
- `[x]` Ejecutar augment real en Neo4j (`bolt://10.10.10.1:7687`).
- `[x]` Generar evidencia JSON de ejecución.
- `[x]` Dejar rollback ejecutable.

Verificación:
- `python3 /home/jotah/denis_unified_v1/scripts/phase1_quantum_augment.py --execute --out-json /home/jotah/denis_unified_v1/phase1_augment_execute.json`
- `python3 /home/jotah/denis_unified_v1/scripts/phase1_quantum_rollback.py --out-json /home/jotah/denis_unified_v1/phase1_rollback_dry_run.json`

Rollback:
- `python3 /home/jotah/denis_unified_v1/scripts/phase1_quantum_rollback.py --execute --out-json /home/jotah/denis_unified_v1/phase1_rollback_execute.json`

Riesgo:
- Medio-bajo (escritura idempotente en Neo4j).

---

## Fase 3 - Meta-grafo e introspección (pasivo)
Objetivo: observación analítica sin auto-mutaciones.

Checklist:
- `[ ]` Crear `metagraph/observer.py` (métricas de estructura).
- `[ ]` Crear `metagraph/pattern_detector.py` (anomalías).
- `[ ]` Crear `metagraph/dashboard.py` (read-only API local).
- `[ ]` Persistir métricas en Redis con TTL.
- `[ ]` Definir reporte horario y archivo de evidencia.

Verificación:
- `[ ]` endpoint/archivo de métricas con timestamp y recuentos consistentes.

Rollback:
- `[ ]` desactivar scheduler metagraph y borrar rutas read-only.

Riesgo:
- Bajo.

---

## Fase 4 - Autopoiesis supervisada
Objetivo: propuestas de cambio con aprobación humana obligatoria.

Checklist:
- `[ ]` Crear `autopoiesis/proposal_engine.py`.
- `[ ]` Crear `autopoiesis/dashboard.py` (`list`, `approve`, `sandbox`).
- `[ ]` Implementar transacción sin commit para validación.
- `[ ]` Marcar propuestas con `reversible=true` y plan de undo.
- `[ ]` Integrar con contratos nivel 0/1.

Verificación:
- `[ ]` propuesta se lista.
- `[ ]` aprobación hace sandbox y no rompe health.

Rollback:
- `[ ]` limpiar propuestas aprobadas pendientes y mantener `supervised`.

Riesgo:
- Medio.

---

## Fase 5 - Orchestration Engine augmentation
Objetivo: mejorar executor manteniendo fallback legacy.

Checklist:
- `[ ]` wrapper `execute_with_cortex()` con fallback a `execute()` legacy.
- `[ ]` retry/backoff/circuit breaker por tool.
- `[ ]` trazas de ejecución a Neo4j/Redis.
- `[ ]` A/B success-rate vs baseline legacy.

Verificación:
- `[ ]` success rate >= baseline.
- `[ ]` no degradación de latencia p95 > 10%.

Rollback:
- `[ ]` desactivar flag de cortex execution.

Riesgo:
- Medio.

---

## Fase 6 - API e interfaces productivas
Objetivo: exponer capa unificada sin romper contrato actual.

Checklist:
- `[ ]` añadir rutas nuevas compatibles (`/v1/chat/completions`, `/v1/models`), sin retirar legacy.
- `[ ]` SSE/WS para eventos.
- `[ ]` middleware auth/rate-limit/trace.
- `[ ]` health contract estable (`/health` + metadata).

Verificación:
- `[ ]` smoke de endpoints y compat OpenAI.

Rollback:
- `[ ]` feature flag de rutas nuevas + revert include_router.

Riesgo:
- Medio.

---

## Fase 7 - Inference Router inteligente
Objetivo: selección dinámica de LLM con fallback robusto.

Checklist:
- `[ ]` scoring por latencia/error/costo/contexto.
- `[ ]` fallback chain configurable.
- `[ ]` métricas por provider en Redis.
- `[ ]` decisión trazada por request_id.

Verificación:
- `[ ]` router responde con provider seleccionado y fallback cuando falla primario.

Rollback:
- `[ ]` forzar provider fijo por flag.

Riesgo:
- Medio.

---

## Fase 8 - Voice pipeline
Objetivo: STT -> Denis -> TTS con streaming estable.

Checklist:
- `[ ]` normalizar entrada/salida audio.
- `[ ]` integración websocket bidireccional.
- `[ ]` métricas de latencia por tramo.
- `[ ]` fallback de voz si servicio principal falla.

Verificación:
- `[ ]` prueba E2E con transcripción y respuesta hablada.

Rollback:
- `[ ]` desactivar pipeline unificado y mantener ruta de voz legacy.

Riesgo:
- Medio-alto.

---

## Fase 9 - Memory systems unificados
Objetivo: consolidar episódica/semántica/procedural/working sin romper persistencia actual.

Checklist:
- `[ ]` contrato único de memoria (esquema + rutas).
- `[ ]` consolidación Neo4j + vector + Redis TTL.
- `[ ]` sincronización y reparaciones automáticas supervisadas.
- `[ ]` métricas de consistencia entre backends.

Verificación:
- `[ ]` sync report consistente y sin pérdida de memoria.

Rollback:
- `[ ]` volver al flujo de memoria legacy y congelar writes nuevos.

Riesgo:
- Medio-alto.

## 5) Reglas de ejecución del refactor (obligatorias)
- Legacy siempre ON hasta pasar gate.
- Cada fase requiere:
  - comando de verificación,
  - evidencia escrita (`*.json` o `*.md`),
  - rollback ejecutable.
- No usar mocks para checks críticos de conectividad.
- No exponer secretos en logs/reportes.

## 6) Kanban rápido (siguiente acción)
- `NOW`: cerrar bloqueo Fase 1 con token HASS válido.
- `NEXT`: arrancar Fase 3 (metagraph pasivo) sin impacto en runtime.
- `LATER`: Fase 4 y 5 en paralelo por módulos.

