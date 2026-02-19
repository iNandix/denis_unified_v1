# Architecture Control Plane - Summary

## Executive Summary

This document consolidates the control plane architecture for DENIS, defining the canonical graph model, control plane ↔ graph contract, overlay/atlas mapping, and failure handling.

## System Components

| Component | Type | Location | Status |
|-----------|------|----------|--------|
| **Chat CP** | Service | denis_unified_v1/chat_cp | Feature-flagged |
| **Overlay FS** | Service | nodomac/overlay | Active |
| **Control Room** | Orchestration | nodomac/control_room | Active |
| **AtlasLite** | Service | nodomac | Active |
| **Inference Gateway** | Service | denis_unified_v1/inference | Active |

## Graph Schema v3

### Node Types
- **Node**: Physical/logical hosts (nodomac, nodo1, nodo2)
- **Component**: Software services
- **Provider**: External service providers (OpenAI, Anthropic, Local)
- **Step**: Orchestration steps
- **FeatureFlag**: Feature toggles
- **HealthState**: Health status
- **OverlayRoot**: Logical namespace
- **Manifest**: File index snapshot
- **SystemState**: Root reference

### Key Relationships
```
SystemState ──HAS_COMPONENT──▶ Component
SystemState ──HAS_NODE───────▶ Node
Node ──HOSTS─────────────────▶ Component
Node ──CONNECTED_TO─────────▶ Node
Component ──HAS_PROVIDER─────▶ Provider
Component ──HAS_FEATURE_FLAG─▶ FeatureFlag
Component ──DEFINES_ROOT────▶ OverlayRoot
OverlayRoot ──HAS_MANIFEST───▶ Manifest
```

## Deliverables Created

| File | Purpose |
|------|---------|
| `scripts/seeds/system_state_v3.cypher` | Graph seed with full schema |
| `docs/graph_schema.md` | Graph schema documentation |
| `var/state/graph_snapshot.json` | Example JSON export |
| `docs/control_plane_graph_contract.md` | Write/Read contract |
| `docs/overlay_graph_mapping.md` | Overlay ↔ Graph mapping |
| `docs/failure_state_machine.md` | State machine definition |

## Control Plane ↔ Graph

### Write Path (Runtime → Graph)
- **Events**: component_state_change, provider_failure, routing_decision, step_execution, health_check, node_heartbeat
- **Frequency**: On change (events), periodic (health/heartbeat)

### Read Path (Graph → Runtime)
- **Queries**: GET_PROVIDER_CHAIN, GET_FEATURE_FLAGS, GET_NODE_TOPOLOGY, GET_HEALTH_STATUS, GET_ROUTING_POLICY
- **Caching**: 10s-300s depending on data volatility

## Overlay / Atlas Mapping

| Concept | Graph | SQLite | Filesystem |
|---------|-------|--------|------------|
| Node definitions | ✅ | - | - |
| Component definitions | ✅ | - | - |
| Overlay roots | ✅ | ✅ | - |
| Manifest metadata | ✅ | ✅ | - |
| File entries | - | ✅ | - |
| Actual content | - | - | ✅ |

## Failure States

### States
- **OK**: Full functionality
- **DEGRADED**: Reduced functionality, fallback active
- **STALE**: No recent updates
- **DOWN**: Not responding
- **BLOCKED**: Waiting on external factor

### Key Transitions
- OK → DEGRADED: provider_error, timeout
- OK → STALE: heartbeat_timeout
- OK → DOWN: connection_failed
- DEGRADED → OK: recovery
- STALE → DOWN: no_heartbeat

## Implementation Checklist (Future)

### P0 - Critical
- [ ] Implement GraphEvent writer in runtime components
- [ ] Add Graph query cache to Chat CP router
- [ ] Wire heartbeat manager to graph
- [ ] Seed graph with v3 schema

### P1 - High
- [ ] Implement state machine in health checker
- [ ] Add failure event logging
- [ ] Create dashboard from graph queries
- [ ] Implement overlay manifest → graph sync

### P2 - Medium
- [ ] Add event replay capability
- [ ] Implement time-series metrics queries
- [ ] Create audit log from events
- [ ] Add AtlasLite graph projection

## Next Steps

1. **Seed the graph**: Run `scripts/seeds/system_state_v3.cypher`
2. **Wire Chat CP**: Enable `DENIS_ENABLE_CHAT_CP=1`
3. **Test write path**: Add event logging to components
4. **Test read path**: Query graph from router
5. **Monitor health**: View node/component status in graph

## Contact Points

- **Graph**: Neo4j at `bolt://localhost:7687`
- **SQLite**: nodomac.db at `/home/jotah/nodomac/nodomac.db`
- **Chat CP API**: Port 9999
- **Overlay API**: Port 19999
- **AtlasLite API**: Port 19998
