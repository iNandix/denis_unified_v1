# Product Roadmap

## Overview

This roadmap outlines the development phases for the DENIS system, from core stabilization through to full IoT integration.

---

## Phase 1: Stabilize Core (Current)

**Goal:** Establish stable foundation with production-ready components.

### Objectives
- [x] Chat Control Plane with multi-provider routing
- [x] Overlay Filesystem with manifest management
- [x] Control Room with step automation
- [x] Keyring integration for secrets
- [x] Graph schema for system state

### Deliverables
- Chat CP (feature-flagged, ready for testing)
- Overlay API (:19999)
- AtlasLite API (:19998)
- Control Room steps
- Graph seed scripts

### Timeline
- Status: **In Progress**
- Target: Q1 2026

### Blockers
- None identified

---

## Phase 2: Facing/UX

**Goal:** Build user-facing interfaces and improve experience.

### Objectives
- [ ] Frontend application (nodo2-based)
- [ ] Web IDE interface
- [ ] Mobile-responsive dashboard
- [ ] Real-time status visualization

### Dependencies
- Chat CP must be stable
- Graph must have health data

### Deliverables
- Frontend build on nodo2
- Web dashboard
- Mobile UI

### Timeline
- Status: **Planned**
- Target: Q2 2026

### Blockers
- Frontend development resources

---

## Phase 3: IoT / Home Assistant Integration

**Goal:** Connect with physical world through Home Assistant.

### Objectives
- [ ] GPS event ingestion
- [ ] Camera motion events
- [ ] Sensor data collection
- [ ] Device state tracking
- [ ] Home Assistant API bridge

### Dependencies
- Graph schema v3 with Device nodes
- Decision trace for automation
- Control Room for automation workflows

### Deliverables
- HASS bridge service
- GPS tracking integration
- Camera event handling
- Sensor data pipeline
- Device management

### API Contracts (Future)

```python
# IoT Device Registration
POST /iot/device/register
{
  "device_id": "phone_001",
  "type": "gps",
  "name": "My Phone"
}

# GPS Event
POST /iot/gps/event
{
  "device_id": "phone_001",
  "lat": 37.7749,
  "lon": -122.4194,
  "accuracy": 10
}
```

### Timeline
- Status: **Planned**
- Target: Q3 2026

### Blockers
- Home Assistant instance configuration
- Network exposure (Tailscale)

---

## Phase 4: Intelligence Operative

**Goal:** Build autonomous operational capabilities.

### Objectives
- [ ] Predictive maintenance (device health)
- [ ] Automated response to IoT events
- [ ] Learning from decision patterns
- [ ] Context-aware routing
- [ ] Self-healing infrastructure

### Dependencies
- Decision traces collected
- Graph analytics operational
- IoT data flowing

### Deliverables
- ML models for prediction
- Automated action engine
- Self-healing triggers

### Timeline
- Status: **Future**
- Target: Q4 2026+

---

## Milestones

| Milestone | Phase | Target | Status |
|-----------|-------|--------|--------|
| M1: Graph Schema v3 | 1 | Feb 2026 | ✅ Complete |
| M2: Chat CP Stable | 1 | Mar 2026 | 🔄 In Progress |
| M3: Overlay/Atlas Ready | 1 | Mar 2026 | 🔄 In Progress |
| M4: Frontend Alpha | 2 | May 2026 | ⏳ Planned |
| M5: HASS Integration | 3 | Aug 2026 | ⏳ Planned |
| M6: Auto-Response | 4 | Dec 2026 | ⏳ Planned |

---

## Dependencies Graph

```
Phase 1 (Core)
├── Chat CP → Graph
├── Overlay → SQLite
├── Control Room → Graph
└── Keyring → OS

Phase 2 (UX)
├── Frontend → Backend APIs
├── Dashboard → Graph
└── Mobile → Backend APIs

Phase 3 (IoT)
├── HASS Bridge → Control Room
├── GPS Events → Graph
├── Camera Events → Graph
└── Sensors → Graph

Phase 4 (Intelligence)
├── ML Models → Decision Traces
├── Auto-Action → Control Room
└── Prediction → IoT Data
```

---

## Resource Requirements

| Resource | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|----------|---------|---------|---------|---------|
| Backend Dev | 1 | 1 | 1 | 1 |
| Frontend Dev | 0 | 2 | 1 | 1 |
| DevOps | 0.5 | 0.5 | 1 | 0.5 |
| ML Engineer | 0 | 0 | 0.5 | 1 |

---

## Risk Register

| Risk | Phase | Impact | Mitigation |
|------|-------|--------|------------|
| Frontend resources | 2 | High | Prioritize MVP features |
| HASS network | 3 | Medium | Use Tailscale |
| ML data volume | 4 | Medium | Start with simple models |

---

## Success Metrics

### Phase 1 (Core)
- Chat CP latency < 500ms (p95)
- Overlay scan completes < 30s
- Graph queries < 100ms

### Phase 2 (UX)
- Page load < 2s
- Mobile support for core features

### Phase 3 (IoT)
- GPS events < 1s latency
- Camera events processed in < 500ms
- 99% device uptime

### Phase 4 (Intelligence)
- Prediction accuracy > 80%
- Auto-response success > 90%
- Self-healing < 30s

---

## Next Steps

1. **Immediate** (This Sprint)
   - Test Chat CP with real providers
   - Seed graph with v3 schema
   - Document API contracts

2. **Short Term** (Next 2 Sprints)
   - Stabilize Chat CP
   - Build frontend skeleton
   - Start HASS bridge design

3. **Medium Term** (This Quarter)
   - Launch frontend
   - Integrate first IoT devices
   - Collect decision traces

4. **Long Term** (Next Year)
   - Deploy ML models
   - Achieve self-healing
   - Scale to production load
