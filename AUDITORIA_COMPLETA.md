# AUDITORÍA COMPLETA: CÓDIGO vs GRAF

## 1. MEMORY SYSTEMS

| Sistema | Código/YAML | En Graf | Estado |
|--------|-------------|---------|--------|
| **Qdrant Collections** | ? | 48 | ✓ Existe |
| **Atlas Collections** | 12 en código | 12 | ✓ Existe |
| **ChromaDB** | ? | 0 | FALTA? |
| **Mem0** | ? | 0 | FALTA? |

### Qdrant Collections (48):
- denis_code_index, identity, denis_memory, denis_tool_intents, personality
- atlas_web_chunks, denis_long_term_v384, denis_semantic, daily, longterm
- denis_cache_v3_v384, patterns, atlas_entries, denis_autobiographical_memory
- denis_memories, denis_template_chunks, denis_cache_v3, denis_long_term
- oceanai_emotional_memory, denis_tool_usage, denis_procedure_shards
- atlas_security, denis_android_tools, denis_world_model_v384, atlas_docs
- denis_rag_v384, denis_contracts, denis_semantic_v384, episodic
- denis_memgpt_archival, denis_world_model, e2e_test, denis_relationships
- atlas_projects, atlas_code, atlas_web, denis_vectors_test, denis_rag_384_test
- metacog, denis_tools, denis_agent_memory_v1, denis_stubs
- denis_templates_v2, denis_template_metadata, denis_model_catalog_v1
- denis_rag, denis_vectors, atlas_images

### Atlas Collections (12):
- conversations, episodic_memory, user_profiles, knowledge_base
- code_templates, system_config, agent_runs, voice_sessions
- emotions_log, audit_trail, device_states

## 2. NEUROLAYERS (12 CAPAS)

| Capa | Código/YAML | En Graf | Estado |
|------|-------------|---------|--------|
| L1_SENSORY | ✓ | ✓ | OK |
| L2_SHORT_TERM / WORKING | ✓ | ✓ | OK |
| L3_EPISODIC | ✓ | ✓ | OK |
| L4_SEMANTIC | ✓ | ✓ | OK |
| L5_PROCEDURAL | ✓ | ✓ | OK |
| L6_SKILLS | ✓ | ✓ | OK |
| L7_EMOTIONAL | ✓ | ✓ | OK |
| L8_SOCIAL | ✓ | ✓ | OK |
| L9_IDENTITY | ✓ | ✓ | OK |
| L10_RELATIONAL | ✓ | ✓ | OK |
| L11_GOALS | ✓ | ✓ | OK |
| L12_METACOG | ✓ | ✓ | OK |

### NeuroLayers en Graf (24 nodos - 2 naming schemes):
- sensory, short_term, working, episodic, semantic, procedural, emotional
- spatial, autobiographical, prospective, meta_memory, pattern
- L1_SENSORY a L12_METACOG

## 3. MENTAL LOOPS

| Loop | Código/YAML | En Graf | Estado |
|------|-------------|---------|--------|
| L1_REFLECTION | ✓ | ? | Verificar |
| L2_META | ✓ | ? | Verificar |
| L3_PATTERN | ✓ | ? | Verificar |
| L4_EXPANSIVE | ✓ | ? | Verificar |

### MentalLoops en Graf (9):
- PerceptionLoop, CognitionLoop, PlanningLoop, ExecutionLoop
- loop:reflection, loop:pattern_recognition, loop:expansive_consciousness, loop:meta_reflection

## 4. CONTRATOS (FUENTE DE VERDAD)

| Tipo | registry.yaml | En Graf | Estado |
|------|---------------|---------|--------|
| L0 (Constitution) | 4 | ✓ | OK |
| L1 (Topology) | 4 | ? | Verificar |
| L2 (Adaptive) | 4 | ? | Verificar |
| L3 Inference | 4+ | ? | Verificar |
| L3 Voice | 3+ | ? | Verificar |
| L3 Memory | 20+ | ? | Verificar |
| L3 Metacognitive | 3+ | ? | Verificar |
| L3 Sprint | 9+ | ? | Verificar |
| L3 Gates | 4+ | ? | Verificar |

### Contratos en Graf:
- Invariant: 16
- Policy: 12 (sin IDs)
- MacroRule: 10

## 5. SKILLS (10)

| Skill | Código | En Graf | Estado |
|-------|--------|---------|--------|
| code_craft | ✓ | ✓ | OK |
| git_operations | ✓ | ✓ | OK |
| memory_recall | ✓ | ✓ | OK |
| multi_file_read | ✓ | ✓ | OK |
| multi_file_write | ✓ | ✓ | OK |
| pro_search | ✓ | ✓ | OK |
| rag_query | ✓ | ✓ | OK |
| refactor_code | ✓ | ✓ | OK |
| test_generation | ✓ | ✓ | OK |
| web_search | ✓ | ✓ | OK |

## 6. TOOLS

| Tipo | Código | En Graf | Estado |
|------|--------|---------|--------|
| Core Tools | 30+ | 103 | MÁSGRAF |

### Tools en Graf (103):
- filesystem (read_file, write_file, edit_file, list_directory)
- network (Tailscale, Port, SSH, Nmap)
- git (Git Commit)
- system (Restart, Reboot, Shell)
- denis-core (bash_execute, python_execute, neo4j_query, ha_control)

## 7. INTENTS

| Tipo | Código | En Graf | Estado |
|------|--------|---------|--------|
| code.* | ~20 | 164 total | MÁSGRAF |
| system.* | ~20 | 68 únicos | Parcial |

### Intents en Graf (164):
- code.write, code.debug, code.review, code.explain, code.test, code.optimize, code.complete, code.translate, code.document, code.refactor
- system.status, system.restart, system.deploy, system.logs, system.config, system.install, system.ssh, system.process, system.monitor
- 96 sin ID

## 8. WORKERS

| Worker | Código | En Graf | Estado |
|--------|--------|---------|--------|
| LLMWorker | ✓ | 1 | FALTA DEFINICIÓN |
| ControlRoomWorker | ✓ | 1 | FALTA DEFINICIÓN |
| AsyncSprintOrchestrator | ✓ | 1 | FALTA DEFINICIÓN |
| QCLI Worker | ✓ | ? | Verificar |

## 9. INFERENCE MODELS

| Model | Código | En Graf | Estado |
|-------|--------|---------|--------|
| Groq | ✓ | 0 | FALTA |
| OpenRouter | ✓ | 0 | FALTA |
| llamaLocal | ✓ | 0 | FALTA |
| Qwen | ✓ | 2 | OK |
| Llama | ✓ | 4 | OK |

## 10. PERSONA & CONSTITUTION

| Nodo | Estado |
|------|--------|
| Persona | ✓ Unificado (1 nodo con todas las propiedades) |
| Constitution | ✓ Unificado (1 nodo con core_principles + non_negotiable_invariants) |
| Identity | ✓ |

## 11. RESUMEN DE GAPS

### CRÍTICO:
- ❌ Workers no definidos (solo 1 nodo Worker genérico)
- ❌ Inference Models no sincronizados (0 Groq/OpenRouter/llamaLocal en grafo)
- ❌ 96 Intents sin ID

### ALTO:
- ⚠️ Contracts/Policy sin IDs en grafo
- ⚠️ MentalLoops incompletos

### VERIFICAR:
- ChromaDB en grafo?
- Mem0 en grafo?
- L1-L4 Mental Loops exactamente en grafo?

## 12. ARCHIVOS TOTALES

- Python en denis_unified_v1: 15,051 archivos
- Contratos YAML: 923 líneas (13 archivos)
- Skills: 10
- Workers: 4+ tipos
- Nodos en Graf: ~13,000+
