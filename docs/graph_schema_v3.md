# Graph Schema v3

## Overview

This document defines the canonical Neo4j graph schema for the DENIS system. The graph serves as the single source of truth for system topology, component state, and operational data.

## Node Types

### 1. SystemState

The root node representing the overall system.

```cypher
(:SystemState {
    id: String,              -- 'denis_unified_v1'
    generated_at: ISO8601,   -- generation timestamp
    version: String,         -- schema version (v3)
    status: String,          -- stable, beta, wip
    confidence: String       -- high, medium, low
})
```

---

### 2. Node

Physical or logical hosts in the system.

```cypher
(:Node {
    id: String,              -- unique identifier (nodomac, nodo1, nodo2)
    name: String,           -- display name
    hostname: String,       -- DNS hostname
    ip: String,            -- IP address
    platform: String,       -- OS (Linux, macOS, Windows)
    is_local: Boolean,      -- whether this is the local node
    gpu: String,           -- GPU info (optional)
    created_at: ISO8601    -- creation timestamp
})
```

---

### 3. Component

Software services deployed in the system.

```cypher
(:Component {
    id: String,              -- unique identifier
    name: String,           -- display name
    type: String,           -- service, orchestration, hardening, booster, iot
    location: String,       -- filesystem path
    port: Integer,          -- listen port (optional)
    status: String,         -- feature_flagged, active, inactive
    version: String,        -- semantic version
    description: String     -- human-readable description
})
```

**Types:**
- `service` - Long-running API services
- `orchestration` - Workflow/orchestration engines
- `hardening` - Resilience components (leases, heartbeats)
- `booster` - Capability boosters
- `iot` - IoT integrations

---

### 4. Provider

External service providers integrated with the system.

```cypher
(:Provider {
    id: String,              -- unique identifier (openai_chat, anthropic_chat)
    name: String,           -- display name
    type: String,           -- llm, tts, embedding
    parent: String,         -- parent component ID
    status: String,         -- configured, available, unavailable
    model_default: String   -- default model for this provider
})
```

---

### 5. Step

Orchestration steps in control room.

```cypher
(:Step {
    id: String,              -- unique identifier
    name: String,           -- step name
    component: String,      -- parent component ID
    timeout_ms: Integer,    -- max execution time
    retry_max: Integer      -- max retry attempts
})
```

---

### 6. FeatureFlag

Feature toggles controlling system behavior.

```cypher
(:FeatureFlag {
    id: String,              -- env var name
    name: String,           -- full name
    default_value: Boolean,  -- default value
    description: String,    -- purpose
    component: String       -- owning component
})
```

---

### 7. HealthState

Current health status of nodes and components.

```cypher
(:HealthState {
    id: String,              -- node_id + '_health'
    entity_type: String,     -- 'node' or 'component'
    entity_id: String,       -- reference to Node or Component
    status: String,          -- alive, degraded, stale, down, blocked
    checked_at: ISO8601,    -- last check timestamp
    details: Map             -- additional status info
})
```

---

### 8. OverlayRoot

Logical namespace definitions for the overlay filesystem.

```cypher
(:OverlayRoot {
    id: String,              -- root_id (denis_repo, artifacts, etc)
    logical_prefix: String,  -- overlay:// prefix
    description: String      -- purpose
})
```

---

### 9. Manifest

File index snapshots.

```cypher
(:Manifest {
    id: String,              -- manifest_id
    root_id: String,         -- reference to OverlayRoot
    generated_at: ISO8601,   -- creation time
    status: String,          -- current, stale, superseded
    total_files: Integer,    -- file count
    total_bytes: Integer     -- total size
})
```

---

### 10. Device (IoT)

IoT devices connected to the system.

```cypher
(:Device {
    id: String,              -- unique device ID
    name: String,            -- display name
    type: String,           -- gps, camera, sensor, switch, light
    status: String,         -- online, offline, error
    last_seen: ISO8601,     -- last communication
    metadata: Map            -- device-specific info
})
```

---

### 11. Person

Users or entities interacting with the system.

```cypher
(:Person {
    id: String,              -- unique person ID
    name: String,           -- display name
    type: String,           -- user, admin, device
    attributes: Map         -- profile attributes
})
```

---

### 12. Event

Audit and system events.

```cypher
(:Event {
    id: String,              -- unique event ID
    type: String,           -- event type
    source: String,         -- source component/device
    timestamp: ISO8601,    -- event time
    data: Map              -- event payload
})
```

---

### 13. Decision

Routing and policy decisions.

```cypher
(:Decision {
    id: String,              -- unique decision ID
    type: String,           -- routing, policy, action
    timestamp: ISO8601,     -- decision time
    inputs: Map,           -- decision inputs
    policy: String,         -- policy used
    selected: String,       -- selected option
    chain: List,           -- options considered
    outcome: String,        -- success, failure, fallback
    latency_ms: Integer    -- decision time
})
```

---

## Relationship Types

| Relationship | From | To | Properties |
|--------------|------|-----|------------|
| `CONNECTED_TO` | Node | Node | `type`, `latency_ms` |
| `HOSTS` | Node | Component | `since` |
| `HAS_PROVIDER` | Component | Provider | - |
| `HAS_STEP` | Component | Step | - |
| `HAS_FEATURE_FLAG` | Component | FeatureFlag | - |
| `HAS_HEALTH` | Node | HealthState | - |
| `DEFINES_ROOT` | Component | OverlayRoot | - |
| `HAS_MANIFEST` | OverlayRoot | Manifest | - |
| `HAS_COMPONENT` | SystemState | Component | - |
| `HAS_NODE` | SystemState | Node | - |
| `DEPENDS_ON` | Component | Component | - |
| `LOCATED_AT` | Device | Node | - |
| `OWNED_BY` | Device | Person | - |
| `GENERATED_BY` | Event | Component | - |
| `GENERATED_BY` | Event | Device | - |
| `TRIGGERED` | Decision | Event | - |

---

## Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SystemState                                     │
│                                                                              │
│         ┌──────────────────────┐                                          │
│         │                      │                                          │
│         ▼                      ▼                                          │
│  ┌─────────────┐        ┌─────────────┐                                   │
│  │  Component  │        │    Node     │                                   │
│  │  (service)  │        │ (physical)  │                                   │
│  └──────┬──────┘        └──────┬──────┘                                   │
│         │                       │                                           │
│         │ HOSTS                │ CONNECTED_TO                              │
│         ▼                       ▼                                          │
│  ┌─────────────┐        ┌─────────────┐                                   │
│  │  Provider   │        │HealthState  │                                   │
│  │  (external) │        │             │                                   │
│  └─────────────┘        └─────────────┘                                   │
│                                                                              │
│         │                                                                │
│         │ DEFINES_ROOT                                                   │
│         ▼                                                                │
│  ┌─────────────┐        ┌─────────────┐                                   │
│  │OverlayRoot  │───────▶│  Manifest    │                                   │
│  │             │        │             │                                   │
│  └─────────────┘        └─────────────┘                                   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                           Events & Decisions                      │        │
│  │                                                                   │        │
│  │   ┌──────────┐         ┌──────────┐         ┌──────────┐    │        │
│  │   │  Event   │◀─────────│ Decision │─────────▶│  Device  │    │        │
│  │   │ (audit)  │          │ (routing)│          │  (IoT)   │    │        │
│  │   └──────────┘          └──────────┘          └──────────┘    │        │
│  │                                                                   │        │
│  │                        ┌──────────┐                               │        │
│  │                        │  Person  │◀──────────┤                  │        │
│  │                        │ (user)   │           │                  │        │
│  │                        └──────────┘           │                  │        │
│  └───────────────────────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Indexes

```cypher
CREATE INDEX node_id IF NOT EXISTS FOR (n:Node) ON (n.id);
CREATE INDEX component_id IF NOT EXISTS FOR (c:Component) ON (c.id);
CREATE INDEX provider_id IF NOT EXISTS FOR (p:Provider) ON (p.id);
CREATE INDEX health_entity IF NOT EXISTS FOR (h:HealthState) ON (h.entity_id);
CREATE INDEX feature_flag_id IF NOT EXISTS FOR (f:FeatureFlag) ON (f.id);
CREATE INDEX system_state_id IF NOT EXISTS FOR (s:SystemState) ON (s.id);
CREATE INDEX device_id IF NOT EXISTS FOR (d:Device) ON (d.id);
CREATE INDEX person_id IF NOT EXISTS FOR (p:Person) ON (p.id);
CREATE INDEX event_timestamp IF NOT EXISTS FOR (e:Event) ON (e.timestamp);
CREATE INDEX decision_timestamp IF NOT EXISTS FOR (d:Decision) ON (d.timestamp);
```

---

## Example Queries

### Get all components on a node

```cypher
MATCH (n:Node {id: 'nodomac'})-[:HOSTS]->(c:Component)
RETURN c.id, c.name, c.status;
```

### Get provider chain for Chat CP

```cypher
MATCH (c:Component {id: 'chat_cp'})-[:HAS_PROVIDER]->(p:Provider)
RETURN p.id, p.name, p.status, p.model_default;
```

### Get all feature flags

```cypher
MATCH (c:Component)-[:HAS_FEATURE_FLAG]->(ff:FeatureFlag)
RETURN c.id AS component, ff.id AS flag, ff.default_value;
```

### Get node health summary

```cypher
MATCH (n:Node)-[:HAS_HEALTH]->(h:HealthState)
RETURN n.id AS node, h.status, h.checked_at;
```

### Get IoT devices for a person

```cypher
MATCH (p:Person {id: 'user_001'})<-[:OWNED_BY]-(d:Device)
RETURN d.id, d.name, d.type, d.status;
```

### Get recent routing decisions

```cypher
MATCH (d:Decision {type: 'routing'})
WHERE d.timestamp > datetime() - duration({hours: 1})
RETURN d.id, d.selected, d.outcome, d.latency_ms
ORDER BY d.timestamp DESC;
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-02-16 | Initial schema with nodes and components |
| v2 | 2026-02-16 | Added Chat CP providers |
| v3 | 2026-02-17 | Added Device, Person, Event, Decision nodes |

---

## Seed File

Run the seed file to populate the graph:

```bash
cypher-shell -u neo4j -p <password> < scripts/seeds/system_state_v3.cypher
```
