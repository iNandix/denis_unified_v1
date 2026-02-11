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
- `[x]` `Fase 5` implementada y validada (executor DAG + fallback + circuit breaker).
- `[x]` `Fase 6` implementada y validada (OpenAI-compatible + health + stream + ws route).
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
- Orchestration smoke: `denis_unified_v1/phase5_orchestration_smoke.json`  
  Resultado: `status=ok`, plan de 4 tools ejecutado, fallback legacy y circuit breaker verificados.
- API smoke: `denis_unified_v1/phase6_api_smoke.json`  
  Resultado: `status=ok`, `/health`, `/v1/models`, `/v1/chat/completions`, stream SSE y ruta WS verificados.

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
- `[x]` wrapper `execute_with_cortex()` con fallback a `execute()` legacy.
- `[x]` retry/backoff/circuit breaker por tool.
- `[x]` trazas de ejecución a Neo4j/Redis.
- `[x]` smoke A/B funcional de ruta cortex y legacy.

Verificación:
- `[x]` plan smoke con `tools_succeeded=4`, `tools_failed=0`.
- `[x]` circuit breaker observado en `legacy.always_fail` tras fallos consecutivos.

Rollback:
- `[x]` desactivar flags `DENIS_USE_ORCHESTRATION_AUG=false`, `DENIS_USE_CORTEX=false`.
- `[x]` borrar módulo/script de fase.

Riesgo:
- Medio.

---

## Fase 6 - API e interfaces productivas
Objetivo: exponer capa unificada sin romper contrato actual.

Checklist:
- `[x]` añadir rutas nuevas compatibles (`/v1/chat/completions`, `/v1/models`), sin retirar legacy.
- `[x]` SSE/WS para eventos.
- `[x]` middleware auth/rate-limit/trace.
- `[x]` health contract estable (`/health` + metadata).

Verificación:
- `[x]` smoke de endpoints y compat OpenAI.

Rollback:
- `[x]` `DENIS_USE_API_UNIFIED=false`.
- `[x]` borrar módulo/script de fase.

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
- `NOW`: arrancar Fase 7 (router de inferencia con fallback por métricas).
- `NEXT`: Fase 8 (voice pipeline incremental sin romper canal actual).
- `LATER`: Fase 9 (consolidación de memorias y sincronización).

## 7) Contracts (transversal)
Ruta: `/home/jotah/denis_unified_v1/contracts`

Estado:
- `[x]` `registry.yaml`
- `[x]` `level0_constitution.yaml`
- `[x]` `level1_topology.yaml`
- `[x]` `level2_adaptive.yaml`
- `[x]` `level3_emergent.yaml`
- `[x]` `level3_cognitive_router.yaml`
- `[x]` `level3_self_extension.yaml`
- `[x]` `changes/README.md`
- `[x]` `changes/_template.md`

---

## 8) Metacognitive Project (paralelo)

**Propósito:** Implementación "detrás de escenas" de capacidades metacognitivas.

### Estado por fase metacognitiva

| Fase Metacognitiva | Depende De (Plan Original) | Estado | Evidencia |
|-------------------|---------------------------|--------|-----------|
| FASE 0: Hooks | FASE 0 completada | **CERRADO (2da vuelta)** | `metacognitive/hooks.py` |
| FASE 1: Perception | FASE 1 completada | **CERRADO (2da vuelta)** | `cortex/metacognitive_perception.py` |
| FASE 2: Propagation | FASE 2 completada | Pendiente | - |
| FASE 3: Active Metagraph | FASE 3 completada | Pendiente | - |
| **FASE 4: Self-Extension** | **FASE 4 completada** | **IMPLEMENTADO** | `capability_detector.py`, `extension_generator.py`, `behavior_handbook.py` |
| **FASE 5: Cognitive Router** | **FASE 5 completada** | **IMPLEMENTADO** | `orchestration/cognitive_router.py` |
| FASE 6: API | FASE 6 pendiente | Esperando | - |
| FASE 7: Self-Aware Inference | FASE 7 pendiente | Esperando | - |
| FASE 8: Metacognitive Voice | FASE 8 pendiente | Esperando | - |
| FASE 9: Self-Aware Memory | FASE 9 pendiente | Esperando | - |

### FASE 4 metacognitiva completada

**Componentes:**
- `autopoiesis/capability_detector.py` - Detecta gaps de capacidad
- `autopoiesis/extension_generator.py` - Genera código para extensiones
- `autopoiesis/behavior_handbook.py` - Extrae patrones de código existente
- `contracts/level3_self_extension.yaml` - Contratos específicos

**Contratos:**
- `L3.EXT.HUMAN_APPROVAL_REQUIRED`
- `L3.EXT.SANDBOX_VALIDATION`
- `L3.EXT.CODE_QUALITY_THRESHOLD`
- `L3.EXT.STYLE_CONSISTENCY`

**Features:**
- `[x]` CapabilityDetector - Analiza errores, latencias, patrones
- `[x]` ExtensionGenerator - Templates: basic_tool, cortex_adapter, memory_augment
- `[x]` BehaviorHandbook - Extrae patrones del código existente
- `[x]` Quality scoring basado en handbook

**Verificación:**
```bash
python3 -c "
from denis_unified_v1.autopoiesis.extension_generator import create_generator
gen = create_generator()
ext = gen.generate_tool(name='test-tool', description='Test')
print(f'Generated: {ext.id}, Quality: {ext.quality_score:.0%}')
"
```

### FASE 5 metacognitiva completada

**Componente:** `orchestration/cognitive_router.py`

**Contratos:** `contracts/level3_cognitive_router.yaml`

**Features:**
- `[x]` CognitiveRouter con scoring inteligente
- `[x]` Extracción de features del task
- `[x]` Estrategias: SMART, ROUND_ROBIN, LEGACY_FALLBACK
- `[x]` Métricas y eventos a Redis

### Siguiente

**YO:**
- `[ ]` Esperar FASE 6 completada (ellos)
- `[ ]` Implementar FASE 6 metacognitiva (`api/metacognitive_api.py`)

### Rollback metacognitivo parcial (FASE 4)
```bash
rm -f autopoiesis/capability_detector.py
rm -f autopoiesis/extension_generator.py
rm -f autopoiesis/behavior_handbook.py
rm -f contracts/level3_self_extension.yaml
redis-cli DEL "denis:self_extension:*"
```
