# Async Operations (async_min) — P1 Ready

`async_min` is non-critical. `/chat` must never depend on Redis/Celery.

## Env
- `ASYNC_ENABLED=1` enables Celery dispatch (still fail-open).
- `ASYNC_REDIS_URL=redis://127.0.0.1:6379/0` (defaults to `REDIS_URL`).
- `DENIS_ARTIFACTS_DIR=...` optional (defaults to `./artifacts`).
- `DENIS_BASE_URL=http://127.0.0.1:9999` base URL for Ops endpoints (`/health`, `/telemetry`).

## Start Worker (non-blocking demo)
```bash
timeout 5s env ASYNC_ENABLED=1 celery -A denis_unified_v1.async_min.celery_main:app worker -Q denis:async_min -l info
```

## Dispatch Job
```bash
timeout 20s env ASYNC_ENABLED=1 python scripts/async_snapshot_hass_demo.py
```

## Artifacts Location
Artifacts are written under:
- `artifacts/control_room/<run_id>/...` (or `DENIS_ARTIFACTS_DIR`)

## Validate Endpoints (base URL aware)
```bash
export DENIS_BASE_URL="${DENIS_BASE_URL:-http://127.0.0.1:9999}"
curl -sS -m 2 "$DENIS_BASE_URL/health" | jq '.async'
curl -sS -m 2 "$DENIS_BASE_URL/telemetry" | jq '.async'
```

For a robust validation (prints `UNREACHABLE` and exits 0 if no server is running):
```bash
DENIS_BASE_URL="${DENIS_BASE_URL:-http://127.0.0.1:9999}" ./scripts/validate_async_min.sh
```

## /telemetry Contract v1.1
Required keys for frontend/nodo2:
- `.async.async_enabled`
- `.async.worker_seen`
- `.async.materializer_stale`
- `.async.last_materialize_ts`
- `.async.blocked_mutations_count`
- `.async.queue_depth` (int|null)
- `.graph.layers[]` (12 layers, each `live|stale|unknown`)
- `.graph.summary` (counts + `integrity_degraded`)

### Graph Layer Freshness (MVP)
`/telemetry.graph` exposes freshness for 12 canonical neurolayers:
- `status=live`: last update is within `DENIS_GRAPH_LAYER_STALE_MS` (default 5 minutes).
- `status=stale`: last update is older than the threshold.
- `status=unknown`: no timestamp or Graph unavailable.

If Neo4j is not reachable or secrets are missing, `/telemetry` still returns 200 with all layers `unknown` and `graph.summary.integrity_degraded=true` (fail-open).

### Example: Telemetry OK (stale)
```json
{
  "timestamp": "2026-02-17T00:00:00Z",
  "started_utc": "2026-02-17T00:00:00Z",
  "requests": {
    "total_1h": 10,
    "error_rate_1h": 0.0,
    "latency_p95_ms": 0,
    "by_path": {"/telemetry": 1},
    "by_status": {"200": 10},
    "last_request_utc": "2026-02-17T00:00:00Z"
  },
  "chat": {"total": 1, "blocked_hop_total": 0, "last_decisions": []},
  "async": {
    "async_enabled": true,
    "worker_seen": false,
    "materializer_stale": true,
    "last_materialize_ts": "",
    "blocked_mutations_count": 0,
    "queue_depth": null
  },
  "graph": {
    "layers": [
      {"layer_id":"L1_SENSORY","status":"unknown","last_update_ts":null},
      {"layer_id":"L2_WORKING","status":"unknown","last_update_ts":null},
      {"layer_id":"L3_EPISODIC","status":"unknown","last_update_ts":null},
      {"layer_id":"L4_SEMANTIC","status":"unknown","last_update_ts":null},
      {"layer_id":"L5_PROCEDURAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L6_EMOTIONAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L7_ATTENTION","status":"unknown","last_update_ts":null},
      {"layer_id":"L8_SOCIAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L9_IDENTITY","status":"unknown","last_update_ts":null},
      {"layer_id":"L10_RELATIONAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L11_VALUES","status":"unknown","last_update_ts":null},
      {"layer_id":"L12_METACOG","status":"unknown","last_update_ts":null}
    ],
    "summary": {
      "live_count": 0,
      "stale_count": 0,
      "unknown_count": 12,
      "integrity_degraded": true
    }
  }
}
```

### Example: Telemetry Degraded
```json
{
  "timestamp": "2026-02-17T00:00:00Z",
  "started_utc": "",
  "requests": {
    "total_1h": 0,
    "error_rate_1h": 0.0,
    "latency_p95_ms": 0,
    "by_path": {},
    "by_status": {},
    "last_request_utc": ""
  },
  "chat": {"total": 0, "blocked_hop_total": 0, "last_decisions": []},
  "async": {
    "async_enabled": false,
    "worker_seen": false,
    "materializer_stale": true,
    "last_materialize_ts": "",
    "blocked_mutations_count": 0,
    "queue_depth": null
  },
  "graph": {
    "layers": [
      {"layer_id":"L1_SENSORY","status":"unknown","last_update_ts":null},
      {"layer_id":"L2_WORKING","status":"unknown","last_update_ts":null},
      {"layer_id":"L3_EPISODIC","status":"unknown","last_update_ts":null},
      {"layer_id":"L4_SEMANTIC","status":"unknown","last_update_ts":null},
      {"layer_id":"L5_PROCEDURAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L6_EMOTIONAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L7_ATTENTION","status":"unknown","last_update_ts":null},
      {"layer_id":"L8_SOCIAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L9_IDENTITY","status":"unknown","last_update_ts":null},
      {"layer_id":"L10_RELATIONAL","status":"unknown","last_update_ts":null},
      {"layer_id":"L11_VALUES","status":"unknown","last_update_ts":null},
      {"layer_id":"L12_METACOG","status":"unknown","last_update_ts":null}
    ],
    "summary": {
      "live_count": 0,
      "stale_count": 0,
      "unknown_count": 12,
      "integrity_degraded": true
    }
  },
  "error": {"code": "degraded", "msg": "telemetry_failed"}
}
```

## Troubleshooting
- Redis down / worker missing: `/telemetry.async.materializer_stale=true` and `queue_depth=null`.
- Broker dispatch is guarded with a fast Redis `PING` (socket timeouts ~200ms). If unreachable, job runs sync and still writes artifacts.
- Common: server not running / wrong port
  - `export DENIS_BASE_URL=http://127.0.0.1:9999` (or your actual host:port)
  - `curl -sS -m 2 "$DENIS_BASE_URL/health"`
