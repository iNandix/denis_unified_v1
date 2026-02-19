"""Graph read endpoints for cockpit UI (fail-open).

Graph is SSoT, but UI must remain non-critical. These endpoints never raise 500:
- If Graph is unavailable, return warning + null payload.

NOTE: This is read-only and intentionally returns small state only.
No prompts/snippets/content should be stored or returned here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


router = APIRouter(prefix="/graph", tags=["graph"])


def _graph_driver():
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        return gc._get_driver()
    except Exception:
        return None


def _safe_node(n: Any) -> dict[str, Any]:
    # Neo4j nodes are dict-like; keep shallow props only.
    try:
        return dict(n)
    except Exception:
        return {}


@router.get("/intent/{intent_id}")
async def get_intent(intent_id: str, request: Request) -> JSONResponse:
    driver = _graph_driver()
    if driver is None:
        return JSONResponse(content={"id": intent_id, "intent": None, "warning": "graph_unavailable"}, status_code=200)

    intent: dict[str, Any] | None = None
    warning: str | None = None
    try:
        with driver.session() as session:
            res = session.run("MATCH (i:Intent {id: $id}) RETURN i LIMIT 1", id=str(intent_id))
            rec = res.single()
            if rec and rec.get("i") is not None:
                intent = _safe_node(rec["i"])
    except Exception:
        warning = "graph_query_failed"

    out: dict[str, Any] = {"id": intent_id, "intent": intent}
    if warning:
        out["warning"] = warning
    return JSONResponse(content=out, status_code=200)


@router.get("/plan/{plan_id}")
async def get_plan(plan_id: str, request: Request) -> JSONResponse:
    driver = _graph_driver()
    if driver is None:
        return JSONResponse(content={"id": plan_id, "plan": None, "warning": "graph_unavailable"}, status_code=200)

    plan: dict[str, Any] | None = None
    warning: str | None = None
    try:
        with driver.session() as session:
            res = session.run("MATCH (p:Plan {id: $id}) RETURN p LIMIT 1", id=str(plan_id))
            rec = res.single()
            if rec and rec.get("p") is not None:
                plan = _safe_node(rec["p"])
    except Exception:
        warning = "graph_query_failed"

    out: dict[str, Any] = {"id": plan_id, "plan": plan}
    if warning:
        out["warning"] = warning
    return JSONResponse(content=out, status_code=200)

