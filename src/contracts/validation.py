from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError


class DecisionTraceInputs(BaseModel):
    request_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)


class DecisionTraceV1(BaseModel):
    trace_id: str = Field(min_length=1)
    timestamp_ms: int = Field(ge=0)
    decision_type: Literal["routing"]
    inputs: DecisionTraceInputs
    provider: str = Field(min_length=1)
    fallback_chain: list[str]
    error_class: Optional[str] = None
    latency_ms: int = Field(ge=0)
    outcome: Literal["success", "failure", "fallback"]


class DeviceEventV1(BaseModel):
    event_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    device_type: Literal["camera", "sensor", "switch", "gps"]
    event_type: Literal["motion", "state_change", "reading", "location"]
    timestamp_ms: int = Field(ge=0)
    payload: dict[str, Any]
    processed: bool


class CareAlertV1(BaseModel):
    alert_id: str = Field(min_length=1)
    severity: Literal["info", "warning", "critical"]
    subject: str = Field(min_length=1)
    source: str = Field(min_length=1)
    message: str = Field(min_length=1)
    created_at: datetime
    acknowledged: bool
    acknowledged_by: Optional[str] = None


ContractV1 = Union[DecisionTraceV1, DeviceEventV1, CareAlertV1]


class ContractValidationResult(BaseModel):
    ok: bool
    kind: Optional[Literal["DecisionTrace", "DeviceEvent", "CareAlert"]] = None
    error: Optional[dict[str, Any]] = None


def _kind_for_model(model: BaseModel) -> str:
    if isinstance(model, DecisionTraceV1):
        return "DecisionTrace"
    if isinstance(model, DeviceEventV1):
        return "DeviceEvent"
    if isinstance(model, CareAlertV1):
        return "CareAlert"
    return "unknown"


def validate_contract_v1(payload: dict[str, Any]) -> ContractValidationResult:
    """Validate a payload against Control Plane Contracts v1.

    This is a pragmatic validator used in services/tests. It does not require
    jsonschema runtime deps.
    """
    errors: list[dict[str, Any]] = []
    for model_cls in (DecisionTraceV1, DeviceEventV1, CareAlertV1):
        try:
            model = model_cls.model_validate(payload)
            return ContractValidationResult(ok=True, kind=_kind_for_model(model))
        except ValidationError as exc:
            errors.append({"kind": model_cls.__name__, "errors": exc.errors()})
        except Exception as exc:
            errors.append({"kind": model_cls.__name__, "errors": [{"msg": str(exc)}]})
    return ContractValidationResult(ok=False, error={"candidates": errors})


def load_contract_v1_schema(repo_root: str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    schema_path = root / "docs" / "schema" / "contract_v1.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))

