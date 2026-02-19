# API Contracts Inventory

## Overview

This document catalogs all API contracts in the DENIS system, both implemented and planned. Each contract is documented with path, request/response schemas, and error handling.

---

## 1. Chat Control Plane APIs

### 1.1 Chat Completion

**Path:** `POST /v1/chat`  
**Server:** Denis Unified API (:9999) / Chat CP (:9999)  
**Feature Flag:** `DENIS_ENABLE_CHAT_CP`

**Request:**
```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "model": "gpt-4o-mini",
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false,
  "response_format": "text"
}
```

**Response:**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

**Errors:**
| Code | Description |
|------|-------------|
| 400 | Invalid request format |
| 401 | Missing API key |
| 429 | Rate limited |
| 500 | Server error |

---

### 1.2 Internal Chat CP (Debug)

**Path:** `POST /internal/chat_cp`  
**Server:** Chat CP (:9999)  
**Feature Flag:** `DENIS_ENABLE_CHAT_CP`

**Request:**
```json
{
  "messages": [{"role": "user", "content": "test"}],
  "response_format": "text"
}
```

**Response:**
```json
{
  "text": "Response from provider",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "latency_ms": 450,
  "trace_id": "req_123"
}
```

---

## 2. Control Room APIs

### 2.1 Execute Step

**Path:** `POST /control_room/execute`  
**Server:** Control Room (internal)  
**Authentication:** None (local)

**Request:**
```json
{
  "step_id": "overlay_scan",
  "run_id": "run_001",
  "config": {
    "batch": 200,
    "sleep_ms": 10
  }
}
```

**Response:**
```json
{
  "step_id": "overlay_scan",
  "status": "completed",
  "duration_ms": 12500,
  "artifacts": {
    "manifest.json": "/path/to/artifact"
  }
}
```

**Errors:**
| Code | Description |
|------|-------------|
| 404 | Step not found |
| 409 | Lease conflict |
| 500 | Step execution failed |

---

### 2.2 Get Step Status

**Path:** `GET /control_room/status/{run_id}`  
**Server:** Control Room (internal)

**Response:**
```json
{
  "run_id": "run_001",
  "steps": [
    {
      "step_id": "overlay_scan",
      "status": "completed",
      "started_at": "2026-02-17T00:00:00Z",
      "completed_at": "2026-02-17T00:00:12Z"
    }
  ]
}
```

---

## 3. Overlay / AtlasLite APIs

### 3.1 Resolve Path

**Path:** `POST /overlay/resolve`  
**Server:** Overlay API (:19999)

**Request:**
```json
{
  "logical_path": "overlay://denis_repo/src/main.py",
  "node_hint": "nodomac"
}
```

**Response:**
```json
{
  "logical_path": "overlay://denis_repo/src/main.py",
  "physical_path": "/home/jotah/projects/denis/src/main.py",
  "node_id": "nodomac",
  "confidence": "exact",
  "meta": {
    "size_bytes": 1234,
    "mtime_ms": 1708000000000,
    "sha256": "abc123..."
  },
  "provenance": "live"
}
```

**Errors:**
| Code | Description |
|------|-------------|
| 404 | Path not found |
| 400 | Invalid path format |

---

### 3.2 Get Manifest

**Path:** `GET /overlay/manifest/{root_id}`  
**Server:** Overlay API (:19999)

**Response:**
```json
{
  "manifest_id": "manifest_001",
  "root_id": "denis_repo",
  "generated_at_ms": 1708000000000,
  "stats": {
    "total_files": 1234,
    "total_bytes": 56789012,
    "new_files": 5,
    "updated_files": 10
  },
  "files": [
    {"rel_path": "src/main.py", "size_bytes": 1234}
  ],
  "payload_ref": "overlay/artifacts/snapshot_20260217.json"
}
```

---

### 3.3 Scan Step

**Path:** `POST /overlay/step/scan`  
**Server:** Overlay API (:19999)

**Request:**
```json
{
  "node_id": "nodomac",
  "root_id": "denis_repo"
}
```

**Response:**
```json
{
  "run_id": "scan_001",
  "status": "completed",
  "files_found": 1234,
  "artifacts": {
    "probes_report.json": "/path/to/report"
  }
}
```

---

### 3.4 AtlasLite Health

**Path:** `GET /atlaslite/health`  
**Server:** AtlasLite (:19998)

**Response:**
```json
{
  "status": "healthy",
  "db_path": "/home/jotah/nodomac/nodomac.db",
  "nodes_active": 3
}
```

---

## 4. Internal Booster Catalog APIs

### 4.1 List Boosters

**Path:** `GET /booster/catalog`  
**Server:** Booster Registry (internal)

**Response:**
```json
{
  "boosters": [
    {
      "id": "code_craft",
      "name": "Code Craft",
      "description": "AI code generation and refactoring",
      "enabled": true,
      "version": "0.1.0"
    },
    {
      "id": "rag_query",
      "name": "RAG Query",
      "description": "Retrieval-augmented generation",
      "enabled": true,
      "version": "0.1.0"
    }
  ]
}
```

---

### 4.2 Execute Booster

**Path:** `POST /booster/execute/{booster_id}`  
**Server:** Booster Registry (internal)

**Request:**
```json
{
  "input": "Explain this code",
  "context": {
    "file_path": "/path/to/file"
  }
}
```

**Response:**
```json
{
  "booster_id": "code_craft",
  "status": "completed",
  "output": "Generated explanation...",
  "latency_ms": 2500
}
```

---

## 5. IoT / Home Assistant APIs (Future)

### 5.1 GPS Event Ingest

**Path:** `POST /iot/gps/event`  
**Server:** Future HASS Bridge

**Request:**
```json
{
  "device_id": "phone_001",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "accuracy": 10,
  "timestamp": "2026-02-17T00:00:00Z"
}
```

**Response:**
```json
{
  "event_id": "gps_001",
  "status": "recorded",
  "device_state_updated": true
}
```

---

### 5.2 Sensor Data Ingest

**Path:** `POST /iot/sensor/data`  
**Server:** Future HASS Bridge

**Request:**
```json
{
  "sensor_id": "temperature_living",
  "value": 22.5,
  "unit": "celsius",
  "timestamp": "2026-02-17T00:00:00Z"
}
```

**Response:**
```json
{
  "sensor_id": "temperature_living",
  "status": "recorded"
}
```

---

### 5.3 Camera Event

**Path:** `POST /iot/camera/event`  
**Server:** Future HASS Bridge

**Request:**
```json
{
  "camera_id": "front_door",
  "event_type": "motion",
  "timestamp": "2026-02-17T00:00:00Z",
  "thumbnail_ref": "/cameras/motion_001.jpg"
}
```

**Response:**
```json
{
  "event_id": "cam_001",
  "status": "recorded",
  "triggered_actions": ["notify_mobile", "record_clip"]
}
```

---

## 6. Inference Gateway APIs

### 6.1 Model List

**Path:** `GET /v1/models`  
**Server:** Inference Gateway (nodo1)

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4o-mini",
      "object": "model",
      "created": 1700000000,
      "owned_by": "openai"
    }
  ]
}
```

---

### 6.2 Chat Completion (Legacy)

**Path:** `POST /v1/chat/completions`  
**Server:** OpenAI Compatible (:9999)

**Request:** Same as OpenAI format

**Response:** Same as OpenAI format

---

## 7. Metadata APIs

### 7.1 Metagraph Metrics

**Path:** `GET /metagraph/metrics`  
**Server:** Denis API (:9999)

**Response:**
```json
{
  "nodes": 150,
  "edges": 450,
  "last_updated": "2026-02-17T00:00:00Z"
}
```

---

### 7.2 Episodic Memory Query

**Path:** `POST /memory/episodic`  
**Server:** Memory API (internal)

**Request:**
```json
{
  "conversation_id": "conv_001",
  "limit": 10
}
```

**Response:**
```json
{
  "memories": [
    {
      "id": "mem_001",
      "content": "User asked about weather",
      "timestamp": "2026-02-17T00:00:00Z"
    }
  ]
}
```

---

## API Versioning

| Version | Status | Description |
|---------|--------|-------------|
| v1 | Stable | Core chat and inference APIs |
| v2 | Beta | Chat CP with multi-provider |
| v1 (OpenAI) | Stable | OpenAI-compatible endpoints |

---

## Error Response Standard

All APIs follow this error format:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "The request is invalid",
    "param": "messages",
    "type": "invalid_request_error"
  }
}
```

---

## Rate Limiting

| API | Limit | Window |
|-----|-------|--------|
| /v1/chat | 60 | minute |
| /v1/chat/completions | 60 | minute |
| /overlay/resolve | 100 | minute |
| /iot/* | 1000 | minute |
