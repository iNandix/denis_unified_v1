import json

import pytest

from src.contracts.validation import (
    load_contract_v1_schema,
    validate_contract_v1,
)


def test_contract_v1_schema_file_loads():
    schema = load_contract_v1_schema()
    assert schema.get("$schema")
    assert schema.get("$defs")
    assert "DecisionTrace" in schema["$defs"]
    assert "DeviceEvent" in schema["$defs"]
    assert "CareAlert" in schema["$defs"]


@pytest.mark.parametrize(
    "payload, expected_kind",
    [
        (
            {
                "trace_id": "trace_abc123",
                "timestamp_ms": 1708000000000,
                "decision_type": "routing",
                "inputs": {"request_id": "req_001", "intent": "chat_completion"},
                "provider": "anthropic_chat",
                "fallback_chain": ["anthropic_chat", "openai_chat", "local_chat"],
                "error_class": None,
                "latency_ms": 450,
                "outcome": "success",
            },
            "DecisionTrace",
        ),
        (
            {
                "event_id": "evt_001",
                "device_id": "cam_front_door",
                "device_type": "camera",
                "event_type": "motion",
                "timestamp_ms": 1708000000000,
                "payload": {"confidence": 0.95},
                "processed": False,
            },
            "DeviceEvent",
        ),
        (
            {
                "alert_id": "alert_001",
                "severity": "warning",
                "subject": "Front Door Motion",
                "source": "camera_front_door",
                "message": "Motion detected at front door",
                "created_at": "2026-02-17T00:00:00Z",
                "acknowledged": False,
                "acknowledged_by": None,
            },
            "CareAlert",
        ),
    ],
)
def test_validate_contract_v1_ok(payload, expected_kind):
    result = validate_contract_v1(payload)
    assert result.ok is True
    assert result.kind == expected_kind


def test_validate_contract_v1_rejects_missing_required():
    result = validate_contract_v1({"trace_id": "x"})
    assert result.ok is False
    assert result.error and "candidates" in result.error

