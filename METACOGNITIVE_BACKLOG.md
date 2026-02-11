# Metacognitive Backlog - Cierre de Gaps

**Fecha:** 2026-02-11  
**Propósito:** Alinear estado real vs documentación

---

## Tickets de Gap-Fixing

### TICKET 0.1: Contracts Registry Update
**Objetivo:** Registrar contratos L3 en registry

**Archivos:**
- `contracts/registry.yaml` - añadir L3.ROUTER, L3.EXT, L3.META

```yaml
- id: level3_cognitive_router
  path: level3_cognitive_router.yaml
  status: active
  
- id: level3_self_extension
  path: level3_self_extension.yaml
  status: active
  
- id: level3_metacognitive
  path: level3_metacognitive.yaml
  status: pending
```

---

### TICKET 0.2: Crear level3_metacognitive.yaml
**Objetivo:** Contratos base metacognitivos

```yaml
version: 1
layer: level3
description: "Contratos metacognitivos base"

contracts:
  - id: L3.META.NEVER_BLOCK
    title: "Metacognición nunca bloquea operación principal"
    severity: medium
    
  - id: L3.META.SELF_REFLECTION_LATENCY
    title: "Reflexión con deadline"
    severity: low
    
  - id: L3.META.ONLY_OBSERVE_L0
    title: "Metacognición solo lee L0"
    severity: critical
```

---

### TICKET F0: Metacognitive Hooks
**Depende:** TICKET 0.1, TICKET 0.2  
**Archivo:** `metacognitive/hooks.py`

**Features:**
- `@metacognitive_trace` decorator
- Eventos a Redis: `denis:metacognitive:events`
- Métricas de latencia por operación

---

### TICKET F1: Metacognitive Perception
**Depende:** TICKET F0  
**Archivo:** `cortex/metacognitive_perception.py`

**Features:**
- `PerceptionReflection` - metadata sobre cada percepción
- `AttentionMechanism` - decide qué entidades importan
- `GapDetector` - detecta entidades faltantes
- `ConfidenceScore` - calcula confianza

---

### TICKET F2: Propagation Engine
**Depende:** TICKET F1  
**Archivo:** `quantum/propagation_engine.py`

**Features:**
- `[x]` `SuperpositionState` - múltiples candidatos simultáneamente
- `[x]` `InterferenceCalculator` - refuerzo/cancelación
- `[x]` `CoherenceDecay` - pérdida de coherencia
- `[x]` `CollapseMechanism` - convergencia a respuesta
- `[x]` `SimilarityCalculator` - similaridad entre candidatos
- `[x]` `PropagationEngine` - motor principal orchestrado

---

### TICKET F3: Active Metagraph
**Depende:** TICKET F2  
**Archivos:**
- `metagraph/active_metagraph.py`
- `metagraph/contract_enforcer.py`

**Features:**
- L1PatternDetector - detecta patrones
- L1Reorganizer - propone reorganizaciones
- L2PrincipleEngine - mantiene principios
- L2Governance - decide aprobar/rechazar

---

### TICKET F4: Self-Extension Engine
**Depende:** TICKET F3  
**Archivo:** `autopoiesis/self_extension_engine.py`

**Features:**
- `SelfExtensionOrchestrator` - coordina todo el flujo
- Integración con capability_detector
- Integración con extension_generator
- Integración con behavior_handbook

---

## Estado Actual vs Esperado

| Componente | Existe | Estado |
|------------|--------|--------|
| `metacognitive/hooks.py` | ❌ | TICKET F0 |
| `cortex/metacognitive_perception.py` | ❌ | TICKET F1 |
| `quantum/propagation_engine.py` | ❌ | TICKET F2 |
| `metagraph/active_metagraph.py` | ❌ | TICKET F3 |
| `metagraph/contract_enforcer.py` | ❌ | TICKET F3 |
| `autopoiesis/self_extension_engine.py` | ❌ | TICKET F4 |
| `contracts/level3_metacognitive.yaml` | ❌ | TICKET 0.2 |
| `contracts/registry.yaml` (actualizado) | ⚠️ | TICKET 0.1 |

---

## Orden de Ejecución

```
TICKET 0.1 → TICKET 0.2 → TICKET F0 → TICKET F1 → TICKET F2 → TICKET F3 → TICKET F4
```

---

## Verificación Final

```bash
# Verificar todos los archivos existen
ls -la metacognitive/hooks.py
ls -la cortex/metacognitive_perception.py
ls -la quantum/propagation_engine.py
ls -la metagraph/active_metagraph.py
ls -la metagraph/contract_enforcer.py
ls -la autopoiesis/self_extension_engine.py
ls -la contracts/level3_metacognitive.yaml

# Verificar registry actualizado
grep -E "level3_(cognitive_router|self_extension|metacognitive)" contracts/registry.yaml
```

---

## Commitments

- [ ] TICKET 0.1: Actualizar registry
- [ ] TICKET 0.2: Crear level3_metacognitive.yaml
- [ ] TICKET F0: Implementar hooks
- [ ] TICKET F1: Implementar perception
- [ ] TICKET F2: Implementar propagation
- [ ] TICKET F3: Implementar active metagraph
- [ ] TICKET F4: Implementar self-extension engine
- [ ] Actualizar documentación
