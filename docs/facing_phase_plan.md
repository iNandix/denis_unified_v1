# Facing Phase Plan

## Overview

This document scopes the next phase of development: building the user-facing layer and integrating with the physical world through Home Assistant.

---

## Phase Objectives

1. **Frontend Refactor** - Modern, responsive UI
2. **UX/Personality Layer** - Denis as the main interface
3. **Home Assistant Integration** - IoT device bridge
4. **Camera/GPS/Sensor Ingestion** - Physical world data

---

## 1. Frontend Refactor

### Current State
- No dedicated frontend
- API endpoints exist but no UI
- nodo2 has compute capacity for frontend build

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER                                  │
│                      (Browser)                               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (nodo2)                         │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                 SPA (React/Vue)                       │  │
│  │  - Chat interface                                    │  │
│  │  - Dashboard                                        │  │
│  │  - Device management                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                   API CLIENT                          │  │
│  │  - Denis API (:9999)                                 │  │
│  │  - Chat CP (:9999)                                   │  │
│  │  - Overlay (:19999)                                  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Interface Requirements

| Interface | Technology | Purpose |
|-----------|------------|---------|
| Chat UI | React | Main interaction |
| Dashboard | React | System status |
| Device Manager | React | IoT devices |
| Settings | React | Configuration |

### Dependencies

- Chat CP must be stable
- API contracts finalized
- Auth system (if needed)

---

## 2. UX/Personality Layer

### Concept
Denis becomes the unified interface for all system interactions.

### Capabilities

| Capability | Input | Output | Example |
|------------|-------|--------|---------|
| Natural Language | "Turn on lights" | Action confirmation | "Lights are on" |
| Context Awareness | User location | Relevant info | "Welcome home" |
| Proactive | Time of day | Suggestions | "It's cold outside" |
| Personalization | User preferences | Custom responses | "Good evening, Jota" |

### Personality Traits

- Friendly but professional
- Proactive but not intrusive
- Consistent across devices
- Adapts to context

### Implementation

```
User Input → Chat CP → Intent Recognition → Action Execution → Response
                ↓
            Graph (context, history, preferences)
```

---

## 3. Home Assistant Integration

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  HOME ASSISTANT (HASS)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   GPS   │  │ Cameras  │  │ Sensors  │  │  Lights  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │             │         │
│       └─────────────┴──────┬──────┴─────────────┘         │
│                            │                              │
│                            ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                  HASS BRIDGE                           │  │
│  │  - WebSocket events                                    │  │
│  │  - State subscriptions                                 │  │
│  │  - Command execution                                   │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     DENIS GRAPH                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Device nodes  |  Event nodes  |  State nodes      │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Interface: HASS Bridge

**WebSocket Connection**
```javascript
// Subscribe to events
ws.subscribe('state_changed', (event) => {
  const device_id = event.data.entity_id;
  const new_state = event.data.new_state.state;
  
  // Write to graph
  graph.updateDeviceState(device_id, new_state);
});
```

### Data Flow

| Source | Event | Graph Update | Action |
|--------|-------|--------------|--------|
| GPS | location_update | Device.position | Notify user |
| Camera | motion_detected | Event.trigger | Record clip |
| Sensor | temperature | Device.state | Alert if high |
| Light | state_change | Device.state | Log change |

---

## 4. Camera/GPS/Sensor Ingestion

### GPS Tracking

**Event Schema:**
```json
{
  "device_id": "phone_001",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "accuracy": 10,
  "timestamp": "2026-02-17T00:00:00Z"
}
```

**Graph Storage:**
```cypher
MATCH (d:Device {id: 'phone_001'})
CREATE (d)-[:HAS_POSITION]->(p:Position {
  lat: 37.7749,
  lon: -122.4194,
  timestamp: datetime()
})
```

### Camera Events

**Event Schema:**
```json
{
  "camera_id": "front_door",
  "event_type": "motion",
  "confidence": 0.95,
  "thumbnail": "/cameras/motion_001.jpg",
  "timestamp": "2026-02-17T00:00:00Z"
}
```

**Graph Storage:**
```cypher
CREATE (e:CameraEvent {
  id: 'cam_001',
  camera_id: 'front_door',
  type: 'motion',
  confidence: 0.95,
  timestamp: datetime()
})
```

### Sensor Data

**Event Schema:**
```json
{
  "sensor_id": "temp_living",
  "type": "temperature",
  "value": 22.5,
  "unit": "celsius",
  "timestamp": "2026-02-17T00:00:00Z"
}
```

**Graph Storage:**
```cypher
MATCH (s:Sensor {id: 'temp_living'})
SET s.current_value = 22.5,
    s.last_updated = datetime()
```

---

## Contracts Summary

### Frontend → Backend

| Endpoint | Purpose | Payload |
|----------|---------|---------|
| GET /v1/chat | Chat completion | `{messages, model}` |
| GET /status | System health | - |
| GET /devices | List devices | - |
| POST /command | Execute command | `{device, action}` |

### HASS → Graph

| Event Type | Data | Frequency |
|------------|------|-----------|
| state_changed | entity_id, state | Real-time |
| location_update | lat, lon | Every 30s |
| motion_detected | camera_id, confidence | On trigger |
| sensor_update | sensor_id, value | Every 60s |

---

## Dependencies

### Phase 1 → Phase 2

| Phase 1 Item | Required For | Why |
|--------------|--------------|-----|
| Chat CP stable | Frontend chat | Main interaction |
| Graph v3 | Device state | Storage |
| API contracts | Frontend dev | Interface |

### External Dependencies

| Dependency | Required For | Status |
|------------|--------------|--------|
| Home Assistant instance | IoT integration | Not configured |
| Tailscale network | Cross-node access | ✅ Exists |
| Frontend framework | UI build | Not selected |

---

## Implementation Phases

### Sprint 1: Frontend Skeleton

- [ ] Select frontend framework
- [ ] Set up build pipeline on nodo2
- [ ] Create basic layout
- [ ] Connect to Denis API

### Sprint 2: Chat Interface

- [ ] Chat UI component
- [ ] Message history
- [ ] Streaming responses
- [ ] Mobile responsive

### Sprint 3: HASS Bridge

- [ ] WebSocket client
- [ ] Event handlers
- [ ] Graph writes
- [ ] Device registration

### Sprint 4: Device Management

- [ ] Device list UI
- [ ] State visualization
- [ ] Command interface
- [ ] Location tracking

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| nodo2 limited GPU | Frontend build slow | Optimize, cache |
| HASS network exposure | Security | Use Tailscale |
| Real-time sync complexity | Latency | Batch updates |
| UX complexity | Poor adoption | Start simple |

---

## Success Criteria

- [ ] Frontend loads in < 2s
- [ ] Chat responds in < 500ms
- [ ] GPS updates every 30s
- [ ] Camera events in < 1s
- [ ] 99% device uptime tracking

---

## Next Steps

1. **Immediate** (This Sprint)
   - Select frontend framework
   - Set up nodo2 build environment
   - Create HASS bridge design doc

2. **Short Term** (Next 2 Sprints)
   - Build frontend skeleton
   - Implement HASS bridge
   - Test device ingestion

3. **Medium Term** (This Quarter)
   - Full frontend feature set
   - Complete IoT integration
   - UX polish

---

## Interface Summary

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   USER      │      │  FRONTEND   │      │   BACKEND   │
└──────┬──────┘      └──────┬──────┘      └──────┬──────┘
       │                    │                    │
       │ Chat               │ API calls          │
       ▼                    ▼                    ▼
┌───────────────────────────────────────────────────────┐
│                      DENIS GRAPH                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Device  │  │  Person  │  │  Event   │           │
│  └──────────┘  └──────────┘  └──────────┘           │
└───────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────┐
│                 HOME ASSISTANT                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │    GPS   │  │  Camera  │  │  Sensor  │           │
│  └──────────┘  └──────────┘  └──────────┘           │
└───────────────────────────────────────────────────────┘
```

---

## Summary

The Facing Phase transforms DENIS from a backend system into a user-facing platform with IoT integration.

**Key interfaces:**
- Frontend: React/Vue SPA on nodo2
- HASS Bridge: WebSocket events → Graph
- UX Layer: Chat CP with personality
- IoT: GPS, cameras, sensors via Home Assistant

**Dependencies:**
- Chat CP stable
- Graph v3 with Device/Event nodes
- Home Assistant instance
- Frontend framework selection
