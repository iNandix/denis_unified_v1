# AGENTS.md — Denis GodMode + Pipecat Voz + 4 Workers Paralelos

## Arquitectura Completa

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERFAZ DE USUARIO                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Texto     │  │    Voz      │  │      IDE/API            │ │
│  │  (Chat)     │  │  (Pipecat)  │  │   (Opencode/CLI)        │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
└─────────┼────────────────┼─────────────────────┼───────────────┘
          │                │                     │
          └────────────────┴──────────┬──────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 DENIS PERSONA (Orquestador Único)                │
│                                                                  │
│  • Única fuente de verdad                                        │
│  • Decide qué Agent/Worker usar                                  │
│  • Evalúa complejidad (CoT adaptativa)                           │
│  • Mantiene estado en Neo4j                                      │
│  • Voz e identidad: Pipecat conversacional                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │ decide()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTS (Herramientas)                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │   Rasa     │  │  ParLAI    │  │  Pipecat   │  │ Workers  │  │
│  │   (NLU)    │  │(Templates) │  │   (Voz)    │  │(Paralelo)│  │
│  │ Entiende   │  │  Responde  │  │  Habla     │  │ Ejecuta  │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  │
└────────┼───────────────┼───────────────┼──────────────┼────────┘
         │               │               │              │
         └───────────────┴───────┬───────┴──────────────┘
                                 │
                                 ▼
                    ┌─────────────────────┐
                    │  NEO4J (Grafo)      │
                    │  Fuente de Verdad   │
                    └─────────────────────┘
```

## Jerarquía de Control

```
Usuario
  ↓
Pipecat (Interfaz Conversacional - "La Voz de Denis")
  ↓
Denis Persona (Orquestador Único - Decide TODO)
  ↓
  ├─ Rasa (NLU - entiende, no decide)
  ├─ ParLAI (Templates - responde, no decide)
  ├─ Agents (Opencode/Groq/OpenRouter - ejecutan, no deciden)
  └─ Workers (Paralelos - trabajan, no deciden)
```

## Regla de Oro

**Denis Persona es el único que decide.**

- Pipecat habla, pero Denis decide qué decir.
- Rasa entiende, pero Denis decide qué hacer.
- ParLAI responde, pero Denis decide cómo.
- Workers ejecutan, pero Denis decide cuándo y qué.

## Los 4 Workers

### Worker 1: SEARCH (Búsqueda)
```python
role: "Buscador de Contexto"
goal: "Encontrar símbolos, archivos y relaciones en el grafo"
backstory: "Especialista en queries Cypher y vector search"

tasks:
  - find_symbol(name) → Neo4j
  - semantic_search(query) → Qdrant  
  - get_related_files(symbol) → Graph
  - discover_patterns(intent) → RedundancyDetector
```

### Worker 2: ANALYSIS (Análisis)
```python
role: "Analista de Código"
goal: "Analizar estructura, dependencias y calidad del código"
backstory: "Experto en AST, LSP y métricas de código"

tasks:
  - lsp_diagnostics(file) → pyright/langserver
  - analyze_dependencies(files) → import graph
  - calculate_complexity(code) → cyclomatic/halstead
  - detect_patterns(code) → tree-sitter
```

### Worker 3: CREATE (Creación)
```python
role: "Generador de Código"
goal: "Crear nuevos archivos, funciones y módulos"
backstory: "Especialista en generación determinista y templates"

tasks:
  - generate_function(spec, context) → validated code
  - create_test_suite(target) → pytest files
  - scaffold_module(name, pattern) → boilerplate
  - generate_docs(code) → docstrings/comments
```

### Worker 4: MODIFY (Modificación Atómica)
```python
role: "Editor de Código Preciso"
goal: "Modificar archivos existentes con precisión quirúrgica"
backstory: "Experto en refactors atómicos y validación"

tasks:
  - atomic_refactor(pattern, replacement, files) → patches
  - apply_patch(file, diff) → validated change
  - rename_symbol(old, new, scope) → LSP-powered
  - extract_function(code_range) → new function
```

## Orquestación por Denis Persona

```python
# Flujo de delegación
async def delegate_task(intent: str, complexity: int) -> CrewResult:
    
    # Denis decide cuántos workers necesita
    if complexity <= 2:
        workers = [Worker4]  # Solo modificación
    elif complexity <= 5:
        workers = [Worker1, Worker4]  # Search + Modify
    elif complexity <= 8:
        workers = [Worker1, Worker2, Worker4]  # Search + Analysis + Modify
    else:
        workers = [Worker1, Worker2, Worker3, Worker4]  # Todos
    
    # CrewAI orquesta en paralelo
    crew = Crew(
        agents=workers,
        tasks=create_tasks(intent),
        process=Process.parallel,  # <-- CLAVE: paralelo
        manager=DenisPersona()     # <-- Denis gestiona
    )
    
    result = await crew.kickoff()
    
    # Todo al grafo
    persist_to_neo4j(result)
    
    return result
```

## Comunicación Grafocéntrica

### Cada worker escribe a Neo4j:
```cypher
// Worker inicia tarea
CREATE (w:WorkerTask {
  id: $task_id,
  worker_type: $worker_type,  // SEARCH|ANALYSIS|CREATE|MODIFY
  status: 'running',
  started_at: datetime(),
  input: $input_json
})

// Worker completa tarea
MATCH (w:WorkerTask {id: $task_id})
SET w.status = 'completed',
    w.output = $output_json,
    w.completed_at = datetime(),
    w.files_touched = $files,
    w.symbols_modified = $symbols

// Link al CP padre
MATCH (w:WorkerTask {id: $task_id})
MATCH (cp:ContextPack {id: $cp_id})
CREATE (cp)-[:HAS_WORKER_TASK]->(w)

// Agregar a Denis Persona knowledge
MATCH (d:Persona {name: 'Denis'})
MATCH (w:WorkerTask {id: $task_id})
CREATE (d)-[:KNOWS_FROM_WORKER]->(w)
```

## Información al Usuario

### Progreso en tiempo real:
```python
class WorkerMonitor:
    """Monitorea workers y actualiza UI"""
    
    async def stream_progress(self, crew_id: str):
        while True:
            # Query Neo4j cada 2 segundos
            tasks = self.query_running_tasks(crew_id)
            
            for task in tasks:
                status = self.format_status(task)
                
                # Mostrar en popup/live
                self.update_zenity_progress(
                    f"Worker {task.worker_type}: {status}"
                )
                
                # Si hay error, notificar inmediatamente
                if task.status == 'error':
                    self.alert_user(task.error_message)
            
            await asyncio.sleep(2)
```

### Formato de estado:
```
🤖 Denis delegando tarea compleja...

Worker SEARCH    [████████░░] 80% - 12 símbolos encontrados
Worker ANALYSIS  [██████░░░░] 60% - Analizando dependencias  
Worker CREATE    [░░░░░░░░░░] 0%  - Esperando análisis...
Worker MODIFY    [░░░░░░░░░░] 0%  - Esperando creación...

[Cancelar] [Ver Detalles] ⏱️ ETA: 45s
```

## Uso por el Agente

### Solicitar workers paralelos:
```python
# El agente solicita a Denis
result = await atlas_parallel_delegation({
    "intent": "refactor_auth_system",
    "parallel_streams": 4,  # Solicitar los 4 workers
    "tasks": {
        "search": {
            "worker": "Worker1",
            "task": "find_all_auth_symbols",
            "priority": 1
        },
        "analysis": {
            "worker": "Worker2", 
            "task": "analyze_auth_dependencies",
            "priority": 2,
            "depends_on": ["search"]  # Espera a search
        },
        "create": {
            "worker": "Worker3",
            "task": "generate_new_auth_module",
            "priority": 3,
            "depends_on": ["analysis"]
        },
        "modify": {
            "worker": "Worker4",
            "task": "refactor_legacy_calls",
            "priority": 4,
            "depends_on": ["create"]
        }
    }
})

# Resultado consolidado
if result.status == "completed":
    files_created = result.workers["create"].output.files
    files_modified = result.workers["modify"].output.files
    symbols_updated = result.workers["search"].output.symbols
```

## Integración Atlas (Archivos)

### Worker4 (Modify) usa Atlas para operaciones atómicas:
```python
class Worker4Modify(Agent):
    """Modificación precisa con Atlas"""
    
    def atomic_refactor(self, files, pattern, replacement):
        # Atlas maneja backup + patch + validate
        result = atlas.atomic_refactor(
            files=files,
            pattern=pattern,
            replacement=replacement,
            validate_with_lsp=True,
            create_backups=True,
            auto_commit=False  # Esperar aprobación CP
        )
        
        # Validar con Control Plane antes de aplicar
        cp = self.generate_mini_cp(result)
        if not self.control_plane.validate(cp):
            raise ValidationError("Control Plane rechazó cambios")
        
        return result
```

## Tools MCP para Workers

```python
# Denis orquesta workers
atlas_parallel_delegation(intent, streams, tasks)
→ {crew_id, workers[], status}

# Monitor de workers
atlas_worker_status(crew_id)
→ {workers[], progress[], eta}

# Cancelar workers
atlas_cancel_workers(crew_id)
→ {cancelled, reason}

# Resultado consolidado
atlas_consolidate_results(crew_id)
→ {files[], symbols[], summary}
```

## Flujo Completo Ejemplo

```
1. Usuario: "Refactoriza todo el sistema de auth"

2. Agente → atlas_decide()
   Denis: "Complejidad 9/10, usar los 4 workers"

3. Agente → atlas_parallel_delegation({
     streams: 4,
     tasks: [search, analysis, create, modify]
   })
   
4. CrewAI inicia 4 workers en paralelo
   - Cada worker escribe progreso a Neo4j cada 2s
   - Denis monitoriza desde el grafo
   
5. Worker1 (Search) completa
   → 15 símbolos de auth encontrados
   
6. Worker2 (Analysis) usa resultados de Worker1
   → Detecta 3 dependencias circulares
   
7. Worker3 (Create) genera nuevo módulo
   → Usa análisis para diseño
   
8. Worker4 (Modify) aplica refactors
   → Usa Atlas para cambios atómicos
   → Control Plane valida cada cambio
   
9. Crew completa → resultado al grafo
   
10. Agente → atlas_consolidate_results()
    → Recibe resumen de 4 workers
    → Presenta a usuario: "15 archivos modificados, 
       3 dependencias resueltas, 1 nuevo módulo creado"
```

## Lenguaje Máquina

Todo en JSON estructurado:
```json
{
  "crew_id": "crew_2026_abc123",
  "orchestrator": "DenisPersona",
  "parallelism": 4,
  "workers": [
    {"type": "SEARCH", "status": "completed", "output": {...}},
    {"type": "ANALYSIS", "status": "completed", "output": {...}},
    {"type": "CREATE", "status": "completed", "output": {...}},
    {"type": "MODIFY", "status": "completed", "output": {...}}
  ],
  "consolidated": {
    "files_touched": 15,
    "symbols_modified": 23,
    "validation_passed": true
  }
}
```

## Reglas de Oro

1. **SIEMPRE** Denis decide cuántos workers (1-4)
2. **SIEMPRE** workers escriben a Neo4j (grafocéntrico)
3. **SIEMPRE** Worker4 (Modify) valida con Control Plane
4. **SIEMPRE** Atlas maneja operaciones de archivos
5. **NUNCA** workers actúan sin aprobación de Denis
6. **SIEMPRE** resultado consolidado al grafo antes de presentar al usuario
