# Architecture Freeze v2

## Overview

Frozen snapshot of DENIS architecture as of February 2026.

---

## STABLE

### Core Services

| Component | Port | Node | Status |
|-----------|------|------|--------|
| Denis Unified API | 9999 | nodo1 | Production ready |
| Inference Gateway | - | nodo1 | Multi-provider fallback working |
| Memory System | - | nodo1 | All 4 types operational |
| Overlay API | 19999 | nodomac | Path resolution stable |
| Control Room | - | nodomac | Steps executing correctly |

### Contracts

- OpenAI-compatible API (/openai/v1/*)
- Chat completion API (/v1/chat)
- Memory APIs (/memory/*)
- Overlay resolve API (/overlay/resolve)

### Data Stores

- Neo4j (graph): Topology and state
- Redis (cache): Session and transient data
- SQLite (nodomac.db): Overlay and Control Room

---

## EXPERIMENTAL

### Feature-Flagged

| Feature | Flag | Status | Risk |
|---------|------|--------|------|
| Chat CP | DENIS_ENABLE_CHAT_CP | Tested, needs broader usage | Low |
| Shadow Mode | DENIS_CHAT_CP_SHADOW_MODE | Available for debugging | Low |
| Graph Writes | DENIS_CHAT_CP_GRAPH_WRITE | Collecting traces | Low |
| Decision Traces | - | Schema defined, writing enabled | Medium |

### Characteristics
- Behind feature flags
- Limited production testing
- May have edge cases

---

## MISSING

### Phase 1 - Critical

- [ ] Frontend application (SPA)
- [ ] Home Assistant bridge
- [ ] IoT device management
- [ ] Real-time sync between nodes
- [ ] Unified monitoring dashboard

### Phase 2 - Important

- [ ] GPS event pipeline
- [ ] Camera motion detection
- [ ] Sensor data aggregation
- [ ] Mobile app
- [ ] Voice interface

### Phase 3 - Future

- [ ] ML prediction models
- [ ] Automated responses
- [ ] Self-healing infrastructure
- [ ] Multi-user support
- [ ] Advanced analytics

---

## RISKS

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| 1 | nodomac resource constraints | High | Offload heavy tasks to nodo1 |
| 2 | No real-time sync | Medium | Manual refresh, queue updates |
| 3 | Chat CP untested at scale | Medium | Gradual rollout with flags |
| 4 | No monitoring dashboard | Medium | Log analysis, manual checks |
| 5 | Home Assistant not configured | High | Set up instance, Tailscale |
| 6 | Frontend framework not selected | Low | Evaluate options quickly |
| 7 | nodo2 GPU limited (4GB) | Medium | Use small models only |
| 8 | No automated backups | High | Implement backup strategy |
| 9 | Graph queries not optimized | Medium | Add indexes, cache |
| 10 | No rate limiting on IoT | Low | Implement per-device limits |

---

## Next Review

- **Frozen**: 2026-02-17
- **Review**: Before Facing Phase start
- **Status**: Stable foundation, ready for UX phase
