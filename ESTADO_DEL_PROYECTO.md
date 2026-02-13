# ESTADO DEL PROYECTO DENIS UNIFIED V1
## Fecha: 2026-02-13

---

## RESUMEN EJECUTIVO

**Estado General:** Sistema operativo pero con **servicios degradados** y **contratos pendientes**.

El proyecto DENIS Unified V1 está parcialmente implementado. Hay actividad en el grafo (10,689 nodos), pero varios componentes tienen problemas de datos nulos y la API unificada aún no está habilitada para producción.

---

## ESTADÍSTICAS DEL GRAFO NEO4J

| Métrica | Valor |
|---------|-------|
| Total Nodos | 10,689 |
| Total Relaciones | 14,094 |
| Nodos con Quantum Augmentation | 7,616 (71%) |
| Conscious States | 306 |
| Self-Reflections | 287 |
| Neuro Layers definidas | 24 |
| Memory Chunks | 130 |
| Tool Executions | 69 |
| Sessions | 93 |
| Events | 453 |

---

## IMPLEMENTACIÓN DE FASES

| Fase | Nombre | Estado | Nodos | Observaciones |
|------|--------|--------|------|---------------|
| **F0** | Metacognitive Hooks | ✅ Implementado | 2 | Instrumentación Redis activa |
| **F1** | Quantum Augmentation | ✅ Implementado | 7,616 | Propiedades quantum en 71% nodos |
| **F2** | Cortex | ✅ Implementado | 453 | Eventos de percepción |
| **F3** | Metagraph | ✅ Implementado | 859 | GraphRoutes activos |
| **F4** | Autopoiesis | ✅ Implementado | 1,188 | AgentScans registrados |
| **F5** | Orchestration | ✅ Implementado | 69 | ToolExecutions |
| **F6** | API Unified | ⚠️ Parcial | N/A | Corriendo en 8085, feature flags OFF |
| **F7** | Inference Router | ⚠️ Parcial | 6 | Shadow mode activo |
| **F8** | Voice Pipeline | ⚠️ Degradado | 4 | Pipecat caído |
| **F9** | Memory Unified | ✅ Implementado | 130 | Lectura/escritura activas |
| **F10** | Gate Hardening | ✅ Implementado | N/A | Sandboxing activo |
| **F11** | Sprint Orchestrator | ⚠️ Deshabilitado | 93 | Flag OFF |

---

## SERVICIOS ACTIVOS

### Puertos Principales

| Puerto | Servicio | Estado | Versión |
|--------|----------|--------|---------|
| 8084 | denis_persona_canonical | ⚠️ degraded | 1.1.0-canonical |
| 8085 | denis_unified_v1 (API) | ✅ healthy | unified-v1 |
| 8004 | denis_pipecat_canonical | ✅ healthy | 1.0.0-canonical |
| 5005 | Rasa NLU | ✅ active | N/A |
| 9997 | llama-server (qwen 3B) | ✅ active | N/A |
| 9998 | llama-server (coder 7B) | ✅ active | N/A |
| 19040 | MCP Server | ✅ active | N/A |
| 6379 | Redis | ✅ active | N/A |
| 7687 | Neo4j | ✅ running | 5.26.21 |

### Problemas Detectados

1. **Puerto 8084 (denis_persona):**
   - Estado: `degraded`
   - Causa: pipecat_events_fail: 105
   - Uptime: 24,896 segundos (~7 horas)

2. **Puerto 8004 (pipecat):**
   - Estado: `healthy` pero con eventos fallidos

3. **API Unified (8085):**
   - Feature flags mayoría en `false`
   - Solo inference_router y memory_unified activos

---

## CONTRATOS (GOVERNANCE)

### Level 0 (Constitución) - 4 contratos
- ✅ L0.IDENTITY.CORE
- ✅ L0.SAFETY.NO_SECRET_LOGGING  
- ✅ L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD
- ✅ L0.RESILIENCE.ROLLBACK_REQUIRED

### Level 3 (Implementación) - 60 contratos
- ✅ ~40 activos
- ⏳ ~15 en draft
- ❌ 7 pendientes (metacognitivos):
  - L3.META.NEVER_BLOCK
  - L3.META.SELF_REFLECTION_LATENCY
  - L3.META.ONLY_OBSERVE_L0
  - L3.META.HUMAN_APPROVAL_FOR_GROWTH
  - L3.META.EVENT_SOURCING
  - L3.META.QUALITY_GATE
  - L3.EMERGENT.PENDING

---

## QUANTUM AUGMENTATION (FASE 1)

El sistema tiene propiedades cuánticas en el 71% de los nodos:

```
Propiedades por nodo:
- cognitive_state: '{}'
- amplitude: 1.0
- phase: 0.0
- cognitive_dimensions: { contextual, emotional, historical_coherence, intentional }
- last_augmented: 2026-02-11 20:55:00
```

### Neuro Layers Definidas (24):
- L1_SENSORY, L2_WORKING, L3_EPISODIC, L4_SEMANTIC
- L5_PROCEDURAL, L6_SKILLS, L7_EMOTIONAL, L8_SOCIAL
- L9_IDENTITY, L10_RELATIONAL, L11_GOALS, L12_METACOG
- + variantes en español

### Mental Loops:
- PerceptionLoop
- CognitionLoop
- PlanningLoop
- ExecutionLoop

---

## CAPACIDADES ACTIVAS DEL AGENTE

```
- adaptive_cot (CoT adaptativo)
- speculative_decoding
- theory_of_mind
- hidden_intent_detection
- template_chunking
- self_reflection
- parallel_thinking
- voice_streaming
```

---

## PROBLEMAS IDENTIFICADOS

### Críticos
1. **Servicios degradados:** pipecat_19025 caído con 105 eventos fallidos
2. **Contratos pending:** 7 contratos metacognitivos sin activar
3. **Feature flags OFF:** API unified deshabilitada para producción

### Alto Prioridad
1. **Datos nulos:** Muchos nodos tienen propiedades importantes en null
2. **Conversaciones huérfanas:** `response: [missing_response_backfilled]`
3. **Tool executions con null:** Muchos registros sin tool_name

### Medio Prioridad
1. **Reorganización activa:** ~50 archivos en staging (git)
2. **Shims de empaquetado:** `denisunifiedv1/` añadidos pero no completos
3. **Tokens en .env:** Credenciales visibles en texto plano

---

## QUÉ ESTÁN HACIENDO LOS AGENTES

### Agentes Activos (procesos Python):

1. **denis_agent_autonomous.py** (PID 1476, 1477)
   - Modo: `mcp` y `monitor`
   - Estado: Ejecutando desde hace ~25 horas

2. **denis_unified_v1.api.fastapi_server** (PID 1315562)
   - Puerto 8085
   - Feature flags activos:
     - `denis_use_inference_router: true`
     - `denis_use_memory_unified: true`
     - `denis_enable_metagraph: true`
     - `denis_use_gate_hardening: true`

3. **denis_persona_canonical** (PID 991128)
   - Puerto 8084
   - Estado: degraded
   - Acciones: Procesando conversaciones, ejecutando tools

4. **denis_whisper_stt** (PID 1487)
   - STT para voz

5. **denis_pipecat_canonical** (PID 2459348)
   - Pipeline de voz completo

6. **denis_identity_api** (PID 2459226)
   - Gestión de identidad

7. **denis_tool_executor** (PID 2459349)
   - Ejecución de herramientas

8. **Celery Workers** (PID 12227-12241)
   - Cola autoheal

### Actividad Reciente en el Grafo:

- **Últimas tool executions:** `infra.perceive.node2`, `infra.perceive.nodomac`, `opencode`, `legacy.echo`
- **Últimos eventos:** `conversation.turn`, `interaction`
- **Último AgentScan:** 1771013043688 (timestamp unix)

---

## RECOMENDACIONES

### Inmediatas
1. Revisar el servicio pipecat en puerto 19025
2. Activar contratos metacognitivos pending
3. Habilitar feature flags de API unified gradualmente

### Corto Plazo
1. Limpiar datos nulos en nodos
2. Investigar conversaciones con `missing_response_backfilled`
3. Completar reorganización de código

### Medio Plazo
1. Migrar completamente a API unified (8085)
2. Habilitar Sprint Orchestrator
3. Completar contratos level 3 pending

---

## MÉTRICAS DE SALUD

| Métrica | Valor | Estado |
|---------|-------|--------|
| uptime_8084 | 24,896s | ⚠️ |
| pipecat_events_ok | 0 | ❌ |
| pipecat_events_fail | 105 | ❌ |
| neo4j | true | ✅ |
| redis | true | ✅ |
| rasa_nlu_5005 | true | ✅ |
| single_writer_8084 | true | ✅ |
| graph_first_enabled | true | ✅ |

---

*Reporte generado automáticamente del análisis del repositorio y estado de servicios.*
