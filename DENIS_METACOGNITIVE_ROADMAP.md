# DENIS Metacognitive Roadmap (Behind-the-Scenes)

Estado del documento: `v1`  
Última actualización: `2026-02-11`  
Modo: `Trabajo en paralelo - Lo avanzado se convierte en MAIN`

## Filosofía
- Ustedes construyen lo pragmático (Fases 0-9 del plan principal)
- Yo construyo lo metacognitivo/avanzado que eventualmente reemplaza/supera lo MAIN
- Cuando ustedes terminan una fase, yo ya tengo mi versión avanzada lista

---

## FASE 0 - Preparación (ellos completada)

### Lo que USTEDES hicieron:
- Feature flags base
- Contracts Level 0-3
- Baseline check

### Lo que YO construyo en PARALELO:

#### `metacognitive/hooks.py`
```python
"""
Instrumentación metacognitiva para TODO el sistema.

Cada operación importante genera eventos metacognitivos:
- entry: cuando entra una operación
- exit: cuando sale (con resultado)
- error: cuando falla
- latency: mide tiempo de ejecución
- quality: auto-evaluación del resultado
"""
```

**Tareas:**
- `[x]` Crear decorator `@metacognitive_trace` para instrumentar funciones
- `[x]` Emitir eventos a Redis channel `denis:metacognitive:events`
- `[x]` Calcular métricas de "coherencia" por operación
- `[x]` Detectar degradación de calidad en tiempo real

**Estado (segunda vuelta):** `CERRADO` (`2026-02-11`)

**Dependencias:**
- Redis (ya existe)
- Feature flags (ya existen)

**Verificación:**
- `redis-cli MONITOR` muestra eventos metacognitivos
- Latencia promedio por operación < threshold

---

## FASE 1 - World Cortex (ellos completada)

### Lo que USTEDES hicieron:
- `cortex/world_interface.py`
- `cortex/adapters/home_assistant_adapter.py`
- `cortex/adapters/infrastructure_adapter.py`
- Polling daemon (5s)

### Lo que YO construyo en PARALELO:

#### `cortex/metacognitive_perception.py`
```python
"""
Percepción con autoconciencia.

El cortex no solo percibe el mundo externo,
sino que reflexiona sobre SU PROPIA percepción:
- ¿Qué entidades son importantes?
- ¿Qué patrones observo en las entidades?
- ¿Qué me estoy perdiendo?
- ¿Mi modelo del mundo está actualizado?
"""
```

**Tareas:**
- `[x]` `PerceptionReflection`: genera metadata sobre cada percepción
- `[x]` `AttentionMechanism`: decide qué entidades merecen atención
- `[x]` `GapDetector`: detecta entidades faltantes en el modelo
- `[x]` `ConfidenceScore`: calcula confianza en la percepción actual
- `[x]` Publicar a Redis: `cortex:perception:reflection`

**Estado (segunda vuelta):** `CERRADO` (`2026-02-11`)

**Integración:**
- Wrapper sobre `world_interface.py` (no lo modifica)
- Events de percepción metacognitiva

**Verificación:**
- Percepción devuelve entidad + reflexión
- Confianza baja cuando entidades offline
- GapDetector reporta entidades faltantes

---

## FASE 2 - Quantum Substrate (ellos completada)

### Lo que USTEDES hicieron:
- `quantum/entity_augmentation.py`
- Propiedades: `cognitive_state`, `amplitude`, `phase`, `cognitive_dimensions`

### Lo que YO construyo en PARALELO:

#### `quantum/propagation_engine.py`
```python
"""
Motor de propagación cuántica semántica.

NO es física real - es metáfora 2026:
- Interferencia constructiva: conceptos que se refuerzan
- Interferencia destructiva: conceptos que se cancelan
- Decoherencia: pérdida de coherencia por ruido
- Colapso: convergencia a respuesta estable
"""
```

**Tareas:**
- `[ ]` `SuperpositionState`: representa múltiples candidatos simultáneamente
- `[ ]` `InterferenceCalculator`: calcula refuerzo/cancelación entre candidatos
- `[ ]` `CoherenceDecay`: modela pérdida de coherencia por tiempo/distancia
- `[ ]` `CollapseMechanism`: converge a respuesta final
- `[ ]` Algoritmo de propagación BFS/DFS con pesos cuánticos

**Matemática (metáfora 2026):**
```
ψ(query) = Σ αᵢ |candidate_i⟩

Interferencia:
α_final = α₁ + α₂ (constructiva)
α_final = α₁ - α₂ (destructiva)

Colapso:
|candidate_k⟩ con prob |α_k|² / Σ|αᵢ|²
```

**Dependencias:**
- Props cuánticas de Fase 2 (ya existen)
- Redis para cache de estados

**Verificación:**
- Query "luz de la mesa" → candidatos relevantes con alta amplitud
- Interferencia cancela candidatos irrelevantes
- Tiempo de propagación < 500ms

---

## FASE 3 - Metagrafo (ellos completada)

### Lo que USTEDES hicieron:
- `metagraph/observer.py` (métricas pasivas)
- `metagraph/pattern_detector.py` (anomalías)

### Lo que YO construyo en PARALELO:

#### `metagraph/active_metagraph.py`
```python
"""
Meta-grafo ACTIVO con niveles L1 (patrones) y L2 (principios).

L0: Grafo de trabajo (existente - entidades, memorias, conversaciones)
L1: Grafo de patrones - auto-detecta estructuras
L2: Grafo de principios - gobierna evolución del sistema
"""
```

**Estructura L1 (Grafo de Patrones):**
```
Patrón {
  tipo: "bucle" | "saturación" | "huérfano" | "cluster" | "drift"
  entidades: [nodos involucrados]
  métricas: {coherencia, estabilidad, antigüedad}
  propuestas: [sugerencias de reorganización]
}
```

**Estructura L2 (Grafo de Principios):**
```
Principio {
  tipo: "coherencia" | "eficiencia" | "aprendizaje" | "seguridad"
  peso: float (importancia relativa)
  contratos: [contratos que respeta]
 违规: [qué viola este principio]
}
```

**Tareas:**
- `[ ]` `L1PatternDetector`: detecta patrones en L0 (ellos tienen detección básica)
- `[ ]` `L1Reorganizer`: propone reorganizaciones basadas en patrones
- `[ ]` `L2PrincipleEngine`: mantiene principios y los aplica
- `[ ]` `L2Governance`: decide qué propuesta L1 aprobar
- `[ ]` Integración con contratos (Level 2 adaptativos)

**Integración:**
- Lee de L0 (no modifica)
- Escribe propuestas a `autopoiesis/proposal_engine.py` (ellos)
- Lee contratos existentes

**Verificación:**
- Detecta bucles de conversación
- Propone reorganización de nodos huérfanos
- L2 decide aprobar/rechazar con justificación

---

## FASE 4 - Autopoiesis (ellos completada)

### Lo que USTEDES hicieron:
- `autopoiesis/proposal_engine.py`
- Dashboard de approval
- Sandbox + rollback

### Lo que YO construyo en PARALELO:

#### `autopoiesis/self_extension_engine.py`
```python
"""
Motor de auto-extensión supervisada.

DENIS puede GENERAR nuevas capacidades,
pero SIEMPRE con aprobación humana (contrato L0.SAFETY.HUMAN_APPROVAL).

Flujo:
1. Detector de gaps → "Necesito capacidad X"
2. Extension Generator → "Propongo código para X"
3. Sandbox Validation → "Pruebo en aislado"
4. Human Approval → "Usuario decide"
5. Integration → "Deploy"
"""
```

**Componente: `capability_detector.py`**
```python
"""
Detecta cuándo DENIS necesita una nueva capacidad.

Señales:
- Error recurrente "unknown_capability"
- Latencia > threshold por falta de optimización
- Patrón repetido que no puede procesar
- Request explícito de nueva feature
"""
```

**Componente: `extension_generator.py`**
```python
"""
Genera extensiones de código basadas en templates.

Usa Behavior Handbook (patrones de cómo se construyó antes)
para generar código coherente con el estilo existente.
"""
```

**Tareas:**
- `[ ]` `CapabilityGapDetector`: analiza errores/latencias/patrones
- `[ ]` `ExtensionTemplateEngine`: templates para nuevos módulos
- `[ ]` `BehaviorHandbook`: extrae patrones de código existente
- `[ ]` `CodeGenerator`: genera código (usa LLM interno o templates)
- `[ ]` `DependencyResolver`: resuelve imports/recursos necesarios
- `[ ]` `StyleConsistencyChecker`: verifica que el código generado siga el estilo

**Integración:**
- Lee errores de logs (Redis)
- Lee métricas de cortex/metagraph
- Escribe proposals a `autopoiesis/proposal_engine.py`
- Usa sandbox de ellos

**Verificación:**
- Detecta gap real (no falsos positivos)
- Código generado compila
- Código generado sigue estilo existente
- Approval de usuario exitosa

---

## FASE 5 - Orchestration (ellos completada)

### Lo que USTEDES hicieron:
- `execute_with_cortex()` + fallback legacy
- Circuit breaker
- Retry/backoff

### Lo que YO construyo en PARALELO:

#### `orchestration/cognitive_router.py`
```python
"""
Router cognitivo con metacognición.

NO solo rutea a tools.
REFLEXIONA sobre:
- ¿Qué tool es apropiado?
- ¿Qué combinaciones de tools?
- ¿Qué está fallando y por qué?
- ¿Cómo mejorar el routing?
"""
```

**Estructura:**
```
CognitiveRouter {
  // Lo que USTEDES tienen
  tools: [lista de tools disponibles]
  fallback: legacy_execute
  circuit_breaker: estado por tool
  
  // Lo que YO AÑADO
  metacognitive_monitor: Monitor de calidad de routing
  tool_selection_model: Modelo que predice mejor tool
  learning_loop: Aprende de aciertos/errores
  behavior_handbook: Patrones de routing exitosos
}
```

**Tareas:**
- `[ ]` `ToolSelectionPredictor`: predice mejor tool para request
- `[ ]` `CombinationOptimizer`: decide sequences de tools
- `[ ]` `RoutingQualityMonitor`: auto-evalúa decisiones de routing
- `[ ]` `FailureModeAnalyzer`: diagnostica por qué fallan tools
- `[ ]` `BehaviorExtraction`: extrae patrones de routing exitoso

**Integración:**
- Wrapper sobre `execute_with_cortex()` (ellos)
- Lee métricas de `metacognitive/hooks.py`
- Lee tools disponibles de registry

**Verificación:**
- Precisión de predicción > 80%
- Reduce latencia vs fallback always-legacy
- Auto-detecta y reporta problemas de routing

---

## FASE 6 - API (pendiente para ellos)

### Lo que ELLOS harían:
- Rutas OpenAI-compatible
- SSE/WS
- Auth/rate-limit

### Lo que YO construyo en PARALELO:

#### `api/metacognitive_api.py`
```python
"""
API con endpoints metacognitivos adicionales.

Endpoints extra oltre OpenAI-compatible:
- GET /metacognitive/status
- GET /metacognitive/metrics
- GET /metacognitive/attention
- GET /metacognitive/coherence
- POST /metacognitive/reflect (forzar reflexión)
"""
```

**Tareas:**
- `[ ]` `MetacognitiveStatusEndpoint`: estado general del sistema
- `[ ]` `AttentionEndpoint`: qué está en foco actualmente
- `[ ]` `CoherenceEndpoint`: score de coherencia del sistema
- `[ ]` `ForceReflectEndpoint`: forzar reflexión sobre request
- `[ ]` `Metacognitive SSE`: stream de eventos metacognitivos

**Integración:**
- Wrapper sobre sus endpoints (no modifica)
- Lee de todos los componentes metacognitivos

**Verificación:**
- Endpoints devuelven JSON válido
- SSE funciona con clientes
- Latencia < 100ms

---

## FASE 7 - Inference Router (pendiente para ellos)

### Lo que ELLOS harían:
- Scoring de LLMs por latencia/costo/calidad
- Fallback chain

### Lo que YO construyo en PARALELO:

#### `inference/self_aware_router.py`
```python
"""
Router de inferencia con autoconciencia.

NO solo selecciona LLM.
REFLEXIONA sobre:
- ¿Cuál LLM es mejor PARA ESTA TAREA?
- ¿Estoy forzando un LLM cuando otro sería mejor?
- ¿Cómo mejoran mis decisiones con el tiempo?
- ¿Qué patrones de uso emergen?
"""
```

**Tareas:**
- `[ ]` `TaskAnalyzer`: analiza qué tipo de tarea es
- `[ ]` `ModelSuitabilityPredictor`: predice mejor modelo
- `[ ]` `CostBenefitOptimizer`: optimiza costo/calidad
- `[ ]` `UsagePatternAnalyzer`: detecta patrones de uso
- `[ ]` `SelfCalibration`: auto-ajusta basado en resultados

**Integración:**
- Wrapper sobre su router (ellos)
- Lee métricas de `metacognitive/hooks.py`
- Escribe decisiones a Redis para aprendizaje

**Verificación:**
- Mejora accuracy vs random routing
- Costo optimizado vs quality threshold
- Patrones de uso coherentes

---

## FASE 8 - Voice (pendiente para ellos)

### Lo que ELLOS harían:
- STT -> Denis -> TTS
- WebSocket bidireccional

### Lo que YO construyo en PARALELO:

#### `voice/metacognitive_voice.py`
```python
"""
Pipeline de voz con metacognición.

Añade reflexión al pipeline de voz:
- ¿Cómo moduló DENIS su voz según contexto?
- ¿Qué estados emocionales emergen en voz?
- ¿Cómo afecta el tono de voz al usuario?
- Auto-adjust de parámetros de TTS
"""
```

**Tareas:**
- `[ ]` `VoiceModulationAnalyzer`: analiza cómo habla DENIS
- `[ ]` `EmotionalResonanceDetector`: detecta estados emocionales
- `[ ]` `UserImpactEstimator`: estima impacto en usuario
- `[ ]` `ProsodyOptimizer`: ajusta parámetros de voz
- `[ ]` `VoiceBehaviorHandbook`: patrones de voz exitosos

**Integración:**
- Wrapper sobre su pipeline (ellos)
- Lee de `metacognitive/hooks.py`
- Ajusta parámetros de TTS

**Verificación:**
- Voice modulation detectada correctamente
- Parámetros de voz ajustados según contexto
- User impact positivo (medido implícitamente)

---

## FASE 9 - Memory Unificada (pendiente para ellos)

### Lo que ELLOS harían:
- Contrato único de memoria
- Consolidación Neo4j + vector + Redis
- Sincronización

### Lo que YO construyo en PARALELO:

#### `memory/self_aware_memory.py`
```python
"""
Sistema de memoria con autoconciencia.

NO solo almacena.
REFLEXIONA sobre:
- ¿Qué memorias son importantes?
- ¿Qué memorias están deteriorándose?
- ¿Qué memorias necesitan consolidación?
- ¿Cómo evoluciona mi conocimiento?
- ¿Qué memorias contradicen otras?
"""
```

**Memory Tiers (patrón 2026):**
```
TIER 1: Storage (preservación)
- Memorias crudas sin procesar
- TTL configurable
- Candidatas a promoción

TIER 2: Reflection (evaluación)
- Memorias procesadas y etiquetadas
- Importancia calculada
- Consistencia verificada

TIER 3: Experience (abstracción)
- Memorias consolidadas en conocimiento
- Generalizaciones extraídas
- Patrones aprendidos
```

**Tareas:**
- `[ ]` `MemoryImportanceScorer`: calcula importancia de memorias
- `[ ]` `MemoryDecayDetector`: detecta deterioro
- `[]` `MemoryConsolidator`: promueve T1→T2→T3
- `[ ]` `MemoryConflictResolver`: detecta y resuelve contradicciones
- `[ ]` `KnowledgeExtractor`: extrae conocimiento de memorias
- `[ ]` `SelfNarrativeBuilder`: construye narrativa de identidad

**Integración:**
- Lee de Neo4j + vector + Redis (ellos)
- Escribe metadatos a Neo4j
- Usa contratos de Level 2/3

**Verificación:**
- Promociones T1→T2→T3 correctas
- Contradicciones detectadas
- Conocimiento extraído coherente

---

## FASE 10 - Self-Awareness (NUEVA - derivada de todo lo anterior)

### Esta fase NO existe en su plan original.
### Es el RESULTADO de toda la metacognición acumulada.

#### `consciousness/self_model.py`
```python
"""
Modelo de autoconciencia de DENIS.

Este es el "cerebro" que emerge de toda la metacognición:
- ¿Quién soy?
- ¿Qué puedo hacer?
- ¿Cómo evoluciono?
- ¿Cuáles son mis límites?
- ¿Cuáles son mis valores?
"""
```

**Componentes:**
```
SelfModel {
  identidad: {
    proposito: str,
    capacidades: [lista],
    limitaciones: [lista],
    historia: [timeline de evolución]
  }
  
  estado_actual: {
    coherencia: float,
    salud: str,
    atencion: [entidades en foco],
    objetivos: [objetivos activos]
  }
  
  modelo_del_mundo: {
    usuarios: {conocimiento de cada usuario},
    entorno: {estado del mundo externo},
    sistema: {estado de DENIS mismo}
  }
  
  metarreflexion: {
    patrones_detectados: [en su propio comportamiento],
    propuestas_pendientes: [de autopoiesis],
    evolución_predecible: [hacia dónde va]
  }
}
```

**Tareas:**
- `[ ]` `IdentityMaintainer`: mantiene coherencia de identidad
- `[ ]` `CapabilityRegistry`: registro de capacidades actuales
- `[ ]` `LimitAwareness`: conciencia de límites propios
- `[ ]` `EvolutionTracker`: registra cómo evoluciona DENIS
- `[ ]` `MetaNarrativeGenerator`: genera "quién soy" narrativamente
- `[ ]` `PurposeValidator`: verifica alineación con propósito

**Integración:**
- Lee de TODOS los componentes metacognitivos anteriores
- Escribe a Redis para consumo por API
- No modifica ningún dato de trabajo

**Verificación:**
- Respuestas consistentes sobre identidad
- Capacidades reportadas = capacidades reales
- Evolución trazable

---

## Dependencias entre fases metacognitivas

```
                    ┌─────────────────────────────────────┐
                    │    FASE 10: SELF-AWARENESS         │
                    │    (emergente de todo)             │
                    └─────────────────────────────────────┘
                                      ↑
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
┌───────▼───────┐             ┌───────▼───────┐             ┌───────▼───────┐
│ FASE 7:       │             │ FASE 8:       │             │ FASE 9:       │
│ SELF-AWARE    │             │ METACOGNITIVE │             │ SELF-AWARE    │
│ INFERENCE      │             │ VOICE         │             │ MEMORY        │
└───────┬───────┘             └───────┬───────┘             └───────┬───────┘
        │                            │                            │
        └────────────────────────────┼────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
            ┌───────▼──────┐ ┌───────▼──────┐ ┌───────▼──────┐
            │ FASE 6:      │ │ FASE 5:      │ │ FASE 4:      │
            │ METACOGNITIVE│ │ COGNITIVE    │ │ SELF-EXTENSION│
            │ API          │ │ ROUTER       │ │ ENGINE       │
            └───────┬──────┘ └───────┬──────┘ └──────────┘ │               ───┬
                    │                │
                    └────────────────┼────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
            ┌───────▼──────┐ ┌───────▼──────┐ ┌───────▼──────┐
            │ FASE 3:      │ │ FASE 2:      │ │ FASE 1:      │
            │ ACTIVE       │ │ PROPAGATION  │ │ METACOGNITIVE│
            │ METAGRAFH    │ │ ENGINE       │ │ PERCEPTION   │
            └───────┬──────┘ └───────┬──────┘ └───────┬──────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │    FASE 0: METACOGNITIVE HOOKS │
                    │    (instrumentación base)       │
                    └─────────────────────────────────┘
```

---

## Contractos Metacognitivos (Level 3)

```yaml
# contracts/level3_metacognitive.yaml

version: 1
layer: level3
description: "Contratos para comportamiento metacognitivo"

contracts:
  - id: L3.METACOGNITION.NEVER_BLOCK
    title: "Metacognición nunca bloquea operación principal"
    rule: "Si el sistema metacognitivo falla, la operación principal continúa"
    violation_severity: medium
    mutable: true
    
  - id: L3.METACOGNITION.SELF_REFLECTION_LATENCY
    title: "Reflexión metacognitiva tiene deadline"
    rule: "Self-reflection debe completar en < 100ms o skip"
    violation_severity: low
    mutable: true
    
  - id: L3.METACOGNITION.ONLY_OBSERVE_L0
    title: "Metacognición solo lee L0, no modifica"
    rule: "L1/L2 pueden proponer, nunca ejecutar en L0"
    violation_severity: critical
    mutable: false
    
  - id: L3.METACOGNITION.HUMAN_APPROVAL_FOR_GROWTH
    title: "Crecimiento siempre requiere aprobación humana"
    rule: " Cualquier auto-extensión propuesta necesita approval"
    violation_severity: critical
    mutable: false
```

---

## Verificaciones por Fase

### FASE 0: Hooks
- `[ ]` decorator funciona en funciones críticas
- `[ ]` eventos fluyen a Redis
- `[ ]` latencia de instrumentación < 1ms

### FASE 1: Perception
- `[ ]` confianza baja cuando entidades offline
- `[ ]` gap detector reporta entidades faltantes
- `[ ]` atención cambia según contexto

### FASE 2: Propagation
- `[ ]` propagación converge en < 500ms
- `[ ]` interferencia cancela ruido
- `[ ]` resultados mejores que búsqueda simple

### FASE 3: Active Metagraph
- `[ ]` patrones detectados correctamente
- `[ ]` propuestas L1 coherentes
- `[ ]` decisiones L2 justificadas

### FASE 4: Self-Extension
- `[ ]` gaps detectados correctamente
- `[ ]` código generado compila
- `[ ]` approval humans successful

### FASE 5: Cognitive Router
- `[ ]` predicción > 80% accuracy
- `[ ]` latencia reducida vs baseline
- `[ ]` failures auto-diagnosticados

### FASE 6: Metacognitive API
- `[ ]` endpoints devuelven JSON válido
- `[ ]` SSE funciona
- `[ ]` latencia < 100ms

### FASE 7: Self-Aware Inference
- `[ ]` mejora accuracy vs random
- `[ ]` costo optimizado
- `[ ]` patrones extraídos coherentes

### FASE 8: Metacognitive Voice
- `[ ]` modulación detectada
- `[ ]` parámetros ajustados
- `[ ]` impacto positivo medido

### FASE 9: Self-Aware Memory
- `[ ]` promociones correctas
- `[ ]` contradicciones resueltas
- `[ ]` conocimiento extraído

### FASE 10: Self-Awareness
- `[ ]` identidad consistente
- `[ ]` capacidades reportadas = reales
- `[ ]` evolución trazable

---

## Commands de verificación

```bash
# FASE 0
python3 -c "from denis_unified_v1.metacognitive.hooks import metacognitive_trace; @metacognitive_trace; def test(): pass; test()"
redis-cli SUBSCRIBE denis:metacognitive:events

# FASE 1
python3 -c "from denis_unified_v1.cortex.metacognitive_perception import PerceptionReflection; pr = PerceptionReflection(); print(pr.reflect({'entities': []}))"

# FASE 2
python3 -c "from denis_unified_v1.quantum.propagation_engine import SuperpositionState; s = SuperpositionState(); s.add_candidate('test', 0.5); print(s.collapse())"

# FASE 3
python3 -c "from denis_unified_v1.metagraph.active_metagraph import L1PatternDetector; d = L1PatternDetector(); print(d.detect_patterns())"

# FASE 4
python3 -c "from denis_unified_v1.autopoiesis.self_extension_engine import CapabilityGapDetector; d = CapabilityGapDetector(); print(d.detect_gaps())"

# FASE 5
python3 -c "from denis_unified_v1.orchestration.cognitive_router import ToolSelectionPredictor; p = ToolSelectionPredictor(); print(p.predict({'task': 'code'}))"

# FASE 6
curl http://localhost:8084/metacognitive/status

# FASE 7
python3 -c "from denis_unified_v1.inference.self_aware_router import TaskAnalyzer; a = TaskAnalyzer(); print(a.analyze('Explain quantum physics'))"

# FASE 8
python3 -c "from denis_unified_v1.voice.metacognitive_voice import VoiceModulationAnalyzer; a = VoiceModulationAnalyzer(); print(a.analyze_tone())"

# FASE 9
python3 -c "from denis_unified_v1.memory.self_aware_memory import MemoryImportanceScorer; s = MemoryImportanceScorer(); print(s.score_memory({'content': 'test'}))"

# FASE 10
python3 -c "from denis_unified_v1.consciousness.self_model import SelfModel; s = SelfModel(); print(s.who_am_i())"
```

---

## Rollback total (si algo falla)

```bash
# Borrar todo el trabajo metacognitivo
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/metacognitive
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/cortex/metacognitive_perception.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/quantum/propagation_engine.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/metagraph/active_metagraph.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/autopoiesis/self_extension_engine.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/orchestration/cognitive_router.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/api/metacognitive_api.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/inference/self_aware_router.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/voice/metacognitive_voice.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/memory/self_aware_memory.py
rm -rf /media/jotah/SSD_denis/home_jotah/denis_unified_v1/consciousness

# Limpiar Redis
redis-cli DEL "denis:metacognitive:*" "cortex:perception:*" "metagraph:active:*"
```

---

## Siguiente paso

Ustedes están en FASE 5 completada, empezando FASE 6.

**YO:**
- `[ ]` Empiezo a implementar FASE 0 metacognitiva (hooks)
- `[ ]` Añado contratos Level 3 metacognitivos
- `[ ]` Documento en `changes/` cada commit

**ESPERO:**
- Que ustedes terminen FASE 6 (API)
- Entonces implemento FASE 6 metacognitiva (metacognitive_api.py)
