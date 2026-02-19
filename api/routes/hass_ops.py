"""HASS entities endpoint for Care dashboard - P0 Implementation."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# P0: Stub válido con datos hardcodeados
# P1: Query real a HASS bridge
_STUB_ENTITIES = [
    {
        "entity_id": "camera.front_door",
        "domain": "camera",
        "state": "recording",
        "attributes": {"motion_detection": True, "resolution": "1080p"},
        "last_updated": "2026-02-18T14:25:00Z",
    },
    {
        "entity_id": "sensor.living_room_temp",
        "domain": "sensor",
        "state": "22.5",
        "attributes": {"unit": "celsius"},
        "last_updated": "2026-02-18T14:20:00Z",
    },
    {
        "entity_id": "binary_sensor.motion_living",
        "domain": "binary_sensor",
        "state": "off",
        "attributes": {},
        "last_updated": "2026-02-18T14:15:00Z",
    },
]


@router.get("/hass/entities")
async def list_hass_entities(request: Request) -> JSONResponse:
    """
    Returns list of Home Assistant entities.

    P0: Stub válido con datos hardcodeados
    P1: Query real a HASS via WebSocket/REST
    """
    start_time = time.time()
    try:
        # P0: Devolvemos stub
        response_data = {
            "entities": _STUB_ENTITIES,
            "count": int(len(_STUB_ENTITIES)),
            "hass_connected": False,  # P0: siempre false
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Escribir DecisionTrace (opcional, fail-open)
        try:
            from denis_unified_v1.chat_cp.graph_trace import maybe_write_decision_trace

            maybe_write_decision_trace(
                trace_id=str(request.state.trace_id)
                if hasattr(request.state, "trace_id")
                else None,
                endpoint="/hass/entities",
                decision_type="ops_query",
                outcome="success",
                latency_ms=int((time.time() - start_time) * 1000),
                context={
                    "sources_queried": ["stub"],
                    "hass_connected": False,
                    "entity_count": int(len(_STUB_ENTITIES)),
                },
            )
        except Exception:
            pass

        return JSONResponse(content=response_data)
    except Exception:
        # Fail-open: nunca 500
        return JSONResponse(
            status_code=200,
            content={
                "entities": [],
                "count": 0,
                "hass_connected": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": {"code": "degraded", "msg": "hass_entities_failed"},
            },
        )
