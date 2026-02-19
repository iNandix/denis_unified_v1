# Architecture Freeze v1

## Overview

This document freezes the current state of the DENIS architecture as of February 2026. It provides a snapshot of what exists, what is stable, what is experimental, and what is planned but not yet implemented.

---

## Component Status Matrix

| Component | Status | Location | Dependencies | Notes |
|-----------|--------|----------|-------------|-------|
| **Chat CP** | Feature-Flagged | nodomac/chat_cp | Keyring, OpenAI, Anthropic | Ready for testing |
| **Overlay FS** | Active | nodomac/overlay | SQLite | Stable |
| **Control Room** | Active | nodomac/control_room | SQLite, Overlay | Stable |
| **AtlasLite** | Active | nodomac | SQLite | Stable |
| **Inference Gateway** | Active | nodo1/inference | Neo4j, Redis, Providers | Stable |
| **Denis API** | Active | nodo1 | Neo4j, Redis | Stable |
| **Graph Schema v3** | Implemented | Neo4j | - | Seeded |
| **Keyring Integration** | Implemented | nodomac | OS Keyring | Secrets management |
| **Lease Manager** | Active | nodomac/control_room/hardening | SQLite | Step locking |
| **Heartbeat Manager** | Active | nodomac/control_room/hardening | SQLite | Node liveness |

---

## What Exists

### Core Services

| Service | Port | Protocol | Node |
|---------|------|----------|------|
| Denis Unified API | 9999 | HTTP | nodo1 |
| Chat CP API | 9999 | HTTP | nodomac |
| AtlasLite API | 19998 | HTTP | nodomac |
| Overlay API | 19999 | HTTP | nodomac |
| LLM Server (qwen) | 8003 | HTTP | nodo2 |
| LLM Server (smollm) | 8006 | HTTP | nodo2 |
| LLM Server (safety) | 8007 | HTTP | nodo2 |
| LLM Server (intent) | 8008 | HTTP | nodo2 |
| TTS (Piper) | 8005 | HTTP | nodo2 |

### Data Stores

| Store | Technology | Location | Purpose |
|-------|------------|----------|---------|
| Graph | Neo4j | nodo1:7687 | Topology, state, decisions |
| Cache | Redis | nodo1:6379 | Transient caching |
| Operational | SQLite | nodomac.db | Overlay, Control Room |
| Artifacts | Filesystem | nodomac/var | Snapshots, reports |

### APIs

| API | Status | Version |
|-----|--------|---------|
| /v1/chat | Stable | v1 |
| /openai/v1/* | Stable | OpenAI-compatible |
| /atlaslite/* | Stable | v1 |
| /overlay/* | Stable | v1 |
| /control_room/* | Stable | v1 |
| /internal/chat_cp | Feature-Flagged | v1 |

---

## What Is Stable

### Production-Ready

1. **Inference Gateway** - Multi-provider routing with fallback
2. **Denis Unified API** - Main API surface
3. **OpenAI Compatible Endpoints** - Standard OpenAI client compatibility
4. **Memory System** - Episodic, semantic, procedural, working memory
5. **Metacognitive System** - Self-model and reflection
6. **Overlay Filesystem** - Logical-to-physical path resolution
7. **Control Room Steps** - Scan, index, verify, push automation

### Characteristics of Stable Components

- ✅ Has automated tests
- ✅ Has error handling
- ✅ Has defined contracts
- ✅ Has documentation
- ✅ Has been run in production

---

## What Is Experimental

### Feature-Flagged

1. **Chat CP Layer**
   - Flag: `DENIS_ENABLE_CHAT_CP`
   - Status: Testing in progress
   - Known Issues: None critical
   - Next: Enable for broader testing

2. **Decision Traces**
   - Flag: `DENIS_CHAT_CP_GRAPH_WRITE`
   - Status: Collecting data
   - Known Issues: None
   - Next: Build analytics

3. **Shadow Mode**
   - Flag: `DENIS_CHAT_CP_SHADOW_MODE`
   - Status: Available for testing
   - Known Issues: None
   - Next: Use for debugging

### Characteristics of Experimental

- ⚠️ May have limited testing
- ⚠️ May have incomplete documentation
- ⚠️ May have edge cases not handled
- ⚠️ Requires feature flag to enable

---

## What Is Planned but Missing

### Not Yet Implemented

| Component | Priority | Dependencies | Status |
|-----------|----------|--------------|--------|
| Frontend Application | P1 | Chat CP stable | Not started |
| Home Assistant Bridge | P2 | Graph v3 | Design done |
| IoT Device Management | P2 | HASS Bridge | Not started |
| GPS Event Ingestion | P2 | HASS Bridge | Not started |
| Camera Event Processing | P2 | HASS Bridge | Not started |
| Sensor Data Pipeline | P2 | HASS Bridge | Not started |
| ML Prediction Models | P3 | Decision traces | Not started |
| Self-Healing Infrastructure | P3 | ML Models | Not started |

### Gaps in Current Implementation

1. **Graph Write Path** - Events written but queries not optimized
2. **Multi-Node Sync** - No real-time sync between nodomac and nodo1
3. **Monitoring Dashboard** - No unified monitoring
4. **Alerting** - No alerting system
5. **Rate Limiting** - Basic implementation, needs tuning

---

## System Boundaries

### nodomac (Resource Constrained)

- **Role**: Overlay, Control Room, AtlasLite, Chat CP
- **Constraint**: macOS, limited resources
- **Status**: Running but may be degraded under load
- **Mitigation**: Use nodo1 for heavy computation

### nodo1 (Primary Server)

- **Role**: Denis Core, Inference, Graph, Redis
- **Constraint**: None known
- **Status**: Stable

### nodo2 (Compute Node)

- **Role**: LLM Servers, TTS
- **Constraint**: 4GB VRAM (1050 Ti)
- **Status**: Stable
- **Note**: Good for small models only

---

## Known Issues

| Issue | Severity | Workaround |
|-------|----------|------------|
| nodomac resource constraints | Medium | Offload to nodo1 |
| No real-time sync | Low | Manual refresh |
| Limited testing on Chat CP | Medium | Enable gradual rollout |
| No monitoring dashboard | Low | Check logs manually |

---

## Version Summary

| Component | Version | Schema |
|-----------|---------|--------|
| Denis Unified | 3.1-canonical | - |
| Chat CP | 0.1.0 | - |
| Overlay API | 0.1.0 | - |
| Graph Schema | v3 | Stable |
| API Contracts | v1 | Stable |

---

## Migration Path

To move from experimental to stable:

### Chat CP

1. ✅ Feature flag implemented
2. 🔄 Enable for internal testing
3. 🔄 Collect metrics
4. 🔄 Fix issues found
5. ⏳ Enable by default

### Decision Traces

1. ✅ Schema defined
2. ✅ Writing enabled
3. 🔄 Build analytics
4. 🔄 Optimize queries
5. ⏳ Production ready

---

## Freeze Sign-off

- **Frozen on**: 2026-02-17
- **Status**: Stable foundation, experimental features flag-gated
- **Next Review**: Before Facing Phase start
