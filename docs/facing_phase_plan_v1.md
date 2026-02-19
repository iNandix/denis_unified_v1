# Facing Phase Plan v1

## Overview

Scoped plan for user-facing layer: Frontend, UX, Home Assistant, IoT.

---

## Scope

1. SPA on nodo2
2. Denis API endpoints
3. HASS bridge
4. Denis personality layer

---

## 1. SPA (nodo2)

### Views

| View | Data | Endpoints |
|------|------|-----------|
| Chat | Messages | POST /v1/chat |
| Dashboard | Status | GET /status |
| Devices | IoT list | GET /devices |
| Settings | Config | GET/POST /config |

### Components

- Chat interface (React)
- Device cards
- Alert panel
- Settings form

---

## 2. Denis API (nodo1)

### Endpoints Required

| Method | Path | Purpose |
|--------|------|---------|
| POST | /v1/chat | Chat completion |
| GET | /status | System health |
| GET | /devices | List devices |
| POST | /command | Execute command |
| GET | /alerts | Active alerts |
| POST | /alerts/:id/ack | Acknowledge alert |

---

## 3. HASS Bridge

### Mode

**Push + Pull:**
- Pull: Query HASS REST API
- Push: WebSocket for real-time events

### Data to Graph

| Source | Graph Node | Frequency |
|--------|------------|-----------|
| GPS | GeoPoint | Every 30s |
| Camera | Event | On motion |
| Sensor | Sensor.value | Every 60s |
| State changes | Event | Real-time |

---

## 4. Denis Personality

### Tone

- Friendly but professional
- Proactive when helpful
- Context-aware
- Consistent across channels

### States

| State | Behavior |
|-------|----------|
| Idle | Quiet, listens |
| Active | Responsive, helpful |
| Alert | Urgent notifications |
| Reflective | Shows memory |

### Memory Visible

- Recent conversations
- User preferences
- Device states
- Location context

---

## Checklist

### Sprint 1 - Foundation

- [ ] Select frontend framework (React/Vue)
- [ ] Set up build pipeline on nodo2
- [ ] Create API endpoint stubs
- [ ] HASS bridge skeleton

### Sprint 2 - Chat & Dashboard

- [ ] Chat UI component
- [ ] Message history
- [ ] Dashboard layout
- [ ] Status endpoint

### Sprint 3 - IoT Integration

- [ ] HASS WebSocket client
- [ ] Device list endpoint
- [ ] Device cards UI
- [ ] Graph writes for events

### Sprint 4 - Personality & Polish

- [ ] Denis tone implementation
- [ ] Memory display
- [ ] Alert panel
- [ ] Mobile responsive

---

## Dependencies

### Blocking

| Dependency | For | Status |
|------------|-----|--------|
| Chat CP stable | Chat UI | ✅ Ready |
| Graph v3 | Device storage | ✅ Ready |
| HASS instance | IoT data | ⏳ Need setup |

### Nice to Have

- Tailscale configured
- nodo2 GPU optimized
- CDN for static assets

---

## Risks

| Risk | Mitigation |
|------|------------|
| nodo2 limited resources | Optimize bundle size |
| HASS not available | Mock data for development |
| Real-time complexity | Start with polling |

---

## Success Criteria

- [ ] SPA loads < 2s
- [ ] Chat < 500ms response
- [ ] Device updates < 1s
- [ ] Mobile functional

---

## Next Steps

1. Select frontend framework
2. Set up nodo2 build environment
3. Create HASS bridge
4. Implement chat UI
5. Test with real devices

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Sprint 1 | 2 weeks | Foundation + build |
| Sprint 2 | 2 weeks | Chat + Dashboard |
| Sprint 3 | 2 weeks | IoT integration |
| Sprint 4 | 2 weeks | Personality + polish |

**Total: 8 weeks**

---

## Ready to Start

- ✅ Architecture documented
- ✅ Contracts defined
- ✅ Graph schema ready
- ⏳ Frontend framework selection needed
