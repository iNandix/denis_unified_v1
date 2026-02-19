import json
from pathlib import Path

import jsonschema


def _load_schema() -> dict:
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "docs" / "schema" / "telemetry_v1_1.json").read_text(encoding="utf-8"))


def test_telemetry_v1_1_schema_validates_ok_example():
    schema = _load_schema()
    layers = [
        {"layer_id": lid, "status": "unknown", "last_update_ts": None}
        for lid in [
            "L1_SENSORY",
            "L2_WORKING",
            "L3_EPISODIC",
            "L4_SEMANTIC",
            "L5_PROCEDURAL",
            "L6_EMOTIONAL",
            "L7_ATTENTION",
            "L8_SOCIAL",
            "L9_IDENTITY",
            "L10_RELATIONAL",
            "L11_VALUES",
            "L12_METACOG",
        ]
    ]
    payload = {
        "timestamp": "2026-02-17T00:00:00Z",
        "started_utc": "2026-02-17T00:00:00Z",
        "requests": {
            "total_1h": 10,
            "error_rate_1h": 0.0,
            "latency_p95_ms": 0,
            "by_path": {"/telemetry": 1},
            "by_status": {"200": 10},
            "last_request_utc": "2026-02-17T00:00:00Z",
        },
        "chat": {"total": 1, "blocked_hop_total": 0, "last_decisions": []},
        "async": {
            "async_enabled": True,
            "worker_seen": False,
            "materializer_stale": True,
            "last_materialize_ts": "",
            "blocked_mutations_count": 0,
            "queue_depth": None,
        },
        "providers": {},
        "graph": {
            "layers": layers,
            "summary": {
                "live_count": 0,
                "stale_count": 0,
                "unknown_count": 12,
                "integrity_degraded": True,
            },
        },
    }
    jsonschema.validate(payload, schema)


def test_telemetry_v1_1_schema_validates_degraded_example():
    schema = _load_schema()
    layers = [
        {"layer_id": lid, "status": "unknown", "last_update_ts": None}
        for lid in [
            "L1_SENSORY",
            "L2_WORKING",
            "L3_EPISODIC",
            "L4_SEMANTIC",
            "L5_PROCEDURAL",
            "L6_EMOTIONAL",
            "L7_ATTENTION",
            "L8_SOCIAL",
            "L9_IDENTITY",
            "L10_RELATIONAL",
            "L11_VALUES",
            "L12_METACOG",
        ]
    ]
    payload = {
        "timestamp": "2026-02-17T00:00:00Z",
        "started_utc": "",
        "requests": {
            "total_1h": 0,
            "error_rate_1h": 0.0,
            "latency_p95_ms": 0,
            "by_path": {},
            "by_status": {},
            "last_request_utc": "",
        },
        "chat": {"total": 0, "blocked_hop_total": 0, "last_decisions": []},
        "async": {
            "async_enabled": False,
            "worker_seen": False,
            "materializer_stale": True,
            "last_materialize_ts": "",
            "blocked_mutations_count": 0,
            "queue_depth": None,
        },
        "providers": {},
        "graph": {
            "layers": layers,
            "summary": {
                "live_count": 0,
                "stale_count": 0,
                "unknown_count": 12,
                "integrity_degraded": True,
            },
        },
        "error": {"code": "degraded", "msg": "telemetry_failed"},
    }
    jsonschema.validate(payload, schema)
