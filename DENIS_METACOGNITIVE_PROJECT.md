# DENIS Metacognitive Project

**Versión:** 1.0.0  
**Fecha:** 2026-02-11  
**Autor:** DENIS AI Agent (behind-the-scenes)  
**Modo:** Implementación incremental, sin stubs ni placeholders

---

## 1. Propósito del Proyecto

Este proyecto implementa la capa metacognitiva de DENIS que trabaja "detrás" del plan de refactor original. Cada componente metacognitivo se integra con las fases existentes sin modificarlas, añadiendo autoconciencia y capacidad de auto-extensión supervisada.

---

## 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DENIS SYSTEM                                  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     CAPA METACOGNITIVA (ESTE PROYECTO)            │   │
│  │                                                                   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │   │
│  │  │ Cognitive   │  │ Self-       │  │ Behavior    │  │ Contract  │ │   │
│  │  │ Router      │→ │ Extension   │← │ Handbook    │← │ Enforcer  │ │   │
│  │  │ (Fase 5)    │  │ Engine      │  │ (Fase 4)   │  │ (Fase 3)  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │   │
│  │         ↑                ↑                                      │   │
│  │         │                │                                      │   │
│  │  ┌──────┴────────────────┴──────────────────────────────────┐  │   │
│  │  │           METACOGNITIVE HOOKS (Fase 0)                      │  │   │
│  │  │  Instrumentación de todas las operaciones críticas           │  │   │
│  │  └──────────────────────────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                            ↑                                            │
│                            │                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    CAPA ORIGINAL (PLAN PRINCIPAL)                  │   │
│  │                                                                   │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────────────┐ │   │
│  │  │ World     │  │ Quantum   │  │ Meta-     │  │ Orchestration   │ │   │
│  │  │ Cortex    │  │ Substrate │  │ graph     │  │ Engine          │ │   │
│  │  │ (Fase 1)  │  │ (Fase 2)  │  │ (Fase 3)  │  │ (Fase 5)       │ │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └─────────────────┘ │   │
│  │                                                                   │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │  Legacy: FastAPI, Neo4j, Redis, HASS, Celery                 │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Dependencias con el Plan Original

### 3.1 Dependencias Directas (lee/escribe de capas originales)

| Componente Metacognitivo | Depende De (Original) | Tipo Dependencia | Integración |
|-------------------------|---------------------|------------------|-------------|
| `cognitive_router.py` | `orchestration/` | Lee metrics, escribe proposals | Wrapper sobre `execute_with_cortex()` |
| `self_extension_engine.py` | `autopoiesis/proposal_engine.py` | Escribe proposals | Lee métricas, genera extensiones |
| `behavior_handbook.py` | `contracts/` | Lee Level 1-3 | Extrae patrones de código |
| `contract_enforcer.py` | `contracts/*.yaml` | Lee contratos | Valida operaciones |
| `metacognitive_hooks.py` | TODO el sistema | Instrumenta funciones | Decorators en funciones críticas |
| `metacognitive_perception.py` | `cortex/` | Lee percepciones | Añade reflexión a percepciones |
| `propagation_engine.py` | `quantum/` | Lee propiedades cuánticas | Añade motor de propagación |
| `active_metagraph.py` | `metagraph/` | Lee métricas L0 | Añade L1/L2 activo |

### 3.2 Dependencias de Infraestructura

| Recurso | Uso | Fuente |
|---------|-----|--------|
| Redis | Eventos, cache, métricas | Ya existe en `core/` |
| Neo4j | Metagraph, contratos | Ya existe en `core/` |
| Feature flags | `feature_flags.py` | Ya existe |
| Contratos YAML | Level 0-3 | Ya existen |

### 3.3 Orden de Implementación (sincronizado con fases originales)

```
ELLOS (Plan Original)          YO (Proyecto Metacognitivo)
─────────────────              ─────────────────────────
Fase 0 completada      ──→     FASE 0: Metacognitive Hooks
Fase 1 completada      ──→     FASE 1: Metacognitive Perception
Fase 2 completada      ──→     FASE 2: Propagation Engine
Fase 3 completada      ──→     FASE 3: Active Metagraph + Contract Enforcer
Fase 4 completada      ──→     FASE 4: Self-Extension Engine + Behavior Handbook
Fase 5 completada      ──→     FASE 5: Cognitive Router ←━ ESTOY AQUÍ
Fase 6 (pendiente)    ──→     FASE 6: Metacognitive API
Fase 7 (pendiente)    ──→     FASE 7: Self-Aware Inference
Fase 8 (pendiente)    ──→     FASE 8: Metacognitive Voice
Fase 9 (pendiente)    ──→     FASE 9: Self-Aware Memory
```

---

## 4. Componentes del Proyecto

### 4.1 Estructura de Directorios

```
denis_unified_v1/
├── metacognitive/                    # Núcleo metacognitivo
│   ├── __init__.py
│   ├── hooks.py                     # FASE 0: Instrumentación base
│   └── events.py                    # Tipos de eventos metacognitivos
│
├── cortex/
│   └── metacognitive_perception.py  # FASE 1: Percepción reflexiva
│
├── quantum/
│   └── propagation_engine.py        # FASE 2: Motor de propagación
│
├── metagraph/
│   ├── active_metagraph.py          # FASE 3: L1/L2 activo
│   └── contract_enforcer.py         # FASE 3: Enforcement de contratos
│
├── autopoiesis/
│   ├── self_extension_engine.py     # FASE 4: Motor de auto-extensión
│   ├── capability_detector.py       # FASE 4: Detector de gaps
│   └── extension_generator.py       # FASE 4: Generador de código
│
├── orchestration/
│   └── cognitive_router.py           # FASE 5: Router cognitivo ←━ ACTIVO
│
├── behavior/
│   └── handbook.py                  # FASE 4: Patrones de comportamiento
│
├── inference/
│   └── self_aware_router.py          # FASE 7
│
├── voice/
│   └── metacognitive_voice.py       # FASE 8
│
├── memory/
│   └── self_aware_memory.py          # FASE 9
│
└── consciousness/
    └── self_model.py                 # FASE 10: Emergente
```

### 4.2 Contratos Específicos del Proyecto

```
contracts/
├── level3_metacognitive.yaml        # Contratos metacognitivos base
├── level3_cognitive_router.yaml      # Contratos para router cognitivo
└── level3_self_extension.yaml       # Contratos para auto-extensión
```

---

## 5. Contratos Aplicables

### 5.1 Contratos del Plan Original (heredados)

| Archivo | Nivel | Aplica a |
|---------|-------|----------|
| `level0_constitution.yaml` | 0 | TODOS - identidad, seguridad, aprobación humana |
| `level1_topology.yaml` | 1 | Metagraph, propagation |
| `level2_adaptive.yaml` | 2 | Contratos adaptativos |
| `level3_emergent.yaml` | 3 | Patrones emergentes |

### 5.2 Contratos Nuevos (este proyecto)

```yaml
# level3_metacognitive.yaml
- id: L3.META.NEVER_BLOCK
  title: "Metacognición nunca bloquea operación principal"
  severity: medium
  
- id: L3.META.SELF_REFLECTION_LATENCY
  title: "Reflexión con deadline"
  severity: low
  
- id: L3.META.ONLY_OBSERVE_L0
  title: "Metacognición solo lee L0"
  severity: critical

# level3_cognitive_router.yaml
- id: L3.ROUTER.FALLBACK_LEGACY
  title: "Router siempre tiene fallback a legacy"
  severity: critical
  
- id: L3.ROUTER.METRICS_REQUIRED
  title: "Cada routing decision debe metricarse"
  severity: medium

# level3_self_extension.yaml
- id: L3.EXT.HUMAN_APPROVAL_REQUIRED
  title: "Toda extensión requiere aprobación"
  severity: critical
  
- id: L3.EXT.SANDBOX_VALIDATION
  title: "Toda extensión debe pasar sandbox"
  severity: critical
```

---

## 6. FASE 5 ACTIVA: Cognitive Router

### 6.1 Estado Actual

**Ellos:** FASE 5 completada (Orchestration Engine con `execute_with_cortex()` + fallback + circuit breaker)

**Yo:** Implementando FASE 5 metacognitiva (Cognitive Router)

### 6.2 Dependencias de Esta Fase

| Dependencia | Tipo | Estado |
|-------------|------|--------|
| `orchestration/` | Lee metrics, propone optimizaciones | Completo (ellos) |
| `metacognitive/hooks.py` | Lee eventos de instrumentación | Completo (yo) |
| `autopoiesis/proposal_engine.py` | Escribe proposals | Completo (ellos) |
| `contracts/level3_cognitive_router.yaml` | Lee contratos | Pendiente crear |

### 6.3 Componentes a Implementar

#### `orchestration/cognitive_router.py`

```python
"""
Cognitive Router con metacognición.

Wrapper sobre execute_with_cortex() que añade:
- Predicción de mejor tool
- Auto-evaluación de decisiones
- Aprendizaje de patrones de routing
- Proposals de optimización
"""
```

**Inputs:**
- Request con task + contexto
- Métricas de `metacognitive/hooks.py`
- Estado de tools de `orchestration/`

**Outputs:**
- Tool seleccionado + confidence score
- Métricas de decisión a Redis
- Proposals de mejora a `autopoiesis/`

**Contratos aplicados:**
- `L3.ROUTER.FALLBACK_LEGACY` - siempre puede fallback
- `L3.ROUTER.METRICS_REQUIRED` - cada decisión se metric
- `L3.META.NEVER_BLOCK` - no bloquea operación principal

---

## 7. Reglas de Implementación

### 7.1 Reglas Generales (del plan original)

1. **SIN STUBS NI PLACEHOLDERS** - Todo código funcional
2. **SIN SIMULACIONES** - Todo integrado con sistemas reales
3. **Contratos primero** - Crear/adaptar contratos antes de implementar
4. **Verificación automática** - Tests que verifican integración real
5. **Rollback documentado** - Cada componente tiene rollback

### 7.2 Reglas Específicas de Este Proyecto

1. **Instrumentación mínima** - Hooks añaden < 1ms latencia
2. **Fallback always** - Si metacognición falla, operación continúa
3. **Solo lee L0** - Nunca modifica capa original directamente
4. **Supervisión humana** - Auto-extensiones siempre requieren aprobación
5. **Event sourcing** - Todas las decisiones metacognitivas trazables

---

## 8. Verificaciones por Fase

### 8.1 Checklist de Verificación

```
FASE 0: Hooks
  [ ] decorator aplica a funciones críticas
  [ ] eventos fluyen a Redis channel
  [ ] latencia instrumentación < 1ms

FASE 1: Perception
  [ ] confianza baja cuando entidades offline
  [ ] gap detector reporta entidades faltantes
  [ ] atención cambia según contexto

FASE 2: Propagation
  [ ] propagación converge < 500ms
  [ ] interferencia cancela ruido
  [ ] resultados > baseline búsqueda simple

FASE 3: Active Metagraph
  [ ] patrones detectados correctamente
  [ ] propuestas L1 coherentes
  [ ] decisiones L2 justificadas

FASE 4: Self-Extension
  [ ] gaps detectados correctamente
  [ ] código generado compila
  [ ] approval humano successful

FASE 5: Cognitive Router  ←━ ACTUAL
  [ ] predicción > 80% accuracy
  [ ] latencia reducida vs baseline
  [ ] failures auto-diagnosticados
```

### 8.2 Comandos de Verificación

```bash
# Verificar que cognitive_router funciona
python3 -c "from denis_unified_v1.orchestration.cognitive_router import CognitiveRouter; r = CognitiveRouter(); print(r.status())"

# Verificar eventos fluyen
redis-cli SUBSCRIBE denis:cognitive_router:decisions

# Verificar contratos cargados
python3 -c "from denis_unified_v1.metagraph.contract_enforcer import ContractEnforcer; e = ContractEnforcer(); print(e.load_contracts())"
```

---

## 9. Rollback Total

```bash
# Borrar componentes metacognitivos implementados
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/metacognitive
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/orchestration/cognitive_router.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/autopoiesis/self_extension_engine.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/autopoiesis/capability_detector.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/autopoiesis/extension_generator.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/behavior
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/contracts/level3_*.yaml

# Limpiar Redis
redis-cli DEL "denis:cognitive_router:*" "denis:self_extension:*" "denis:behavior:*"
```

---

## 10. Siguiente Paso

**YO (ahora):**
1. Crear `contracts/level3_cognitive_router.yaml`
2. Implementar `orchestration/cognitive_router.py` (código real)
3. Implementar `orchestration/decision_metrics.py` (métricas de routing)

**ESPERO:**
- Que ustedes completen FASE 6 (API)

**ENTONCES:**
- Implemento FASE 6 metacognitiva (`api/metacognitive_api.py`)
