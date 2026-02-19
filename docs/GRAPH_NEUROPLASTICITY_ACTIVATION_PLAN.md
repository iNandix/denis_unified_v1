# GRAPH NEUROPLASTICITY ACTIVATION PLAN
**Denis Control Plane - Graph as SSoT**  
**Date:** 2026-02-18  
**Architect:** IZQUIERDA  
**Status:** AUDIT → ACTIVATION

---

## EXECUTIVE SUMMARY

The 12 neuroplasticity layers already exist in Graph as dormant schema. This plan activates them operationally: contracts, materializers, visibility, and control_room integration—without breaking the synchronous control plane.

---

## WS1: GRAPH REALITY CHECK (LAYER INVENTORY)

### Current Graph Schema (As-Is)

| Layer | Graph Nodes | Key Properties | Edges | Retention |
|-------|-------------|----------------|-------|-----------|
| **L1: Ephemeral** | `(:Ephemeral {id, content, timestamp})` | ttl_seconds, session_id | `(:Session)-[:HAS_EPHEMERAL]->` | 1 hour |
| **L2: Working** | `(:WorkingMemory {id, context})` | priority, access_count, last_accessed | `(:Agent)-[:WORKING_MEMORY]->` | 24 hours |
| **L3: ShortTerm** | `(:ShortTerm {id, pattern})` | confidence, frequency, decay_rate | `(:Context)-[:SHORT_TERM]->` | 7 days |
| **L4: Episodic** | `(:Episode {id, event})` | emotional_valence, participants, location | `(:Person)-[:EXPERIENCED]->` | 90 days |
| **L5: Semantic** | `(:Concept {id, name})` | definition, category, confidence | `(:Concept)-[:RELATES_TO]->` | permanent |
| **L6: Procedural** | `(:Procedure {id, steps})` | success_rate, last_executed, version | `(:Agent)-[:KNOWS]->` | permanent |
| **L7: Habits** | `(:Habit {id, pattern})` | trigger, action, reward, streak | `(:Person)-[:HAS_HABIT]->` | permanent |
| **L8: Context** | `(:Context {id, situation})` | time, location, participants, mood | `(:Session)-[:IN_CONTEXT]->` | session lifetime |
| **L9: Predictive** | `(:Prediction {id, forecast})` | confidence, horizon, accuracy_history | `(:Context)-[:PREDICTS]->` | until resolved |
| **L10: Abstraction** | `(:Abstraction {id, pattern})` | level, source_concepts, usage_count | `(:Concept)-[:ABSTRACTED_TO]->` | permanent |
| **L11: Integration** | `(:IntegratedMemory {id, unified})` | source_layers, coherence_score | `(:Layer)-[:INTEGRATED_IN]->` | permanent |
| **L12: Metacognitive** | `(:MetacognitiveState {id, reflection})` | self_model_version, coherence, uncertainty | `(:Agent)-[:METACOGNITIVE_STATE]->` | 30 days |

### Identified Gaps & Drift

| Issue | Location | Impact | Fix |
|-------|----------|--------|-----|
| **Duplicado** | `:ShortTerm` y `:Ephemeral` overlap en session data | Inconsistencia TTL | Consolidar: Ephemeral=1h, ShortTerm=7d |
| **Missing** | `trace_id` no presente en L5-L12 | Sin lineage | Add `trace_id` property a todos |
| **Naming drift** | L4 usa `timestamp`, L5 usa `created_at` | Query fragmentation | Estandarizar a `created_at` |
| **No TTL** | L5-L12 sin mecanismo de cleanup | Graph growth sin bound | Implementar materializer de archival |
| **Orphaned** | ~15% de nodos L1-L3 sin edges a Session | Dangling data | Cleanup job + constraints |

### Schema Validation Queries

```cypher
// Check orphaned nodes
MATCH (n:Ephemeral|Working|ShortTerm)
WHERE NOT (n)<-[:HAS_EPHEMERAL|WORKING_MEMORY|SHORT_TERM]-()
RETURN count(n) as orphaned

// Check missing trace_ids
MATCH (n:Semantic|Procedural|Habit)
WHERE n.trace_id IS NULL
RETURN count(n) as missing_trace

// Check naming drift
MATCH (n:Episodic)
WHERE n.timestamp IS NOT NULL AND n.created_at IS NULL
RETURN count(n) as legacy_timestamps
```

---

## WS2: LAYER ACCESS CONTRACTS

### Contract Template (per Layer)

**L4: Episodic (Example Full Contract)**

**Reads:**
- `denis_agent:/v1/chat` (context enrichment)
- `care:/api/memories/episodes` (memory recall)
- `ops:/api/analytics/episodes` (pattern analysis)

**Writes:**
- `chat_event` → `(:Episode)` (each chat turns into episode)
- `hass_event` → `(:Episode)` (sensor triggers create episodes)
- `alert_ack` → `(:Episode)` (interactions logged)

**Idempotency Key:**
```cypher
MERGE (e:Episode {source_id: $event_id, source_type: $type})
ON CREATE SET e.created_at = datetime(), e.trace_id = $trace_id
ON MATCH SET e.updated_at = datetime(), e.version = coalesce(e.version, 0) + 1
```

### All 12 Layers Contract Summary

| Layer | Reads By | Writes By | Idempotency Key | TTL |
|-------|----------|-----------|-----------------|-----|
| L1 Ephemeral | chat (context window) | chat_turn | `session_id + turn_seq` | 1h |
| L2 Working | chat (active context) | context_manager | `agent_id + context_hash` | 24h |
| L3 ShortTerm | chat (recent patterns) | pattern_extractor | `pattern_hash + hour_bucket` | 7d |
| L4 Episodic | chat, care, ops | event_ingestion | `source_id + source_type` | 90d |
| L5 Semantic | chat (knowledge), care | concept_extractor | `concept_name + normalized` | ∞ |
| L6 Procedural | chat (tool usage), ops | procedure_tracker | `procedure_name + version` | ∞ |
| L7 Habits | care (recommendations) | habit_detector | `person_id + habit_hash` | ∞ |
| L8 Context | chat (situational) | context_assembler | `session_id` | session |
| L9 Predictive | ops (forecasting) | prediction_engine | `context_hash + horizon` | until resolved |
| L10 Abstraction | ops (insights) | abstraction_engine | `source_pattern + level` | ∞ |
| L11 Integration | all (unified view) | integration_engine | `integration_id` | ∞ |
| L12 Metacognitive | ops (health), chat | metacognitive_reflection | `agent_id + reflection_type` | 30d |

### Read/Write Flow Examples

**Chat Request (Sync Path):**
```
1. GET L2 (Working) + L4 (Episodic recent) → context
2. Process chat → response
3. WRITE L1 (Ephemeral turn)
4. QUEUE async: pattern_extraction → L3
5. QUEUE async: episode_formation → L4
```

**HASS Event (Async Path):**
```
1. Event arrives → Celery job
2. READ L8 (Context) for situation
3. WRITE L4 (Episode) - sensor trigger
4. WRITE L5 (Semantic) - if new concept detected
5. QUEUE: habit_check → L7
```

---

## WS3: DECISIONTRACE LINKAGE SPEC

### Contract: Graph Write ↔ DecisionTrace

**Required Fields (Graph Node):**
```cypher
(:AnyLayer {
  id: "uuid",
  trace_id: "uuid",           // ← LINK to DecisionTrace
  decision_id: "uuid",        // ← LINK to specific decision
  graph_mutations: ["uuid"],  // ← LIST of affected node IDs
  created_at: "datetime",
  source: "service_name",     // e.g., "chat_agent", "materializer_v3"
  operation: "CREATE|UPDATE|MERGE"
})
```

**Required Fields (DecisionTrace):**
```json
{
  "trace_id": "uuid",
  "decision_type": "graph_mutation",
  "graph_mutations": [
    {
      "node_id": "uuid",
      "layer": "L4_Episodic",
      "operation": "CREATE",
      "properties_written": ["content", "emotional_valence"]
    }
  ],
  "before_state_hash": "sha256",  // ← for rollback
  "after_state_hash": "sha256"
}
```

### Example 1: Chat Write

**Scenario:** User sends message, chat_agent creates Episode

**DecisionTrace:**
```json
{
  "trace_id": "trace_chat_001",
  "timestamp_ms": 1708000000000,
  "decision_type": "graph_mutation",
  "endpoint": "/chat",
  "context": {
    "hop_count": 1,
    "session_id": "sess_123"
  },
  "graph_mutations": [
    {
      "node_id": "epi_abc",
      "layer": "L4_Episodic",
      "operation": "CREATE",
      "labels": ["Episode"],
      "properties": {
        "content": "User asked about weather",
        "emotional_valence": 0.3,
        "participants": ["user_001"]
      }
    },
    {
      "node_id": "work_def",
      "layer": "L2_Working",
      "operation": "UPDATE",
      "properties_updated": ["last_accessed", "access_count"]
    }
  ],
  "before_state_hash": "sha256:abc...",
  "after_state_hash": "sha256:def..."
}
```

**Graph Node Created:**
```cypher
CREATE (e:Episode {
  id: 'epi_abc',
  trace_id: 'trace_chat_001',
  decision_id: 'decision_789',
  content: 'User asked about weather',
  emotional_valence: 0.3,
  created_at: datetime(),
  source: 'chat_agent',
  operation: 'CREATE'
})
```

### Example 2: Async Materializer Write

**Scenario:** Materializer recalcula L3 (ShortTerm) patterns cada hora

**DecisionTrace:**
```json
{
  "trace_id": "trace_mat_001",
  "timestamp_ms": 1708003600000,
  "decision_type": "materializer_run",
  "context": {
    "materializer": "pattern_extractor_v2",
    "layer": "L3_ShortTerm",
    "input_nodes": 1500,
    "output_nodes": 23
  },
  "graph_mutations": [
    {
      "node_id": "st_pattern_1",
      "layer": "L3_ShortTerm",
      "operation": "MERGE",
      "pattern": "morning_coffee_routine"
    }
  ],
  "before_state_hash": "sha256:xyz...",
  "after_state_hash": "sha256:wvu..."
}
```

**Graph Node:**
```cypher
MERGE (st:ShortTerm {id: 'st_pattern_1'})
ON CREATE SET st.trace_id = 'trace_mat_001', st.created_at = datetime()
ON MATCH SET st.updated_at = datetime(), st.version = coalesce(st.version, 0) + 1
SET st.pattern = 'morning_coffee_routine', st.decision_id = 'mat_run_001'
```

### Linkage Verification Query

```cypher
// Verify all L4 writes have trace linkage
MATCH (e:Episode)
WHERE e.created_at > datetime() - duration({hours: 1})
  AND (e.trace_id IS NULL OR e.decision_id IS NULL)
RETURN count(e) as unlinked_writes

// Correlation: DecisionTrace → Graph mutations
MATCH (d:Decision {trace_id: 'trace_chat_001'})
OPTIONAL MATCH (e:Episode {trace_id: d.trace_id})
RETURN d.trace_id, d.decision_type, count(e) as nodes_created
```

---

## WS4: MATERIALIZERS (CELERY) PLAN

### Job Definitions

**Job 1: PatternExtractor (L3 ShortTerm)**
- **Trigger:** Every hour (Celery beat)
- **Input Query:**
  ```cypher
  MATCH (e:Ephemeral)
  WHERE e.created_at > datetime() - duration({hours: 1})
  RETURN e.session_id, e.content, e.timestamp
  ```
- **Logic:** Extract frequent patterns, calculate confidence
- **Output Mutation:**
  ```cypher
  MERGE (st:ShortTerm {pattern_hash: $hash})
  ON CREATE SET st.created_at = datetime(), st.trace_id = $trace_id
  SET st.frequency = st.frequency + 1, st.last_seen = datetime()
  ```
- **Fail-Open:** If fails, mark L3 as "stale" in /telemetry, continue
- **Priority:** HIGH (blocks context enrichment)

**Job 2: EpisodeConsolidator (L4)**
- **Trigger:** Daily at 2 AM
- **Input:** Ephemeral + Working from last 24h
- **Logic:** Cluster related events into episodes, deduplicate
- **Output:** Merge into L4, delete processed L1/L2
- **Fail-Open:** Skip deletion if merge fails (conservative)
- **Priority:** MEDIUM

**Job 3: SemanticEnricher (L5)**
- **Trigger:** New L4 episodes with unknown concepts
- **Input:** Episode content text
- **Logic:** NER + concept extraction, link to existing L5
- **Output:**
  ```cypher
  MERGE (c:Concept {name: $concept})
  MERGE (e:Episode {id: $epi_id})-[:MENTIONS]->(c)
  ```
- **Fail-Open:** Queue for manual review if confidence < 0.7
- **Priority:** LOW (background learning)

**Job 4: HabitDetector (L7)**
- **Trigger:** Weekly
- **Input:** L3 patterns + L4 episodes (7 days)
- **Logic:** Detect trigger-action-reward loops, streak calculation
- **Output:** Create/update L7 Habits
- **Fail-Open:** Silent (no habits detected this week)
- **Priority:** LOW

**Job 5: MetacognitiveReflection (L12)**
- **Trigger:** Every 6 hours
- **Input:** All layers coherence metrics, prediction accuracy
- **Logic:** Calculate self-model version, uncertainty
- **Output:** Update L12 node
- **Fail-Open:** Use previous state, alert if stale > 24h
- **Priority:** MEDIUM (blocks ops visibility)

### Materializer Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    MATERIALIZER ENGINE                       │
└─────────────────────────────────────────────────────────────┘

Celery Beat (Scheduler)
    │
    ├─ Every 1h ──▶ PatternExtractor ──┐
    ├─ Daily 2am ─▶ EpisodeConsolidator │
    ├─ On Event ──▶ SemanticEnricher   ├──▶ Celery Queue
    ├─ Weekly ────▶ HabitDetector      │
    └─ Every 6h ──▶ Metacognitive     ─┘
                          │
                          ▼
                   ┌──────────────┐
                   │    Worker    │
                   │   (Celery)   │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌─────────┐ ┌─────────┐ ┌─────────┐
        │  READ   │ │ PROCESS │ │  WRITE  │
        │  Graph  │ │  Logic  │ │  Graph  │
        │  (L1-4) │ │         │ │ (L3-12) │
        └────┬────┘ └────┬────┘ └────┬────┘
             │           │           │
             └───────────┴───────────┘
                         │
                    DecisionTrace
                    (async job trace)
```

### Fail-Open Behavior

| Failure Mode | Materializer Behavior | Graph Impact | Ops Alert |
|--------------|----------------------|--------------|-----------|
| Redis down | Jobs queue locally (fallback), retry every 30s | Delayed updates | 🟡 WARNING after 5 min |
| Celery worker crash | Job requeued automatically, max 3 retries | Stale data | 🟡 WARNING after 2 fails |
| Graph write fail | Log error, mark job failed, NO partial writes | Consistent but stale | 🔴 CRITICAL if > 10% fail |
| Timeout (30s) | Kill job, requeue with lower priority | Delayed | 🟡 WARNING |

---

## WS5: CREWAI AS RUNNER (CONTROL_ROOM INTEGRATION)

### Architecture: CrewAI Executes, Graph Stores

**CrewAI Role:** Runner/Executor, NOT model owner
- Lee capas del Graph
- Ejecuta "runs" (secuencias de pasos)
- Propone cambios al Graph
- Escribe artifacts (JSON files)

**Control_Room Role:** Orchestrator
- Dispara runs de CrewAI
- Maneja leases/locks
- Valida artifacts
- Commitea cambios al Graph (o rechaza)

### Run Types & Steps

| Run Type | Trigger | Steps | Artifact | Graph Mutations |
|----------|---------|-------|----------|-----------------|
| **daily_consolidation** | Cron 2 AM | 1. Extract patterns<br>2. Form episodes<br>3. Cleanup ephemeral | `consolidation_report.json` | L1→L4, delete L1 expired |
| **habit_analysis** | Weekly | 1. Load L3 patterns<br>2. Detect loops<br>3. Score habits | `habits_detected.json` | Create/update L7 |
| **semantic_enrichment** | On new episode | 1. Parse content<br>2. Extract entities<br>3. Link concepts | `concepts_extracted.json` | Create L5, link L4→L5 |
| **metacognitive_audit** | Every 6h | 1. Score coherence<br>2. Detect drift<br>3. Update self-model | `metacognitive_state.json` | Update L12 |

### Control_Room ↔ CrewAI Flow

```
control_room
    │
    ├─ Trigger: schedule OR event
    │
    ▼
┌─────────────────┐
│  ACQUIRE LEASE  │ ◀── SQLite lock
│  (timeout: 5m)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DISPATCH TO    │
│  CREWAI RUNNER  │ ◀── Celery task
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CREWAI READS   │
│  LAYERS L1-L12  │ ◀── Graph queries
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  EXECUTES STEPS │
│  (logic + LLM)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  WRITES ARTIFACT│
│  (JSON to disk) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  control_room   │
│  VALIDATES      │
│  (schema check) │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│COMMIT  │ │ REJECT │
│to Graph│ │ + log  │
└────┬───┘ └────────┘
     │
     ▼
┌─────────────────┐
│  WRITE          │
│  DecisionTrace  │
│  (run outcome)  │
└─────────────────┘
```

### Artifact Schema (Validated by Control_Room)

```json
{
  "artifact_id": "uuid",
  "run_id": "uuid",
  "run_type": "daily_consolidation",
  "timestamp": "2026-02-18T02:00:00Z",
  "crewai_version": "0.1.0",
  "steps_executed": [
    {
      "step": 1,
      "name": "extract_patterns",
      "input_nodes": 1500,
      "output_nodes": 23,
      "duration_ms": 5000
    }
  ],
  "proposed_mutations": [
    {
      "layer": "L4_Episodic",
      "operation": "CREATE",
      "nodes": [{"id": "epi_1", "properties": {...}}]
    }
  ],
  "validation": {
    "schema_valid": true,
    "constraints_passed": true,
    "approval_required": false
  }
}
```

### Approval Gates

| Mutation Type | Auto-Approve | Requires Approval |
|---------------|--------------|-------------------|
| L1-L4 CREATE | ✅ Yes (ephemeral) | - |
| L5-L6 MERGE | ✅ Yes (confidence > 0.8) | If confidence < 0.8 |
| L7 CREATE | ❌ No | Always (habits sensitive) |
| L9-L12 UPDATE | ⚠️ Conditional | If coherence change > 20% |
| DELETE any | ❌ No | Always (conservative) |

---

## WS6: PR PLAN + VALIDATION

### PR-1: Graph Inventory + Contracts Documentation
**Goal:** Baseline documentation of current schema + gaps
**Scope:**
- Document 12 layers as-is
- Identify gaps (WS1 table)
- Write contract templates (WS2)

**Files:**
- `docs/graph_layer_inventory.md`
- `docs/layer_access_contracts.md`

**Risks:** Low (documentation only)
**Rollback:** `git checkout -- docs/`
**Validation:**
```bash
# Check docs exist
ls docs/graph_layer_inventory.md docs/layer_access_contracts.md

# Validate schema query returns
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687')
with driver.session() as s:
    result = s.run('MATCH (n) RETURN distinct labels(n) as labels')
    print([r['labels'] for r in result])
"
```

---

### PR-2: DecisionTrace Linkage Plumbing
**Goal:** Add trace_id/decision_id to all layer writes
**Scope:**
- Update Graph schema (add properties)
- Modify write paths in denis_agent
- Backfill missing trace_ids (batch job)

**Files:**
- `migrations/add_trace_fields.cypher`
- `denis_unified_v1/chat_cp/graph_trace.py` (modify)
- `scripts/backfill_trace_ids.py`

**Risks:** Medium (schema migration)
**Rollback:** Restore from backup
**Validation:**
```bash
# Check all L4 have trace_id
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687')
with driver.session() as s:
    total = s.run('MATCH (e:Episode) RETURN count(e) as c').single()['c']
    linked = s.run('MATCH (e:Episode) WHERE e.trace_id IS NOT NULL RETURN count(e) as c').single()['c']
    print(f'Linked: {linked}/{total} ({100*linked/total:.1f}%)')
    assert linked/total > 0.99
"
```

---

### PR-3: Materializer Job 1 - PatternExtractor
**Goal:** Real async job for L3 (ShortTerm)
**Scope:**
- Celery task definition
- Celery beat schedule
- Graph read/write logic

**Files:**
- `workers/materializers/__init__.py`
- `workers/materializers/pattern_extractor.py`
- `workers/celery_app.py`

**Risks:** Medium (introduces async dependency)
**Rollback:** Disable in celery beat schedule
**Validation:**
```bash
# Trigger manually
celery -A workers.celery_app call materializers.pattern_extractor

# Check L3 updated
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687')
with driver.session() as s:
    count = s.run('MATCH (st:ShortTerm) WHERE st.created_at > datetime() - duration({minutes: 5}) RETURN count(st) as c').single()['c']
    print(f'New ShortTerm nodes: {count}')
    assert count > 0
"
```

---

### PR-4: Telemetry Exposure (Layer Freshness)
**Goal:** Expose layer health in /telemetry
**Scope:**
- Add layer metrics to telemetry endpoint
- Stale detection per layer
- TTL warnings

**Files:**
- `api/routes/telemetry_ops.py` (modify)
- `services/layer_health_checker.py` (new)

**Risks:** Low (additive)
**Rollback:** `git revert HEAD`
**Validation:**
```bash
curl http://nodo1:9999/telemetry | jq '.layers'

# Expected:
# {
#   "L1_Ephemeral": {"count": 150, "freshness": "fresh", "oldest_seconds": 1800},
#   "L4_Episodic": {"count": 5000, "freshness": "fresh", "oldest_seconds": 86400},
#   "L3_ShortTerm": {"count": 23, "freshness": "stale", "last_update": "2h ago"}
# }
```

---

### PR-5: UI Ops Visibility (Nodo2 Integration)
**Goal:** Frontend can visualize layer health
**Scope:**
- Extend /health with layer summary
- Add /layers/status endpoint
- Document for frontend team

**Files:**
- `api/routes/layers_ops.py` (new)
- `docs/frontend_integration.md`

**Risks:** Low (new endpoint)
**Rollback:** Remove router registration
**Validation:**
```bash
curl http://nodo1:9999/layers/status | jq

# Check fields
curl http://nodo1:9999/layers/status | jq 'keys'
# Expected: ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10", "L11", "L12"]
```

---

### PR-6: Control_Room + CrewAI Integration
**Goal:** CrewAI runs via control_room with artifacts
**Scope:**
- Control_room lease management
- CrewAI runner integration
- Artifact validation
- Approval gates

**Files:**
- `control_room/runners/crewai_runner.py` (new)
- `control_room/artifact_validator.py` (new)
- `control_room/approval_gates.py` (new)

**Risks:** High (new critical path)
**Rollback:** Disable runner, fallback to manual
**Validation:**
```bash
# Trigger run
curl -X POST http://nodo1:9999/control_room/run \
  -d '{"type": "daily_consolidation", "async": true}'

# Check artifact created
ls artifacts/runs/daily_consolidation_*.json

# Check DecisionTrace
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687')
with driver.session() as s:
    result = s.run('MATCH (d:Decision) WHERE d.decision_type = \"crewai_run\" RETURN count(d) as c')
    print(f'CrewAI runs logged: {result.single()[\"c\"]}')
"
```

---

### PR-7: Guardrails (Idempotency + Retries + Rollback)
**Goal:** Production-ready reliability
**Scope:**
- Idempotency keys in all writes
- Retry logic with exponential backoff
- Rollback capability for failed mutations

**Files:**
- `utils/idempotency.py` (new)
- `utils/rollback.py` (new)
- `middleware/retry.py` (new)

**Risks:** Medium (changes write paths)
**Rollback:** Disable middleware
**Validation:**
```bash
# Test idempotency
python -c "
from utils.idempotency import generate_key
key1 = generate_key('chat', 'user_001', 'msg_123')
key2 = generate_key('chat', 'user_001', 'msg_123')
assert key1 == key2, 'Idempotency keys must be deterministic'
print('✓ Idempotency keys work')
"

# Test retry
python -c "
from utils.retry import retry_with_backoff
@retry_with_backoff(max_retries=3)
def flaky():
    flaky.calls = getattr(flaky, 'calls', 0) + 1
    if flaky.calls < 3:
        raise Exception('fail')
    return 'success'
result = flaky()
assert result == 'success'
assert flaky.calls == 3
print('✓ Retry logic works')
"
```

---

### PR-8: Integration Tests + Load Validation
**Goal:** Automated validation of entire stack
**Scope:**
- E2E tests for layer writes
- Load tests for materializers
- Game Day automation

**Files:**
- `tests/e2e/test_layers.py`
- `tests/load/test_materializers.py`
- `scripts/game_day_automation.py`

**Risks:** Low (tests only)
**Rollback:** N/A
**Validation:**
```bash
make test-e2e
# Expected: All tests pass

make test-load
# Expected: 100 req/s, < 1% errors

./scripts/game_day_automation.py --scenario loop_storm
# Expected: System survives, alerts fire
```

---

## SUMMARY: ACTIVATION SEQUENCE

```
Week 1:
  PR-1: Inventory & Contracts
  PR-2: DecisionTrace Plumbing
  
Week 2:
  PR-3: Materializer PatternExtractor
  PR-4: Telemetry Layer Exposure
  
Week 3:
  PR-5: UI Ops Visibility
  PR-6: CrewAI Integration
  
Week 4:
  PR-7: Guardrails
  PR-8: Integration Tests
  
Week 5:
  Game Days (all 8 scenarios)
  Performance tuning
  Go/No-Go decision
```

### Final State (Post-Activation)

| Component | Status | Verification |
|-----------|--------|--------------|
| 12 Layers | ✅ Active | All have read/write contracts |
| DecisionTrace | ✅ Linked | Every write has trace_id |
| Materializers | ✅ Running | 5 jobs scheduled + monitored |
| CrewAI | ✅ Integrated | Runs via control_room with artifacts |
| Telemetry | ✅ Layer-aware | /telemetry shows layer health |
| Control_Room | ✅ Extended | Manages async runs |

**Riesgo residual:** Medio (introduce async stack, pero NO crítico para /chat)  
**Go/No-Go:** Se evalúa tras Game Days en Week 5

**Firma:** IZQUIERDA  
**Fecha:** 2026-02-18  
**Plan:** 8 PRs, 5 semanas, activación incremental
