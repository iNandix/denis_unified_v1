# Denis Unified Architecture - TODAS las herramientas integradas

## Principio Inmutable
**TODO se persiste en Neo4j. Nada existe fuera del grafo.**

## Arquitectura Completa Integrada

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE ENTRADA (User)                               │
│  • Chat / CLI / IDE / API                                                    │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 1: RASA NLU + PARLAI (Entendimiento + Templates)                       │
│                                                                              │
│  Rasa NLU (Real, no stub):                                                   │
│    • Intent classification → (:RasaIntent)                                   │
│    • Entity extraction → (:Entity)                                           │
│    • Confidence scoring                                                      │
│                                                                              │
│  ParLAI Templates:                                                           │
│    • (:ParLAITemplate)-[:FOR_INTENT]->(:RasaIntent)                         │
│    • Context enrichment from graph                                           │
│    • Code patterns from (:CodePattern)                                       │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ intent + entities + template
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 2: INDEXER + CHUNKER (Procesamiento de Código)                         │
│                                                                              │
│  Atlas Indexer:                                                              │
│    • Indexa workspace → (:File)-[:HAS_SYMBOL]->(:Symbol)                    │
│    • AST parsing → tree-sitter                                               │
│    • Dependencies → (:File)-[:DEPENDS_ON]->(:File)                          │
│                                                                              │
│  Content Chunker:                                                            │
│    • Chunk files → (:Chunk)                                                  │
│    • Semantic chunks → embeddings                                            │
│    • (:Chunk)-[:PART_OF]->(:File)                                           │
│    • Deduplication → (:Chunk)-[:SIMILAR_TO]->(:Chunk)                       │
│                                                                              │
│  Chunk Classifier:                                                           │
│    • Classifica chunks: code/docs/config/test                               │
│    • (:Chunk {type: 'implementation'})                                       │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ indexed_symbols + chunks
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 3: BÚSQUEDA PRO (Perplexica Fork Local + RAG)                          │
│                                                                              │
│  3 Niveles de Profundidad:                                                   │
│                                                                              │
│  Nivel 1 - Local (Instantáneo):                                              │
│    • (:Symbol) en Neo4j                                                      │
│    • (:File) recientemente modificados                                       │
│    • Working Memory hot files                                                │
│                                                                              │
│  Nivel 2 - Qdrant Vector Store (Semántico):                                  │
│    • Embeddings de chunks                                                    │
│    • Similarity search                                                       │
│    • (:Chunk)-[:SEMANTICALLY_SIMILAR]->(:Chunk)                             │
│                                                                              │
│  Nivel 3 - Perplexica Fork (Web + External):                                 │
│    • Búsqueda en documentación externa                                       │
│    • StackOverflow, GitHub, docs                                             │
│    • Resultados cacheados en (:ExternalKnowledge)                            │
│                                                                              │
│  RAG Context Builder:                                                        │
│    • Recupera contexto relevante de los 3 niveles                           │
│    • Rank y deduplicación                                                    │
│    • Construye prompt enriquecido                                            │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ context_enriched (symbols + chunks + rag)
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 4: CONTROL PLANE (Validación + Seguridad)                              │
│                                                                              │
│  Constitución Level0:                                                        │
│    • (:ConstitutionalRule)-[:BLOCKS]->(:Action)                             │
│    • L0.SAFETY.NO_SECRET_LOGGING                                            │
│    • L0.SAFETY.HUMAN_APPROVAL_FOR_SELF_MOD                                   │
│                                                                              │
│  Approval Engine:                                                            │
│    • (:ProtectedPath)-[:REQUIRES_APPROVAL]->(:File)                         │
│    • (:ContextPack)-[:BLOCKED_BY]->(:ApprovalRule)                           │
│                                                                              │
│  ChangeGuard:                                                                │
│    • Detecta cambios sensibles                                               │
│    • (:Change)-[:VIOLATES]->(:DoNotTouch)                                   │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ validated_context_pack
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 5: DENIS PERSONA (Orquestador Único)                                   │
│                                                                              │
│  Decision Engine:                                                            │
│    • Evalúa complejidad 1-10                                                 │
│    • (:Decision)-[:DECIDED_BY]->(:Persona {name: 'Denis'})                  │
│    • Selecciona modelo                                                       │
│    • Activa workers si complejidad >= 6                                      │
│                                                                              │
│  Model Router:                                                               │
│    • Opencode native (kimi-k2.5-free)                                       │
│    • Groq API (llama-3.3-70b)                                               │
│    • OpenRouter (múltiples modelos)                                         │
│    • Local llama.cpp (2 en nodo1, 4 en nodo2)                               │
│                                                                              │
│  State en Grafo:                                                             │
│    • (:Persona)-[:HAS_MOOD]->(:Mood)                                        │
│    • (:Persona)-[:KNOWS]->(:Symbol)                                         │
│    • (:Persona)-[:PREFERS]->(:Engine)                                       │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ execution_order
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 6: MEMORIA 12 CAPAS (Neuroplastic)                                     │
│                                                                              │
│  Las 12 Capas persistidas en Neo4j:                                          │
│                                                                              │
│  L1_INSTINCTIVE    → (:Memory {layer: 1, ttl: '5s'})                         │
│  L2_SHORT_TERM     → (:Memory {layer: 2, ttl: '60s'})                        │
│  L3_EPISODIC       → (:Memory {layer: 3, type: 'event'})                     │
│  L4_PROCEDURAL     → (:Memory {layer: 4, type: 'macro'})                     │
│  L5_SEMANTIC       → (:Memory {layer: 5, type: 'concept'})                   │
│  L6_RELATIONAL     → (:Memory {layer: 6, type: 'relationship'})              │
│  L7_EMOTIONAL      → (:Memory {layer: 7, type: 'emotion'})                   │
│  L8_IDENTITY       → (:Memory {layer: 8, type: 'identity'})                  │
│  L9_CULTURAL       → (:Memory {layer: 9, type: 'cultural'})                  │
│  L10_ARCHETYPAL    → (:Memory {layer: 10, type: 'archetype'})                │
│  L11_COLLECTIVE    → (:Memory {layer: 11, type: 'collective'})               │
│  L12_COSMIC        → (:Memory {layer: 12, type: 'cosmic'})                   │
│                                                                              │
│  Consolidación:                                                              │
│    • (:Memory)-[:CONSOLIDATES_TO]->(:Memory) (sube de capa)                 │
│    • (:Memory)-[:DECAYS]->(:Forgotten) después de TTL                       │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ memory_context
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 7: WORKERS PARALELOS (Celery + Redis)                                  │
│                                                                              │
│  4 Workers Especializados:                                                   │
│                                                                              │
│  WORKER 1 - SEARCH:                                                          │
│    • Busca en (:Symbol), (:File), (:Chunk)                                   │
│    • Semantic search en Qdrant                                               │
│    • Resultado: (:WorkerTask {type: 'SEARCH'})                               │
│                                                                              │
│  WORKER 2 - ANALYSIS:                                                        │
│    • Analiza dependencias (:File)-[:DEPENDS_ON]                             │
│    • Complejidad ciclomática                                                 │
│    • Issues y sugerencias                                                    │
│    • Resultado: (:WorkerTask {type: 'ANALYSIS'})                             │
│                                                                              │
│  WORKER 3 - CREATE:                                                          │
│    • Genera código nuevo                                                     │
│    • Usa templates de (:CodeTemplate)                                        │
│    • Valida con LSP                                                          │
│    • Resultado: (:WorkerTask {type: 'CREATE'})                               │
│                                                                              │
│  WORKER 4 - MODIFY:                                                          │
│    • Atlas Fork: cambios atómicos                                            │
│    • Backup → Patch → Validate → Apply                                       │
│    • (:Change)-[:APPLIED_TO]->(:File)                                        │
│    • Resultado: (:WorkerTask {type: 'MODIFY'})                               │
│                                                                              │
│  Orquestación:                                                               │
│    • (:Crew)-[:HAS_WORKER]->(:WorkerTask)                                    │
│    • Dependencies entre workers                                              │
│    • Progress tracking cada 2s                                               │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ worker_results
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CAPA 8: EJECUCIÓN + VALIDACIÓN                                              │
│                                                                              │
│  Multi-File Edit (Atlas):                                                    │
│    • Backup automático (:Backup)                                             │
│    • Atomic apply                                                            │
│    • Rollback si falla                                                       │
│                                                                              │
│  LSP Validation:                                                             │
│    • Syntax check                                                            │
│    • Type checking                                                           │
│    • (:Validation)-[:PASSED]->(:Change)                                     │
│                                                                              │
│  Tests:                                                                      │
│    • Run tests afectados                                                     │
│    • (:TestRun)-[:VALIDATES]->(:Change)                                     │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ execution_result
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  GRAFO (Neo4j) - Fuente de Verdad Única                                      │
│                                                                              │
│  Nodos Principales:                                                          │
│    (:Persona), (:Decision), (:ContextPack), (:WorkerTask)                    │
│    (:File), (:Symbol), (:Chunk), (:Memory {layer: 1-12})                     │
│    (:RasaIntent), (:ParLAITemplate), (:CodeTemplate)                         │
│    (:ConstitutionalRule), (:ProtectedPath)                                   │
│    (:Change), (:Backup), (:Validation), (:TestRun)                           │
│                                                                              │
│  Relaciones Clave:                                                           │
│    (:Decision)-[:GENERATES]->(:ContextPack)                                  │
│    (:ContextPack)-[:HAS_WORKER_TASK]->(:WorkerTask)                          │
│    (:WorkerTask)-[:EXECUTED_IN]->(:Session)                                  │
│    (:Persona)-[:KNOWS_FROM_WORKER]->(:WorkerTask)                            │
│    (:File)-[:HAS_SYMBOL]->(:Symbol)                                          │
│    (:File)-[:HAS_CHUNK]->(:Chunk)                                            │
│    (:Memory)-[:CONSOLIDATES_TO]->(:Memory)                                   │
│    (:Change)-[:APPLIED_TO]->(:File)                                          │
│    (:Change)-[:VALIDATED_BY]->(:Validation)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Esquema de Datos Completo

### 1. Indexer + Chunker → Grafo

```cypher
// Indexar archivo
MERGE (f:File {path: $path})
SET f.last_indexed = datetime(),
    f.language = $language,
    f.lines = $lines

// Crear símbolos
UNWIND $symbols as sym
MERGE (s:Symbol {name: sym.name, file: $path})
SET s.kind = sym.kind,
    s.line = sym.line,
    s.signature = sym.signature
MERGE (f)-[:HAS_SYMBOL]->(s)

// Crear chunks
UNWIND $chunks as chunk
CREATE (c:Chunk {
  id: chunk.id,
  content: chunk.content,
  start_line: chunk.start_line,
  end_line: chunk.end_line,
  type: chunk.type  // code/docs/config/test
})
MERGE (f)-[:HAS_CHUNK {index: chunk.index}]->(c)

// Embedding en Qdrant (referencia en grafo)
SET c.qdrant_id = $qdrant_id
```

### 2. Búsqueda Pro 3 Niveles

```cypher
// Nivel 1: Local (Neo4j)
MATCH (f:File)-[:HAS_SYMBOL]->(s:Symbol)
WHERE s.name CONTAINS $query
RETURN f, s LIMIT 10

// Nivel 2: Vector (Qdrant + Neo4j)
// 1. Buscar en Qdrant: query_embedding → chunk_ids
// 2. Traer metadatos de Neo4j:
MATCH (c:Chunk) WHERE c.qdrant_id IN $chunk_ids
MATCH (c)-[:PART_OF]->(f:File)
RETURN c, f

// Nivel 3: External (Perplexica)
// Cachear resultados en grafo:
MERGE (ek:ExternalKnowledge {query: $query})
SET ek.result = $result,
    ek.source = $source,
    ek.timestamp = datetime()
```

### 3. Memoria 12 Capas

```cypher
// Insertar en L1 (instintiva)
CREATE (m:Memory {
  layer: 1,
  content: $content,
  ttl_seconds: 5,
  created_at: datetime()
})

// Consolidación: L1 → L2 después de threshold
MATCH (m:Memory {layer: 1})
WHERE datetime() > m.created_at + duration('PT1M')
SET m.layer = 2,
    m.ttl_seconds = 60

// Continuar hasta L12...
```

### 4. Workers Paralelos

```cypher
// Crear Crew
CREATE (crew:Crew {
  id: $crew_id,
  started_at: datetime(),
  complexity: $complexity
})

// Workers
UNWIND $workers as worker
CREATE (wt:WorkerTask {
  id: worker.id,
  type: worker.type,  // SEARCH|ANALYSIS|CREATE|MODIFY
  status: 'pending',
  priority: worker.priority
})
CREATE (crew)-[:HAS_WORKER]->(wt)

// Dependencias
MATCH (wt1:WorkerTask {id: $worker_id})
MATCH (wt2:WorkerTask {id: $depends_on})
CREATE (wt2)-[:MUST_COMPLETE_BEFORE]->(wt1)

// Resultado
MATCH (wt:WorkerTask {id: $worker_id})
SET wt.status = 'completed',
    wt.output = $output,
    wt.completed_at = datetime()
```

## MCP Tools Unificados

```python
# Layer 1: NLU + Templates
rasa_parse(text: str) -> RasaIntent
parlai_get_template(intent: str) -> ParLAITemplate

# Layer 2: Indexing
indexer_index_workspace(paths: List[str]) -> IndexResult
chunker_chunk_file(file_path: str) -> List[Chunk]
chunk_classifier_classify(chunk: Chunk) -> ChunkType

# Layer 3: Search
search_pro_level1_local(query: str) -> List[Symbol]
search_pro_level2_vector(query: str, embedding: List[float]) -> List[Chunk]
search_pro_level3_external(query: str) -> ExternalKnowledge
rag_build_context(query: str, depth: int) -> Context

# Layer 4: Control Plane
controlplane_validate_cp(cp: ContextPack) -> ValidationResult
approval_check_do_not_touch(files: List[str]) -> List[ProtectedPath]

# Layer 5: Denis
denis_decide_strategy(intent: str, complexity: int) -> ExecutionOrder
denis_select_model(strategy: str, quotas: Dict) -> ModelSelection

# Layer 6: Memory
memory_store_layer(content: str, layer: int) -> MemoryId
memory_retrieve_context(query: str, layers: List[int]) -> Context
memory_consolidate() -> ConsolidationResult

# Layer 7: Workers
workers_execute_parallel(order: ExecutionOrder) -> CrewResult
workers_get_progress(crew_id: str) -> WorkerProgress
workers_cancel(crew_id: str) -> bool

# Layer 8: Execution
atlas_multi_file_edit(files: List[str], patches: Dict) -> EditResult
lsp_validate_changes(files: List[str]) -> ValidationResult
tests_run_affected(files: List[str]) -> TestResult
```

## Persistencia Garantizada

**Todo cambio, decisión, ejecución y resultado se persiste en Neo4j.**

Nada opera en memoria sin reflejarse en el grafo. Esto incluye:
- ✅ Intents detectados por Rasa
- ✅ Templates seleccionados por ParLAI
- ✅ Símbolos indexados por Atlas
- ✅ Chunks creados y clasificados
- ✅ Búsquedas realizadas (3 niveles)
- ✅ Decisiones de Denis
- ✅ Estados de memoria (12 capas)
- ✅ Tareas de Workers
- ✅ Cambios aplicados
- ✅ Validaciones y tests

## Tests de Integración

```python
def test_full_stack_graph_centric():
    """Test: Todo el stack opera sobre el grafo."""
    
    # 1. Usuario hace request
    result = denis_unified.process("Implementa auth JWT")
    
    # 2. Verificar que Rasa persistió en grafo
    rasa_intent = query_neo4j("MATCH (r:RasaIntent) RETURN r LIMIT 1")
    assert rasa_intent is not None
    
    # 3. Verificar que se indexaron símbolos
    symbols = query_neo4j("MATCH (s:Symbol) RETURN count(s)")
    assert symbols > 0
    
    # 4. Verificar chunks creados
    chunks = query_neo4j("MATCH (c:Chunk) RETURN count(c)")
    assert chunks > 0
    
    # 5. Verificar decisión de Denis
    decision = query_neo4j("MATCH (d:Decision) RETURN d LIMIT 1")
    assert decision['complexity'] == 8
    
    # 6. Verificar workers ejecutados
    workers = query_neo4j("MATCH (wt:WorkerTask) RETURN count(wt)")
    assert workers == 4
    
    # 7. Verificar memoria persistida
    memories = query_neo4j("MATCH (m:Memory) RETURN count(m)")
    assert memories > 0
    
    # 8. Verificar cambios aplicados
    changes = query_neo4j("MATCH (ch:Change) RETURN count(ch)")
    assert changes > 0
    
    print("✅ Todo el stack es grafocéntrico")
```

## Contrato de Persistencia

**Regla de Oro:** Si no está en Neo4j, no existe.

Antes de cualquier operación: `MERGE` en grafo.
Durante la operación: `SET` propiedades y relaciones.
Después de la operación: Validar que existe en grafo.

Nada de:
- ❌ Variables en memoria sin persistir
- ❌ Stubs que no escriben al grafo
- ❌ Placeholders temporales
- ❌ Mock data

Solo:
- ✅ Todo en Neo4j
- ✅ Relaciones explícitas
- ✅ Timestamps obligatorios
- ✅ Traza completa en grafo
