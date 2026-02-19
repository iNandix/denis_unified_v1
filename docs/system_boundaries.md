# System Boundaries & Responsibilities

## Overview

This document defines clear ownership and boundaries for each subsystem in the DENIS architecture. Each subsystem has defined inputs, outputs, and failure modes.

---

## 1. Denis Core (nodo1)

### Responsibility
The main backend API and orchestration layer. Handles user requests, routes to appropriate services, and manages the overall system.

### Inputs
- HTTP requests on port 9999
- Feature flags from environment
- Neo4j for graph data
- Redis for caching
- Provider configurations

### Outputs
- JSON responses to clients
- Logs to stdout
- Metrics to observability system

### Key Functions
- Chat completion API (`/v1/chat`)
- OpenAI-compatible API (`/openai/v1/*`)
- Memory operations (`/memory/*`)
- Metacognitive operations (`/metacognitive/*`)

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Neo4j unavailable | Read operations fail | Use cache, fallback to defaults |
| Redis unavailable | Cache misses | Direct database queries |
| Provider timeout | Request hangs | Apply timeout, return error |
| Out of memory | Process crash | Restart, scale down |

### Owner
- **Team**: Backend
- **SLA**: 99.9% uptime

---

## 2. Chat CP (nodomac)

### Responsibility
Multi-provider chat abstraction layer. Routes chat requests to OpenAI, Anthropic, or local fallback. Manages secrets via OS keyring.

### Inputs
- Chat requests (messages, model preferences)
- Feature flags (`DENIS_ENABLE_CHAT_CP`)
- Provider API keys (from keyring)
- Routing policy (from graph)

### Outputs
- Chat responses
- Decision traces (if enabled)
- Provider latency metrics

### Key Functions
- Provider selection and fallback
- Secret management via keyring
- Shadow mode for debugging

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Keyring locked | No API access | Show unlock prompt |
| OpenAI quota exceeded | Provider unavailable | Fallback to Anthropic |
| All providers fail | Return local response | Fail-open mode |

### Owner
- **Team**: Backend
- **SLA**: 99.5% uptime (fail-open design)

---

## 3. Overlay Filesystem (nodomac)

### Responsibility
Logical-to-physical path resolution. Maintains manifests of file locations across nodes. Provides consistent namespace for artifacts.

### Inputs
- Logical paths (e.g., `overlay://denis_repo/src/main.py`)
- Physical file scans
- Manifest push requests

### Outputs
- Physical path resolution
- Manifest snapshots
- File metadata (size, mtime, sha256)

### Key Functions
- `resolve()` - Logical to physical mapping
- `scan()` - File discovery
- `index()` - Metadata storage
- `verify()` - Integrity checking
- `sync()` - Cross-node synchronization

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Manifest stale | Resolving may be wrong | Re-scan, regenerate manifest |
| SQLite locked | Write operations fail | Retry with backoff |
| File moved | Resolution fails | Update manifest |

### Owner
- **Team**: Infrastructure
- **SLA**: 99.9% uptime

---

## 4. AtlasLite (nodomac)

### Responsibility
Graph projection and metadata resolver. Maps runtime state to graph and provides queries for system intelligence.

### Inputs
- Overlay manifests
- Control room runs
- Chat CP traces

### Outputs
- Graph projections
- Metadata queries
- Health checks

### Key Functions
- `resolve()` - Metadata lookup
- `manifest` - File index management
- Graph projection

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Graph unavailable | Projection fails | Queue updates, retry |
| No data | Empty results | Return empty, log warning |

### Owner
- **Team**: Infrastructure
- **SLA**: 99.5% uptime

---

## 5. Control Room (nodomac)

### Responsibility
Orchestration engine for automated workflows. Manages step execution, leases, and heartbeats.

### Inputs
- Step definitions
- Configuration
- Lease acquisition requests

### Outputs
- Step execution results
- Artifacts
- Health state

### Key Functions
- `overlay_scan` - Scan overlay inventory
- `overlay_manifest_push` - Push manifest to nodomac
- `nodomac_scrape_cycle` - Scrape cycle
- `integration_smoke` - Run smoke tests
- `multi_node_test` - Test across nodes
- `pytest_run` - Run test suite

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Lease conflict | Step skipped | Retry later |
| Step timeout | Marked failed | Manual restart |
| Resource exhaustion | Steps queue | Wait for resources |

### Owner
- **Team**: DevOps
- **SLA**: 99% uptime

---

## 6. nodomac (Node)

### Responsibility
Host for Overlay, Control Room, AtlasLite, and Chat CP. Resource-constrained but stable.

### Inputs
- Local filesystem
- Network requests
- User interaction

### Outputs
- API responses
- Artifacts
- Graph updates

### Constraints
- macOS platform
- Limited resources (not a server)
- May be degraded under load

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| High CPU | Slow responses | Offload to nodo1 |
| Memory pressure | Process kills | Restart services |
| Network issues | Cannot reach nodo1/nodo2 | Work locally |

### Owner
- **Team**: Infrastructure
- **Note**: Use nodo1 for heavy computation

---

## 7. Graph (Neo4j on nodo1)

### Responsibility
Single source of truth for system topology, state, and decisions. Authoritative for routing policies and health.

### Inputs
- System state updates
- Decision traces
- Health checks
- Component registrations

### Outputs
- Provider chains
- Feature flags
- Topology
- Health status

### Key Queries
- `GET_PROVIDER_CHAIN` - Active providers in priority
- `GET_FEATURE_FLAGS` - Current feature flags
- `GET_NODE_TOPOLOGY` - Node addresses and capabilities
- `GET_HEALTH_STATUS` - Current health

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Unavailable | No reads/writes | Use cached values |
| Slow queries | High latency | Optimize, add indexes |
| Data corruption | Wrong decisions | Restore from backup |

### Owner
- **Team**: Data
- **SLA**: 99.9% uptime

---

## 8. Inference Gateway (nodo1)

### Responsibility
Multi-provider LLM routing with fallback. Routes inference requests to appropriate providers.

### Inputs
- User prompts
- Provider API keys
- Model configurations

### Outputs
- LLM completions
- Token usage metrics

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| All providers fail | No completion | Return error |
| Timeout | Request hangs | Apply timeout |
| Rate limit | Requests rejected | Backoff, retry |

### Owner
- **Team**: Backend
- **SLA**: 99.9% uptime

---

## 9. Memory System (nodo1)

### Responsibility
Multi-type memory storage and retrieval. Supports episodic, semantic, procedural, and working memory.

### Inputs
- User interactions
- System events
- Learned procedures

### Outputs
- Memory retrieval
- Consolidation
- Contradiction detection

### Key Functions
- Episodic: Conversation history
- Semantic: Concepts and relationships
- Procedural: Learned procedures
- Working: Active context

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Storage full | Cannot store | Delete old, warn |
| Query timeout | Slow retrieval | Return partial |

### Owner
- **Team**: Backend
- **SLA**: 99.5% uptime

---

## Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    USER                                              │
└─────────────────────────────────────┬───────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DENIS CORE (nodo1)                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │   Chat API  │  │   Memory    │  │  Metacog    │  │ Inference   │           │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │
│         │                 │                 │                 │                    │
│         └────────────────┴────────┬────────┴────────────────┘                    │
│                                   │                                              │
│                                   ▼                                              │
│                          ┌─────────────────┐                                     │
│                          │   NEO4J GRAPH   │◀──────────────────────────────────┐  │
│                          └─────────────────┘                                   │  │
└───────────────────────────────────────────────────────────────────────────────────┘  │
                                   │                                                │
                    ┌──────────────┼──────────────┐                                 │
                    ▼              ▼              ▼                                  │
          ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                        │
          │  CHAT CP    │ │   OVERLAY   │ │CONTROL ROOM│ (nodomac)              │
          │ (providers) │ │  (files)   │ │  (steps)   │                        │
          └─────────────┘ └─────────────┘ └─────────────┘                        │
                    │              │              │                                  │
                    ▼              ▼              ▼                                  │
          ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                        │
          │   KEYRING   │ │   SQLITE    │ │   SQLITE    │                        │
          │  (secrets)  │ │ (manifests) │ │   (runs)   │                        │
          └─────────────┘ └─────────────┘ └─────────────┘                        │
                                                                                   │
                    ┌────────────────────────────────────────────┐                │
                    │              NODO2 (compute)                │                │
                    │  ┌─────────┐  ┌─────────┐  ┌─────────┐  │                │
                    │  │   LLM   │  │   LLM   │  │   TTS   │  │                │
                    │  │ :8003   │  │ :8006   │  │ :8005   │  │                │
                    │  └─────────┘  └─────────┘  └─────────┘  │                │
                    └────────────────────────────────────────────┘                │
```

---

## Summary Table

| Subsystem | Owner | Input | Output | Failure Mode |
|-----------|-------|-------|--------|--------------|
| Denis Core | Backend | HTTP requests | Responses | Provider timeout |
| Chat CP | Backend | Chat requests | Chat responses | Fail-open |
| Overlay | Infra | Logical paths | Physical paths | Manifest stale |
| AtlasLite | Infra | Metadata | Graph data | Queue updates |
| Control Room | DevOps | Steps | Artifacts | Lease conflict |
| nodomac | Infra | Local ops | API responses | Resource exhaustion |
| Graph | Data | State/Decisions | Queries | Use cache |
| Inference | Backend | Prompts | Completions | Return error |
| Memory | Backend | Events | Retrieval | Storage full |
