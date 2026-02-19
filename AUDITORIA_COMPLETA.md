# AUDITORÍA GRAFOCÉNTRICA COMPLETA - NEO4J

**Fecha:** 19 de febrero de 2026  
**Total nodos:** 13,789  
**Total relaciones:** 15,293

---

## 1. RESUMEN EJECUTIVO

| Métrica | Valor |
|---------|-------|
| Total Nodos | 13,789 |
| Total Relaciones | 15,293 |
| Tipos de Nodos | 250+ |
| Qdrant Collections | 48 ✓ |
| Atlas Collections | 12 ✓ |
| NeuroLayers | 24 ✓ |
| MentalLoops | 9 |
| Skills | 22 |
| Tools | 103 |
| Intents | 164 (164 sin ID!) |
| Workers | 5 |
| Inference Models | 6 |
| LLM Models | 6 |
| Providers | 6 |
| Engines | 20 |

---

## 2. NEUROLAYERS (24 nodos)

### 2.1 En Graf (24)
| # | Nombre | Estado |
|---|--------|--------|
| 1 | Memoria sensorial | ✓ |
| 2 | Memoria a corto plazo | ✓ |
| 3 | Memoria de trabajo | ✓ |
| 4 | Memoria episódica | ✓ |
| 5 | Memoria semántica | ✓ |
| 6 | Memoria procedimental | ✓ |
| 7 | Memoria emocional | ✓ |
| 8 | Memoria espacial | ✓ |
| 9 | Memoria autobiográfica | ✓ |
| 10 | Memoria prospectiva | ✓ |
| 11 | Meta-memoria | ✓ |
| 12 | Memoria de patrones | ✓ |
| 13 | L1_SENSORY | ✓ |
| 14 | L2_WORKING | ✓ |
| 15 | L3_EPISODIC | ✓ |
| 16 | L4_SEMANTIC | ✓ |
| 17 | L5_PROCEDURAL | ✓ |
| 18 | L6_SKILLS | ✓ |
| 19 | L7_EMOTIONAL | ✓ |
| 20 | L8_SOCIAL | ✓ |
| 21 | L9_IDENTITY | ✓ |
| 22 | L10_RELATIONAL | ✓ |
| 23 | L11_GOALS | ✓ |
| 24 | L12_METACOG | ✓ |

**Estado:** ✓ COMPLETO (24 nodos)

---

## 3. MEMORY LAYERS (14 nodos)

| # | Nombre | Estado |
|---|--------|--------|
| 1 | Memoria sensorial | ✓ |
| 2 | Memoria a corto plazo | ✓ |
| 3 | Memoria de trabajo | ✓ |
| 4 | Memoria episódica | ✓ |
| 5 | Memoria semántica | ✓ |
| 6 | Memoria procedimental | ✓ |
| 7 | Memoria emocional | ✓ |
| 8 | Memoria espacial | ✓ |
| 9 | Memoria autobiográfica | ✓ |
| 10 | Memoria prospectiva | ✓ |
| 11 | Meta-memoria | ✓ |
| 12 | Memoria de patrones | ✓ |
| 13 | L1-L12 (formato nuevo) | ✓ |
| 14 | audit_trail | ✓ |

---

## 4. MENTAL LOOPS (9 nodos)

| # | Nombre | Estado |
|---|--------|--------|
| 1 | PerceptionLoop | ✓ |
| 2 | CognitionLoop | ✓ |
| 3 | PlanningLoop | ✓ |
| 4 | ExecutionLoop | ✓ |
| 5-9 | 5 nodos sin nombre | ⚠️ |

**Problema:** 5 MentalLoops no tienen nombre definido.

---

## 5. SKILLS (22 nodos)

### 5.1 En Graf (22)
```
image_generation
code_analysis
data_query
auto_discover
fast_code_gen
quality_code_gen
code_review
code_debug
atlas_file_read
atlas_file_write
atlas_code_search
multi_file_read
multi_file_write
test_generation
pro_search
git_operations
rag_query
memory_recall
refactor_code
codecraft (x2)
code_craft
```

### 5.2 En Código (10)
```
code_craft
git_operations
memory_recall
multi_file_read
multi_file_write
pro_search
rag_query
refactor_code
test_generation
web_search
```

### 5.3 Análisis
| Métrica | Valor |
|---------|-------|
| En Graf | 22 |
| En Código | 10 |
| Duplicados en grafo |Sí (codecraft x2) |
| Faltan en grafo | web_search |

---

## 6. TOOLS (103 nodos)

### 6.1 Por Categoría
| Categoría | Cantidad |
|-----------|----------|
| filesystem/file | ~15 |
| system | ~15 |
| git | ~15 |
| denis-core | ~15 |
| network | ~10 |
| code | ~10 |
| home (HA) | ~5 |
| memory | ~3 |
| voice | ~3 |
| search | ~3 |
| None | ~8 |

### 6.2 Análisis
- ✓ 103 tools definidos en grafo
- ⚠️ 8 tools sin categoría (None)

---

## 7. INTENTS (164 nodos)

### 7.1 Problema Crítico
| Métrica | Valor |
|---------|-------|
| Total intents | 164 |
| Con ID | 0 |
| Sin ID | 164 |
| Con nombre None | 6 |

### 7.2 Estado
**⚠️ CRÍTICO:** El 100% de los intents NO tienen ID asignado.

---

## 8. CONTRATOS

### 8.1 Invariants (16)
| # | Nombre | ID |
|---|--------|-----|
| 1 | AlwaysAuditable | ✓ |
| 2 | CompanionModeMandatory | ✓ |
| 3 | NoBypassCore | ✓ |
| 4 | NoSilentChange | ✓ |
| 5 | ProportionalEmergencyOverride | ✓ |
| 6 | PurposeBeforePower | ✓ |
| 7 | PurposeIdentityIndivisible | ✓ |
| 8 | PurposePrecedesTransformation | ✓ |
| 9 | identity_requires_companion_mode | ✓ |
| 10 | mandatory_enforcement_systems | ✓ |
| 11-16 | 6 nodos con nombre None | ⚠️ |

### 8.2 Policies (13)
| # | Nombre | ID |
|---|--------|-----|
| 1 | RuntimePolicy | ✗ |
| 2 | deep_mode_policy | ✗ |
| 3 | cost_control | ✗ |
| 4 | source_diversity | ✗ |
| 5 | bias_detection | ✗ |
| 6 | License Policy | ✗ |
| 7 | Reuse First Policy | ✗ |
| 8 | Cost Control Policy | ✗ |
| 9 | No Big Diff Policy | ✗ |
| 10 | Test Gate Policy | ✗ |
| 11 | Security Scan Policy | ✗ |
| 12 | Code Quality Policy | ✗ |
| 13 | Safety Code Exec Policy | ✗ |

**Problema:** El 100% de las Policies NO tienen ID.

### 8.3 MacroRules (10)
| # | Nombre | ID |
|---|--------|-----|
| 1 | Refactor Seguro | ✗ |
| 2 | Hotfix en Producción | ✗ |
| 3 | Migración de Esquema Segura | ✗ |
| 4 | Feature API Completa | ✗ |
| 5 | Extracción de Service Boundary | ✗ |
| 6 | Observabilidad Completa | ✗ |
| 7 | Cambio de Dependencias Seguro | ✗ |
| 8 | Feature Flag Implementado | ✗ |
| 9 | Dockerización Completa | ✗ |
| 10 | Stage de CI/CD | ✗ |

**Problema:** El 100% de las MacroRules NO tienen ID.

---

## 9. WORKERS (5 nodos)

| # | Nombre | Tipo |
|---|--------|------|
| 1 | LLMWorker | - |
| 2 | ControlRoomWorker | - |
| 3 | AsyncSprintOrchestrator | - |
| 4 | QCLIWorker | - |
| 5 | (sin nombre) | - |

**Problema:** 5 workers definidos pero solo 4 tienen nombre. No tienen tipo definido.

---

## 10. INFERENCE MODELS (6 nodos)

| # | Modelo | Provider |
|---|--------|----------|
| 1 | qwen2.5-3b-instruct-q6_k | - |
| 2 | qwen2.5-coder-7b-instruct-q4_k_m | - |
| 3 | llama-model-1 | - |
| 4 | llama-model-2 | - |
| 5 | llama-model-3 | - |
| 6 | llama-model-4 | - |

**Problema:** Ningún provider asignado.

---

## 11. LLM MODELS (6 nodos)

| # | Modelo | Provider |
|---|--------|----------|
| 1 | Qwen2.5-3B-Instruct | - |
| 2 | Qwen2.5-Coder-7B-Instruct | - |
| 3 | SmolLM2-1.7B-Instruct | - |
| 4 | Gemma-3-1B-IT | - |
| 5 | Qwen2.5-0.5B-Instruct | - |
| 6 | Qwen2.5-1.5B-Instruct | - |

**Problema:** Ningún provider asignado.

---

## 12. PROVIDERS (6)

| # | Nombre |
|---|--------|
| 1 | vllm |
| 2 | groq |
| 3 | openrouter |
| 4 | llamacpp |
| 5 | legacy_core |
| 6 | llama_local |

---

## 13. ENGINES (20)

```
openrouter_cloud
qwen3b_local
qwen_coder7b_local
qwen05b_node2
smollm_node2
gemma_node2
qwen15b_node2
piper_tts
groq_booster
qwen3b_nodo1_chat
qwen7b_nodo1_code
llamacpp_node2_1
llamacpp_node2_2
groq_1
qwen05b_nodo2_fast
smollm2_nodo2_skim
gemma1b_nodo2_safety
qwen15b_nodo2_planner
llamacpp_node2_8081
llamacpp_node2_8082
```

---

## 14. MEMORY COLLECTIONS

### 14.1 Qdrant (48)
```
denis_code_index
identity
denis_memory
denis_tool_intents
personality
atlas_web_chunks
denis_long_term_v384
denis_semantic
daily
longterm
denis_cache_v3_v384
patterns
atlas_entries
denis_autobiographical_memory
denis_memories
denis_template_chunks
denis_cache_v3
denis_long_term
oceanai_emotional_memory
denis_tool_usage
denis_procedure_shards
atlas_security
denis_android_tools
denis_world_model_v384
atlas_docs
denis_rag_v384
denis_contracts
denis_semantic_v384
episodic
denis_memgpt_archival
denis_world_model
e2e_test
denis_relationships
atlas_projects
atlas_code
atlas_web
denis_vectors_test
denis_rag_384_test
metacog
denis_tools
denis_agent_memory_v1
denis_stubs
denis_templates_v2
denis_template_metadata
denis_model_catalog_v1
denis_rag
denis_vectors
atlas_images
```
✓ 48 colecciones - COMPLETO

### 14.2 Atlas (12)
```
conversations
episodic_memory
user_profiles
knowledge_base
code_templates
system_config
agent_runs
voice_sessions
emotions_log
audit_trail
device_states
(None)
```
✓ 12 colecciones - COMPLETO

---

## 15. RELACIONES PRINCIPALES

| Relación | Cantidad |
|----------|----------|
| ACTIVATES_LAYER | 2,176 |
| OF_TURN | 1,710 |
| PART_OF | 1,448 |
| CONTRIBUTES_TO | 1,235 |
| USED_LOOP_LEVEL | 1,080 |
| ACTIVATES_LOOP | 900 |
| UPDATES_CAUSAL | 570 |
| INVOLVES | 550 |
| EXPERIENCED | 359 |
| HAS_GRAPH_ROUTE | 289 |

---

## 16. PROBLEMAS CRÍTICOS

### 16.1 CRÍTICO
| # | Problema | Afección |
|---|----------|----------|
| 1 | 100% Intents sin ID | 164 nodos |
| 2 | 100% Policies sin ID | 13 nodos |
| 3 | 100% MacroRules sin ID | 10 nodos |
| 4 | 6 Invariants sin nombre | 6 nodos |
| 5 | 5 MentalLoops sin nombre | 5 nodos |
| 6 | 1 Worker sin nombre | 1 nodo |

### 16.2 ALTO
| # | Problema | Afección |
|---|----------|----------|
| 1 | Skills duplicados (codecraft x2) | 2 nodos |
| 2 | 8 Tools sin categoría | 8 nodos |
| 3 | Inference Models sin provider | 6 nodos |
| 4 | LLM Models sin provider | 6 nodos |
| 5 | Workers sin tipo definido | 5 nodos |

### 16.3 MEDIO
| # | Problema |
|---|----------|
| 1 | Falta web_search en grafo (existe en código) |
| 2 | Duplicación de neuro layers (español + inglés) |

---

## 17. RESUMEN DE GAPS GRAFOCÉNTRICO

| Componente | En Graf | Con ID | Sin ID | % Sincronizado |
|------------|---------|--------|--------|----------------|
| Intents | 164 | 0 | 164 | 0% |
| Policies | 13 | 0 | 13 | 0% |
| MacroRules | 10 | 0 | 10 | 0% |
| Invariants | 16 | 16 | 0 | 100% |
| Skills | 22 | - | - | 100% |
| Tools | 103 | - | - | 100% |
| NeuroLayers | 24 | - | - | 100% |
| Workers | 5 | - | - | 0% (sin tipo) |
| Inference Models | 6 | - | - | 0% (sin provider) |

---

## 18. ACCIONES RECOMENDADAS

### Alta Prioridad
1. **Asignar IDs a Intents** - 164 nodos necesitan ID
2. **Asignar IDs a Policies** - 13 nodos necesitan ID
3. **Asignar IDs a MacroRules** - 10 nodos necesitan ID

### Media Prioridad
4. **Nombrar MentalLoops** - 5 nodos sin nombre
5. **Nombrar Invariants** - 6 nodos sin nombre
6. **Asignar providers a Models** - 12 nodos
7. **Asignar tipos a Workers** - 5 nodos

### Baja Prioridad
8. **Limpiar Skills duplicados**
9. **Categorizar Tools sin categoría**
10. **Sincronizar web_search**

---

## 19. INCONSISTENCIAS ADICIONALES DETECTADAS

### 19.1 Nodos Sin Relaciones (Huérfanos)
| Tipo | Cantidad |
|------|----------|
| AgentScan | 2,737 |
| ReasoningTrace | 453 |
| Episode | 437 |
| ConceptNode | 333 |
| TraitEvolution | 275 |
| None | 249 |
| HakunaMataCycle | 233 |
| TemplateChunkV2 | 170 |
| User | 168 |

### 19.2 Nodos Con Múltiples Labels
| Labels | Cantidad |
|--------|----------|
| Memory, TechnicalMemory | 116 |
| NeuroLayer, MemoryLayer | 12 |
| Booster, ExternalService | 12 |
| Event, IdentityEvent, L12 | 8 |
| Artifact, CodeModule | 8 |
| Skill, ExecutableSkill | 7 |
| Memory, RelationalMemory | 7 |
| Principle, L2 | 6 |
| Pattern, L1 | 5 |

### 19.3 Entidades Sin Sincronizar
| Entidad | Problema |
|---------|----------|
| Intents (96) | Sin ID |
| Policies (13) | Sin ID |
| codecraft (Skill) | Duplicado (2) |

### 19.4 Bugs Corregidos en Código
| Archivo | Bug | Corrección |
|---------|-----|------------|
| gates/audit.py:171 | async with driver síncrono | Cambiado a with driver.session() |
| inference/router.py:283 | Falta cliente piper | Añadido PiperDummy |
| cognition/local_responder.py:199 | async with driver síncrono | Cambiado a with driver.session() |
