# Graph Schema Documentation

## Overview

This document defines the canonical graph schema for the DENIS control plane. The graph serves as the single source of truth for system topology, component state, and operational data.

## Node Types

### Node (Physical/Logical Hosts)

```cypher
(:Node {
    id: String,              -- unique identifier (nodomac, nodo1, nodo2)
    name: String,            -- display name
    hostname: String,        -- DNS hostname
    ip: String,              -- IP address
    platform: String,        -- OS (Linux, macOS, Windows)
    is_local: Boolean,       -- whether this is the local node
    gpu: String,            -- GPU info (optional)
    created_at: ISO8601     -- creation timestamp
})
```

**Relationships:**
- `(:Node)-[:CONNECTED_TO]->(:Node)` - Network topology with latency
- `(:Node)-[:HOSTS]->(:Component)` - Component deployment

### Component (Software Services)

```cypher
(:Component {
    id: String,              -- unique identifier
    name: String,            -- display name
    type: String,            -- service, orchestration, hardening, etc
    location: String,        -- filesystem path
    port: Integer,           -- listen port (optional)
    status: String,          -- feature_flagged, active, inactive
    version: String,         -- semantic version
    description: String      -- human-readable description
})
```

**Types:**
- `service` - Long-running API services
- `orchestration` - Workflow/orchestration engines
- `hardening` - Resilience components (leases, heartbeats)
- `provider` - External service providers

### Provider

```cypher
(:Provider {
    id: String,              -- unique identifier (openai_chat, anthropic_chat)
    name: String,            -- display name
    type: String,            -- always 'provider'
    parent: String,          -- parent component ID
    status: String,          -- configured, available, unavailable
    model_default: String    -- default model for this provider
})
```

### Step

```cypher
(:Step {
    id: String,              -- unique identifier
    name: String,            -- step name (overlay_scan, etc)
    component: String,       -- parent component ID
    timeout_ms: Integer,     -- max execution time
    retry_max: Integer       -- max retry attempts
})
```

### FeatureFlag

```cypher
(:FeatureFlag {
    id: String,              -- env var name
    name: String,            -- full name
    default_value: Boolean,  -- default value
    description: String,     -- purpose
    component: String        -- owning component
})
```

### HealthState

```cypher
(:HealthState {
    id: String,              -- node_id + '_health'
    node_id: String,         -- reference to Node
    status: String,          -- alive, degraded, stale, down, blocked
    checked_at: ISO8601,     -- last check timestamp
    details: Map             -- additional status info
})
```

### OverlayRoot

```cypher
(:OverlayRoot {
    id: String,              -- root_id (denis_repo, artifacts, etc)
    logical_prefix: String,  -- overlay:// prefix
    description: String      -- purpose
})
```

### Manifest

```cypher
(:Manifest {
    id: String,              -- manifest_id
    root_id: String,         -- reference to OverlayRoot
    generated_at: ISO8601,  -- creation time
    status: String,          -- current, stale, superseded
    total_files: Integer,    -- file count
    total_bytes: Integer     -- total size
})
```

### SystemState

```cypher
(:SystemState {
    id: String,              -- 'denis_unified_v1'
    generated_at: ISO8601,  -- generation timestamp
    version: String,         -- schema version (v3)
    status: String,          -- stable, beta, wip
    confidence: String       -- high, medium, low
})
```

## Relationship Types

| Relationship | From | To | Properties |
|--------------|------|-----|------------|
| `CONNECTED_TO` | Node | Node | `type` (ssh/http), `latency_ms` |
| `HOSTS` | Node | Component | `since` (ISO8601) |
| `HAS_PROVIDER` | Component | Provider | - |
| `HAS_STEP` | Component | Step | - |
| `HAS_FEATURE_FLAG` | Component | FeatureFlag | - |
| `HAS_HEALTH` | Node | HealthState | - |
| `DEFINES_ROOT` | Component | OverlayRoot | - |
| `HAS_MANIFEST` | Component | Manifest | - |
| `HAS_COMPONENT` | SystemState | Component | - |
| `HAS_NODE` | SystemState | Node | - |

## Indexes

```cypher
CREATE INDEX node_id IF NOT EXISTS FOR (n:Node) ON (n.id);
CREATE INDEX component_id IF NOT EXISTS FOR (c:Component) ON (c.id);
CREATE INDEX provider_id IF NOT EXISTS FOR (p:Provider) ON (p.id);
CREATE INDEX health_node_id IF NOT EXISTS FOR (h:HealthState) ON (h.node_id);
CREATE INDEX feature_flag_id IF NOT EXISTS FOR (f:FeatureFlag) ON (f.id);
CREATE INDEX system_state_id IF NOT EXISTS FOR (s:SystemState) ON (s.id);
```

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

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-02-16 | Initial schema with nodes and components |
| v2 | 2026-02-16 | Added Chat CP providers |
| v3 | 2026-02-17 | Added HealthState, OverlayRoot, Manifest, SystemState |

## Seed File

Run the seed file to populate the graph:

```bash
cypher-shell -u neo4j -p <password> < scripts/seeds/system_state_v3.cypher
```
