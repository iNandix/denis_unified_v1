# WS23-G Neuro Layers — Graph SSoT Contract

## Overview
Denis Persona mantiene 12 capas neurocognitivas como nodos en el grafo (Neo4j SSoT).
Al arrancar conversación, ejecuta WAKE_SEQUENCE; en cada turno, UPDATE_SEQUENCE.
El estado derivado (ConsciousnessState) controla tono, prioridades, guardrails, y memoria.

## Nodes

### NeuroLayer (x12)
```
(:NeuroLayer {
  id: "neuro:layer:{1..12}",
  layer_index: int,
  layer_key: string,
  title: string,
  freshness_score: float (0..1),
  status: "ok"|"degraded"|"stale"|"error",
  signals_count: int,
  last_update_ts: ISO-8601,
  notes_hash: string|null
})
```

### ConsciousnessState (singleton)
```
(:ConsciousnessState {
  id: "denis:consciousness",
  mode: "awake"|"focused"|"idle"|"degraded",
  focus_topic_hash: string|null,
  fatigue_level: float (0..1),
  risk_level: float (0..1),
  confidence_level: float (0..1),
  last_wake_ts: ISO-8601,
  last_turn_ts: ISO-8601,
  guardrails_mode: "normal"|"strict",
  memory_mode: "short"|"balanced"|"long",
  voice_mode: "on"|"off"|"stub",
  ops_mode: "normal"|"incident",
  updated_ts: ISO-8601
})
```

## Edges
```
(Identity {id: "identity:denis"})-[:HAS_NEURO_LAYER]->(NeuroLayer)
(Identity {id: "identity:denis"})-[:HAS_CONSCIOUSNESS_STATE]->(ConsciousnessState)
(ConsciousnessState)-[:DERIVED_FROM]->(NeuroLayer)  // x12
```

## 12 Layers

| # | Key | Title | Signals |
|---|-----|-------|---------|
| 1 | sensory_io | Sensory/IO | WS latency, errors, input modality |
| 2 | attention | Attention | Focus topic, relevance, noise |
| 3 | intent_goals | Intent/Goals | Active goals hash, constraints hit |
| 4 | plans_procedures | Plans/Procedures | Active plans/tasks, progress |
| 5 | memory_short | Memory Short | Turn recency, session window |
| 6 | memory_long | Memory Long | Qdrant retrieval stats, chunks |
| 7 | safety_governance | Safety/Governance | Guardrail triggers, risk score |
| 8 | ops_awareness | Ops Awareness | Health/telemetry, incident mode |
| 9 | social_persona | Social/Persona | Tone, verbosity, empathy |
| 10 | self_monitoring | Self-Monitoring | Contradictions, retry loops |
| 11 | learning_plasticity | Learning/Plasticity | Changed components, regressions |
| 12 | meta_consciousness | Meta/Consciousness | Global state derivation input |

## Event Types
- `neuro.wake.start` (stored=true)
- `neuro.layer.snapshot` (stored=false, x12)
- `neuro.consciousness.snapshot` (stored=true)
- `neuro.turn.update` (stored=true)
- `neuro.consciousness.update` (stored=true)
- `persona.state.update` (stored=false)

## Rollback
```
NEURO_ENABLED=0
```
Persona sigue en modo degradado sin neuro state.

## Hard Rules
- No raw user text in nodes (only hashes, counters, timestamps)
- All operations MERGE-based (idempotent)
- Fail-open: graph down -> degraded defaults, conversation continues
