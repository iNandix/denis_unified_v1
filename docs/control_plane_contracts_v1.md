# Control Plane Contracts v1

## Overview

Minimal contracts for routing decisions, device events, and care alerts.

---

## 1. DecisionTrace

Routing decision audit log.

### Schema

```json
{
  "trace_id": "uuid",
  "timestamp_ms": "integer",
  "decision_type": "routing",
  "inputs": {
    "request_id": "string",
    "intent": "string"
  },
  "provider": "string",
  "fallback_chain": ["string"],
  "error_class": "string|null",
  "latency_ms": "integer",
  "outcome": "success|failure|fallback"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| trace_id | UUID | Yes | Unique identifier |
| timestamp_ms | Integer | Yes | Epoch milliseconds |
| decision_type | String | Yes | Always "routing" |
| provider | String | Yes | Selected provider |
| fallback_chain | Array | Yes | Options tried in order |
| error_class | String | No | Error type if failed |
| latency_ms | Integer | Yes | Decision time |
| outcome | Enum | Yes | Result status |

### Example

```json
{
  "trace_id": "trace_abc123",
  "timestamp_ms": 1708000000000,
  "decision_type": "routing",
  "inputs": {
    "request_id": "req_001",
    "intent": "chat_completion"
  },
  "provider": "anthropic_chat",
  "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
  "error_class": null,
  "latency_ms": 450,
  "outcome": "success"
}
```

---

## 2. DeviceEvent

IoT device state change or sensor reading.

### Schema

```json
{
  "event_id": "uuid",
  "device_id": "string",
  "device_type": "camera|sensor|switch|gps",
  "event_type": "motion|state_change|reading|location",
  "timestamp_ms": "integer",
  "payload": {},
  "processed": "boolean"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_id | UUID | Yes | Unique identifier |
| device_id | String | Yes | Device reference |
| device_type | Enum | Yes | Device category |
| event_type | Enum | Yes | Event classification |
| timestamp_ms | Integer | Yes | Epoch milliseconds |
| payload | Object | Yes | Event data |
| processed | Boolean | Yes | Whether handled |

### Examples

**Camera Motion:**
```json
{
  "event_id": "evt_001",
  "device_id": "cam_front_door",
  "device_type": "camera",
  "event_type": "motion",
  "timestamp_ms": 1708000000000,
  "payload": {
    "confidence": 0.95,
    "area": [100, 200, 300, 400]
  },
  "processed": false
}
```

**Sensor Reading:**
```json
{
  "event_id": "evt_002",
  "device_id": "temp_living",
  "device_type": "sensor",
  "event_type": "reading",
  "timestamp_ms": 1708000000000,
  "payload": {
    "value": 22.5,
    "unit": "celsius"
  },
  "processed": true
}
```

**GPS Location:**
```json
{
  "event_id": "evt_003",
  "device_id": "phone_jota",
  "device_type": "gps",
  "event_type": "location",
  "timestamp_ms": 1708000000000,
  "payload": {
    "lat": 37.7749,
    "lon": -122.4194,
    "accuracy": 10
  },
  "processed": true
}
```

---

## 3. CareAlert

Notification for care-related events.

### Schema

```json
{
  "alert_id": "uuid",
  "severity": "info|warning|critical",
  "subject": "string",
  "source": "string",
  "message": "string",
  "created_at": "iso8601",
  "acknowledged": "boolean",
  "acknowledged_by": "string|null"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| alert_id | UUID | Yes | Unique identifier |
| severity | Enum | Yes | Alert level |
| subject | String | Yes | What/who affected |
| source | String | Yes | Trigger source |
| message | String | Yes | Human description |
| created_at | ISO8601 | Yes | Timestamp |
| acknowledged | Boolean | Yes | Seen status |
| acknowledged_by | String | No | User ID |

### Severity Levels

| Level | Description | Example |
|-------|-------------|---------|
| info | Informational | Device came online |
| warning | Attention needed | Motion detected |
| critical | Immediate action | Device offline > 1hr |

### Examples

**Warning:**
```json
{
  "alert_id": "alert_001",
  "severity": "warning",
  "subject": "Front Door Motion",
  "source": "camera_front_door",
  "message": "Motion detected at front door",
  "created_at": "2026-02-17T00:00:00Z",
  "acknowledged": false,
  "acknowledged_by": null
}
```

**Critical:**
```json
{
  "alert_id": "alert_002",
  "severity": "critical",
  "subject": "Elderly Person",
  "source": "motion_sensor_bedroom",
  "message": "No motion detected for 12 hours",
  "created_at": "2026-02-17T00:00:00Z",
  "acknowledged": true,
  "acknowledged_by": "jota"
}
```

---

## Validation Rules

### DecisionTrace
- `trace_id` must be valid UUID
- `timestamp_ms` must be positive integer
- `outcome` must be one of: success, failure, fallback
- `latency_ms` must be >= 0

### DeviceEvent
- `event_id` must be valid UUID
- `timestamp_ms` must be positive integer
- `device_type` must be one of: camera, sensor, switch, gps
- `event_type` must be one of: motion, state_change, reading, location

### CareAlert
- `alert_id` must be valid UUID
- `severity` must be one of: info, warning, critical
- `created_at` must be valid ISO8601
- `acknowledged` must be boolean

---

## Graph Storage

All contracts stored in Neo4j:

```cypher
// DecisionTrace as Decision node
CREATE (d:Decision {id: trace_id, ...})

// DeviceEvent as Event node
CREATE (e:Event {id: event_id, ...})

// CareAlert as Alert node
CREATE (a:Alert {id: alert_id, ...})
```

---

## Version

- **Version**: 1.0
- **Date**: 2026-02-17
- **Status**: Stable
