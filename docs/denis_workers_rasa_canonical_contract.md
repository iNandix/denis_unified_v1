# Denis Persona + Workers + Rasa/ParLAI Canonical Contract

## Overview

Este contrato define el flujo canónico de decisión y ejecución en el sistema Denis:
```
Usuario → NLU (Rasa) → Templates (ParLAI) → ControlPlane → DenisPersona → Workers → Grafo
```

## Principios Inmutables

1. **Denis Persona es la única fuente de verdad** - Solo Denis decide qué ejecutar
2. **Rasa/ParLAI son tools, no decisores** - Proporcionan entendimiento y templates
3. **Workers son ejecutores paralelos** - No deciden, solo ejecutan órdenes de Denis
4. **Todo se persiste en grafo** - Cada decisión, ejecución y resultado va a Neo4j

## Arquitectura de Decisión

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUARIO                                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ prompt
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: RASA NLU (Entendimiento)                               │
│  • Detecta intent                                                │
│  • Extrae entidades                                              │
│  • Confianza 0.0-1.0                                            │
│  ↓ Si confianza < 0.7, pasa a ParLAI                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ intent + entities
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: PARLAI (Templates)                                     │
│  • Obtiene template desde grafo                                  │
│  • Enriquece contexto                                            │
│  • Si no hay template, genera uno básico                         │
│  ↓ Pasa contexto enriquecido                                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ enriched_context
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: CONTROL PLANE (Validación)                             │
│  • Verifica Constitución Level0                                  │
│  • Chequea DO_NOT_TOUCH                                          │
│  • Valida contra ApprovalEngine                                  │
│  ↓ Si pasa validación, genera CP                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ ContextPack
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 4: DENIS PERSONA (Decisión Final)                         │
│  • Evalúa complejidad                                            │
│  • Decide estrategia (simple/paralela)                           │
│  • Selecciona modelo (Opencode/Groq/OpenRouter/Local)            │
│  • Si complejidad >= 6: activa Workers                            │
│  ↓ Retorna ExecutionOrder                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ ExecutionOrder
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 5: WORKERS (Ejecución Paralela)                           │
│  • Worker1: SEARCH (símbolos, relaciones)                        │
│  • Worker2: ANALYSIS (dependencias, complejidad)                 │
│  • Worker3: CREATE (generación de código)                        │
│  • Worker4: MODIFY (cambios atómicos)                            │
│  ↓ Resultados consolidados                                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │ results
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  GRAFO (Neo4j) - Fuente de Verdad Persistente                    │
│  • (:Decision)-[:DECIDED_BY]->(:DenisPersona)                    │
│  • (:WorkerTask)-[:EXECUTED_IN]->(:Session)                      │
│  • (:ContextPack)-[:HAS_WORKER_TASK]->(:WorkerTask)              │
└─────────────────────────────────────────────────────────────────┘
```

## Contrato de Datos

### 1. Rasa NLU Output → ParLAI Input

```json
{
  "rasa_output": {
    "intent": {
      "name": "implement_feature",
      "confidence": 0.85
    },
    "entities": [
      {"entity": "technology", "value": "python"},
      {"entity": "file", "value": "auth.py"}
    ],
    "text": "crea un endpoint de autenticación",
    "timestamp": "2026-02-19T12:00:00Z"
  }
}
```

### 2. ParLAI Output → ControlPlane Input

```json
{
  "parlai_output": {
    "template_id": "tpl_implement_api_001",
    "template_name": "Implement API Endpoint",
    "context_enrichment": {
      "files_to_check": ["models.py", "schemas.py"],
      "dependencies": ["fastapi", "pydantic"],
      "similar_patterns": ["user_auth", "session_mgmt"]
    },
    "confidence": 0.78,
    "source": "neo4j_graph"
  }
}
```

### 3. ControlPlane Output → DenisPersona Input

```json
{
  "context_pack": {
    "cp_id": "cp_20260219_001",
    "mission": "Implementar endpoint de autenticación JWT",
    "intent": "implement_feature",
    "complexity": 7,
    "constraints": ["python", "fastapi", "jwt"],
    "files_to_read": ["models.py", "schemas.py", "auth.py"],
    "do_not_touch": ["kernel/__init__.py"],
    "risk_level": "MEDIUM",
    "constitution_checked": true,
    "human_approval_required": true
  }
}
```

### 4. DenisPersona Output → Workers Input

```json
{
  "execution_order": {
    "order_id": "ord_20260219_001",
    "decided_by": "DenisPersona",
    "complexity": 7,
    "strategy": "parallel",
    "workers_needed": 4,
    "model_selection": {
      "primary": "groq/llama-3.3-70b",
      "fallback": "openrouter/auto",
      "local": "llama3.2_local"
    },
    "execution_plan": [
      {"worker": "SEARCH", "task": "find_auth_symbols", "priority": 1},
      {"worker": "ANALYSIS", "task": "analyze_deps", "priority": 2, "depends_on": ["SEARCH"]},
      {"worker": "CREATE", "task": "generate_endpoint", "priority": 3, "depends_on": ["ANALYSIS"]},
      {"worker": "MODIFY", "task": "update_routes", "priority": 4, "depends_on": ["CREATE"]}
    ]
  }
}
```

### 5. Workers Output → Grafo

```json
{
  "worker_results": {
    "crew_id": "crew_20260219_001",
    "workers": [
      {
        "type": "SEARCH",
        "status": "completed",
        "output": {
          "symbols_found": 15,
          "symbols": [...],
          "time_ms": 2500
        }
      },
      {
        "type": "ANALYSIS",
        "status": "completed",
        "output": {
          "dependencies": [...],
          "issues": [...],
          "time_ms": 4200
        }
      },
      {
        "type": "CREATE",
        "status": "completed",
        "output": {
          "files_created": ["auth_endpoint.py"],
          "lines_of_code": 85,
          "time_ms": 8900
        }
      },
      {
        "type": "MODIFY",
        "status": "completed",
        "output": {
          "files_modified": ["routes.py", "main.py"],
          "changes": [...],
          "time_ms": 3400
        }
      }
    ],
    "consolidated": {
      "total_time_ms": 19000,
      "files_touched": 5,
      "symbols_modified": 12,
      "status": "success"
    }
  }
}
```

## Persistencia en Grafo (Cypher)

### Nodos Principales

```cypher
// Decisión de Denis Persona
CREATE (d:Decision {
  id: $decision_id,
  timestamp: datetime(),
  complexity: $complexity,
  strategy: $strategy,
  model_selected: $model
})

// ContextPack
CREATE (cp:ContextPack {
  id: $cp_id,
  mission: $mission,
  intent: $intent,
  risk_level: $risk_level
})

// Worker Task
CREATE (wt:WorkerTask {
  id: $task_id,
  worker_type: $worker_type,  // SEARCH|ANALYSIS|CREATE|MODIFY
  status: $status,
  started_at: datetime(),
  completed_at: datetime(),
  output: $output_json
})

// Sesión de ejecución
CREATE (s:Session {
  session_id: $session_id,
  started_at: datetime(),
  user_id: $user_id
})
```

### Relaciones

```cypher
// Denis decide el CP
MATCH (d:Decision {id: $decision_id})
MATCH (cp:ContextPack {id: $cp_id})
CREATE (d)-[:GENERATES]->(cp)

// CP tiene WorkerTasks
MATCH (cp:ContextPack {id: $cp_id})
MATCH (wt:WorkerTask {id: $task_id})
CREATE (cp)-[:HAS_WORKER_TASK]->(wt)

// WorkerTask ejecutado en Session
MATCH (wt:WorkerTask {id: $task_id})
MATCH (s:Session {session_id: $session_id})
CREATE (wt)-[:EXECUTED_IN]->(s)

// Denis conoce el resultado
MATCH (denis:Persona {name: 'Denis'})
MATCH (wt:WorkerTask {id: $task_id})
CREATE (denis)-[:KNOWS_FROM_WORKER]->(wt)
```

## Reglas de Validación

### 1. Rasa NLU debe:
- Retornar intent con confidence >= 0.5
- Extraer al menos 1 entidad si es relevante
- Persistir resultado en grafo como (:RasaIntent)

### 2. ParLAI debe:
- Consultar grafo para templates
- Retornar template_id válido o null
- Enriquecer contexto con símbolos relacionados

### 3. ControlPlane debe:
- Validar Constitución antes de generar CP
- Bloquear si hay violaciones críticas
- Generar CP con campos obligatorios completos

### 4. DenisPersona debe:
- Evaluar complejidad en rango 1-10
- Seleccionar modelo basado en disponibilidad
- Decidir workers_needed basado en complejidad
- Persistir decisión antes de ejecutar

### 5. Workers deben:
- Recibir ExecutionOrder válido
- Ejecutar en paralelo cuando sea posible
- Reportar progreso cada 2 segundos
- Persistir resultados al completar

## Ejemplos de Flujo Completo

### Ejemplo 1: Tarea Simple (Sin Workers)

```
Usuario: "Arregla typo en README"
↓
Rasa: intent="fix_typo", confidence=0.92
↓
ParLAI: template="fix_simple", context={file: "README.md"}
↓
ControlPlane: CP generado, risk=LOW
↓
Denis: complexity=1, strategy="simple", model="llama_local"
↓
Ejecución directa (sin workers)
↓
Grafo: (:Decision)-[:FIXES]->(:File)
```

### Ejemplo 2: Tarea Compleja (Con Workers)

```
Usuario: "Implementa sistema de autenticación completo"
↓
Rasa: intent="implement_feature", confidence=0.88, entities=[tech: jwt, scope: full]
↓
ParLAI: template="implement_auth_system", context={files: [models.py, routes.py], deps: [fastapi-jwt]}
↓
ControlPlane: CP generado, risk=MEDIUM, human_approval=true
↓
Denis: complexity=8, strategy="parallel", workers=4
↓
Workers:
  W1: SEARCH → 15 símbolos auth encontrados
  W2: ANALYSIS → 3 dependencias circulares detectadas
  W3: CREATE → auth_system.py generado (200 líneas)
  W4: MODIFY → 4 archivos actualizados
↓
Grafo consolidado con todos los nodos y relaciones
```

## MCP Tools Exposed

Para que Opencode use este sistema:

```python
# Tools disponibles
- rasa_parse(text) → RasaIntent
- parlai_get_template(intent) → ParLAITemplate  
- controlplane_generate_cp(context) → ContextPack
- denis_decide(cp) → ExecutionOrder
- workers_execute(order) → WorkerResults
- graph_persist(results) → bool
```

## Tests de Validación

```python
def test_full_flow_simple():
    """Flujo completo tarea simple (sin workers)"""
    result = denis_flow("Arregla typo")
    assert result.complexity == 1
    assert result.workers_needed == 0
    assert result.model == "llama_local"

def test_full_flow_complex():
    """Flujo completo tarea compleja (con workers)"""
    result = denis_flow("Implementa auth system")
    assert result.complexity >= 6
    assert result.workers_needed == 4
    assert result.strategy == "parallel"
    
def test_persistence():
    """Todo se persiste en grafo"""
    result = denis_flow("Crea endpoint")
    graph_result = query_neo4j("MATCH (d:Decision) RETURN count(d)")
    assert graph_result > 0
```

## Versiones

- **v1.0.0** (2026-02-19): Contrato inicial Denis+Workers+Rasa/ParLAI

## Aprobado Por

- Denis Persona (Orquestador)
- Control Plane (Validación)
- Neo4j Grafo (Persistencia)
