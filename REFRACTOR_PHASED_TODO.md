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
- `[x]` `Fase 1` implementada (infra OK, HASS OK, daemon polling OK).
- `[x]` `Fase 2` (parte Neo4j quantum augmentation) implementada y ejecutada en real.
- `[x]` `Fase 3` implementada y validada en modo pasivo (Neo4j + Redis).
- `[x]` `Fase 4` implementada y validada en modo supervisado (proposal + sandbox + approve).
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
  Resultado: HASS + infra OK, nodomac añadido, Tailscale IPs configuradas.
- Cortex polling daemon: `cortex_polling_daemon.py`  
  Resultado: daemon funcional (5s intervalo, publicando a Redis).
- Metagraph snapshot: `denis_unified_v1/phase3_metagraph_snapshot.json`  
  Resultado: `status=ok`, persistencia Redis `ok`, detección de anomalías en modo solo-observación.
- Autopoiesis smoke: `denis_unified_v1/phase4_autopoiesis_smoke.json`  
  Resultado: `status=ok`, propuestas generadas, sandbox con rollback y aprobación supervisada.

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
- `[x]` Validar `perceive_hass` con entidades reales (`light.led_mesa_1`, `light.led_mesa_2`).
- `[x]` Validar `perceive` infraestructura (node1/node2/nodomac) con IPs Tailscale.
- `[x]` Token HASS actualizado y funcional.
- `[x]` Crear daemon de polling (`cortex_polling_daemon.py`) con intervalo configurable (default 5s).

Verificación:
- `python3 /home/jotah/denis_unified_v1/scripts/phase2_cortex_smoke.py --execute`
- `python3 /home/jotah/denis_unified_v1/scripts/cortex_polling_daemon.py --poll-interval 5`

Bloqueo resuelto:
- Token HASS actualizado en `.env.prod.local` y `.env.hass`.
- Nodomac añadido con IP `192.168.1.65`.
- Tailscale IPs configuradas para node1, node2, nodomac.

Rollback:
- `rm -rf /home/jotah/denis_unified_v1/cortex`
- `rm -f /home/jotah/denis_unified_v1/scripts/cortex_polling_daemon.py`
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
- `[x]` Crear `metagraph/observer.py` (métricas de estructura).
- `[x]` Crear `metagraph/pattern_detector.py` (anomalías).
- `[x]` Crear `metagraph/dashboard.py` (read-only API local).
- `[x]` Persistir métricas en Redis con TTL.
- `[x]` Definir reporte de snapshot y archivo de evidencia.

Verificación:
- `[x]` snapshot generado con timestamp y recuentos consistentes.
- `[x]` persistencia Redis `metagraph:metrics:latest` y `metagraph:patterns:latest`.

Rollback:
- `[x]` borrar módulo y script de snapshot (no hay auto-scheduler en esta fase).

Riesgo:
- Bajo.

---

## Fase 4 - Autopoiesis supervisada
Objetivo: propuestas de cambio con aprobación humana obligatoria.

Checklist:
- `[x]` Crear `autopoiesis/proposal_engine.py`.
- `[x]` Crear `autopoiesis/dashboard.py` (`list`, `approve`, `sandbox`).
- `[x]` Implementar transacción sin commit para validación.
- `[x]` Marcar propuestas con `reversible=true` y plan de undo.
- `[x]` Integrar con contratos nivel 0/1.

Verificación:
- `[x]` propuesta se lista.
- `[x]` aprobación hace sandbox y no rompe health.

Rollback:
- `[x]` borrar módulo/script y limpiar keys Redis (`autopoiesis:*`).

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
- `NOW`: arrancar Fase 5 (orchestration augmentation con fallback legacy).
- `NEXT`: Fase 6 (API unificada OpenAI-compatible con flags).
- `LATER`: Fase 7 (router de inferencia con fallback por métricas).

## 7) Contracts (transversal)
Ruta: `/home/jotah/denis_unified_v1/contracts`

Estado:
- `[x]` `registry.yaml`
- `[x]` `level0_constitution.yaml`
- `[x]` `level1_topology.yaml`
- `[x]` `level2_adaptive.yaml`
- `[x]` `level3_emergent.yaml`
- `[x]` `changes/README.md`
- `[x]` `changes/_template.md`
