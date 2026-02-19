# Control Plane ↔ Graph Contract

## Overview

This document defines the contract between the Control Plane (runtime) and the Graph (Neo4j). It specifies what data flows in each direction and the minimal event schema.

## Data Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE (Runtime)                         │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Chat CP   │  │   Overlay   │  │Control Room│  │ Inference   │  │
│  │  Router    │  │  Resolver   │  │   Steps    │  │  Gateway    │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
│         │                 │                 │                 │         │
│         │   WRITE         │   WRITE         │   WRITE         │         │
│         ▼                 ▼                 ▼                 ▼         │
├─────────────────────────────────────────────────────────────────────────┤
│                              GRAPH (Neo4j)                             │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Nodes, Components, Providers, Health, Events, Routing,       │   │
│  │  Feature Flags, Snapshots, Manifests                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│         │                 │                 │                 │         │
│         │   READ          │   READ          │   READ          │         │
│         ▼                 ▼                 ▼                 ▼         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Policy     │  │   Routing   │  │  Topology   │  │  Capabilities│  │
│  │  Decisions  │  │   Table     │  │  Updates    │  │  Discovery   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## WRITE Path: Runtime → Graph

### Events to Persist

| Event Type | Trigger | Data | Frequency |
|------------|---------|------|-----------|
| `component_state_change` | Status change | `{component, old_state, new_state, timestamp}` | On change |
| `provider_failure` | Provider error | `{provider, error_code, error_msg, retryable}` | On error |
| `routing_decision` | Chat request | `{provider_chain, selected, latency_ms, success}` | Per request |
| `step_execution` | Control room step | `{step_id, status, duration_ms, artifacts}` | Per step |
| `health_check` | Periodic | `{node_id, status, details}` | Every 30s |
| `feature_flag_change` | Flag toggle | `{flag_id, old_value, new_value, actor}` | On change |
| `node_heartbeat` | Periodic | `{node_id, timestamp, load}` | Every 10s |

### Event Schema

```python
@dataclass
class GraphEvent:
    event_type: str           # component_state_change, provider_failure, etc.
    timestamp: str           # ISO8601
    source_component: str    # originating component
    data: dict               # event-specific payload
    trace_id: str            # for correlation
```

### Implementation

```python
# Example: Writing a routing decision
def write_routing_decision(trace_id: str, providers: list, selected: str, latency_ms: int):
    query = """
    MATCH (c:Component {id: 'chat_cp'})
    CREATE (c)-[:HAS_EVENT]->(e:RoutingEvent {
        event_id: $trace_id,
        timestamp: datetime(),
        provider_chain: $providers,
        selected_provider: $selected,
        latency_ms: $latency_ms
    })
    """
    # Execute with parameters
```

## READ Path: Graph → Runtime

### Queries to Execute

| Query | Purpose | Cache TTL |
|-------|---------|-----------|
| `GET_PROVIDER_CHAIN` | Get active providers in priority order | 60s |
| `GET_FEATURE_FLAGS` | Get current feature flag values | 30s |
| `GET_NODE_TOPOLOGY` | Get node addresses and capabilities | 60s |
| `GET_HEALTH_STATUS` | Get current health of all nodes | 10s |
| `GET_ROUTING_POLICY` | Get routing policy (fallback order) | 300s |

### Example Queries

#### Get Provider Chain

```cypher
MATCH (c:Component {id: 'chat_cp'})-[:HAS_PROVIDER]->(p:Provider)
WHERE p.status IN ['configured', 'available']
RETURN p.id, p.model_default
ORDER BY p.priority DESC
```

#### Get Feature Flags

```cypher
MATCH (c:Component)-[:HAS_FEATURE_FLAG]->(ff:FeatureFlag)
RETURN ff.id, ff.default_value
```

#### Get Node Topology

```cypher
MATCH (n:Node)-[:HOSTS]->(c:Component)
RETURN n.id, n.ip, collect(c.id) AS components
```

#### Get Health Status

```cypher
MATCH (n:Node)-[:HAS_HEALTH]->(h:HealthState)
RETURN n.id, h.status, h.checked_at
ORDER BY h.checked_at DESC
```

### Implementation

```python
# Example: Reading provider chain
def get_provider_chain() -> list[str]:
    query = """
    MATCH (c:Component {id: 'chat_cp'})-[:HAS_PROVIDER]->(p:Provider)
    WHERE p.status IN ['configured', 'available']
    RETURN p.id
    ORDER BY p.priority DESC
    """
    result = neo4j.execute(query)
    return [row['p.id'] for row in result]
```

## Minimal Events to Persist

### 1. Component State Change

```json
{
  "event_type": "component_state_change",
  "timestamp": "2026-02-17T00:00:00Z",
  "source_component": "chat_cp",
  "data": {
    "component": "openai_chat",
    "old_state": "available",
    "new_state": "unavailable",
    "reason": "quota_exceeded"
  },
  "trace_id": "req_123"
}
```

### 2. Routing Decision

```json
{
  "event_type": "routing_decision",
  "timestamp": "2026-02-17T00:00:00Z",
  "source_component": "chat_cp",
  "data": {
    "chain": ["anthropic_chat", "openai_chat", "local_chat"],
    "selected": "anthropic_chat",
    "latency_ms": 450,
    "success": true,
    "model": "claude-3-5-haiku-latest"
  },
  "trace_id": "req_456"
}
```

### 3. Step Execution

```json
{
  "event_type": "step_execution",
  "timestamp": "2026-02-17T00:00:00Z",
  "source_component": "control_room",
  "data": {
    "step_id": "overlay_scan",
    "status": "completed",
    "duration_ms": 12500,
    "artifacts": ["manifest.json"]
  },
  "trace_id": "step_789"
}
```

### 4. Health Check

```json
{
  "event_type": "health_check",
  "timestamp": "2026-02-17T00:00:00Z",
  "source_component": "heartbeat_manager",
  "data": {
    "node_id": "nodomac",
    "status": "alive",
    "details": {
      "cpu_percent": 45,
      "memory_percent": 62,
      "disk_percent": 34
    }
  },
  "trace_id": "health_001"
}
```

## Caching Strategy

| Data Type | Source | Cache TTL | Invalidation |
|-----------|--------|-----------|--------------|
| Provider chain | Graph | 60s | On provider state change |
| Feature flags | Graph | 30s | On flag change |
| Node topology | Graph | 60s | On node add/remove |
| Health status | Graph | 10s | Always fresh |
| Routing policy | Graph | 300s | On policy change |

## Error Handling

- If graph is unavailable: Use in-memory cache with stale data, log warning
- If write fails: Retry 3 times with exponential backoff, then log error
- If read returns stale (>5min): Log warning, use cached value

## Future Enhancements

- [ ] Add event replay capability
- [ ] Implement event sourcing for audit
- [ ] Add time-series queries for metrics
- [ ] Implement event aggregation for dashboards
