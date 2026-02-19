"""HTTP debug endpoint for Event Bus v1 (dev-only)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.event_bus import get_event_store

router = APIRouter(prefix="/v1", tags=["events"])


@router.get("/events")
async def list_events(
    conversation_id: str = Query(..., min_length=1),
    after: int = Query(0, ge=0),
):
    try:
        events = get_event_store().query_after(
            conversation_id=str(conversation_id), after_event_id=int(after)
        )
        return JSONResponse(
            status_code=200,
            content={
                "conversation_id": conversation_id,
                "after": int(after),
                "count": len(events),
                "events": events,
            },
        )
    except Exception:
        # Fail-open: never 500 for debug.
        return JSONResponse(
            status_code=200,
            content={
                "conversation_id": conversation_id,
                "after": int(after),
                "count": 0,
                "events": [],
                "error": {"code": "degraded", "msg": "events_failed"},
            },
        )

