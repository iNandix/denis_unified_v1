"""Health endpoint for Ops dashboard - P0 Implementation."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# In-memory health state (P0 stub)
_health_state = {
    "status": "healthy",
    "version": "3.1.0",
    "services": {
        "chat_cp": {"status": "up", "latency_ms": 45},
        "graph": {"status": "up", "nodes": 150},
        "overlay": {"status": "up", "last_scan": "2026-02-18T12:00:00Z"},
    },
    "nodomac": {"reachable": True, "last_heartbeat": "2026-02-18T14:29:00Z"},
}


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """
    Returns system health status.

    P0: Stub válido con datos hardcodeados
    P1: Health checks reales a servicios
    """
    from denis_unified_v1.chat_cp.graph_trace import maybe_write_decision_trace

    start_time = time.time()

    # P0: Devolvemos stub válido
    # P1: Aquí haríamos pings reales a servicios
    response_data = {
        "status": _health_state["status"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": _health_state["version"],
        "services": _health_state["services"],
        "nodomac": _health_state["nodomac"],
    }
    # Align with /telemetry async block (v1.1). Fail-open: if telemetry store missing,
    # expose stable shape with nulls/defaults.
    try:
        from api.telemetry_store import get_telemetry_store

        response_data["async"] = get_telemetry_store().snapshot().get("async", {})
    except Exception:
        response_data["async"] = {
            "async_enabled": False,
            "worker_seen": False,
            "materializer_stale": True,
            "last_materialize_ts": "",
            "blocked_mutations_count": 0,
            "queue_depth": None,
        }

    # Graph SSoT status (best-effort). Fail-open.
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client
        from denis_unified_v1.graph.materializers.event_materializer import get_materializer_stats

        gs = get_graph_client().status()
        response_data["graph_ssot"] = {
            "enabled": gs.enabled,
            "up": gs.up,
            "last_ok_ts": gs.last_ok_ts,
            "last_err_ts": gs.last_err_ts,
            "errors_window": gs.errors_window,
            "materializer": get_materializer_stats(),
        }
    except Exception:
        response_data["graph_ssot"] = {
            "enabled": False,
            "up": None,
            "last_ok_ts": "",
            "last_err_ts": "",
            "errors_window": 0,
            "materializer": {},
        }

    # Vectorstore status (best-effort). Fail-open.
    try:
        from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore

        vs = get_vectorstore()
        response_data["vectorstore"] = {
            "enabled": bool(vs.enabled),
            "collection": vs.collection_default,
            "last_upsert_ts": vs.last_upsert_ts or "",
            "upsert_count": int(vs.upsert_count),
            "search_count": int(vs.search_count),
            "fail_count": int(vs.fail_count),
            "qdrant_up": None,
        }
    except Exception:
        response_data["vectorstore"] = {
            "enabled": False,
            "collection": "",
            "last_upsert_ts": "",
            "upsert_count": 0,
            "search_count": 0,
            "fail_count": 0,
            "qdrant_up": None,
        }

    # WS23-G Neuro status (best-effort). Fail-open.
    try:
        import os as _nos

        from denis_unified_v1.feature_flags import load_feature_flags as _lff
        _nff = _lff()
        neuro_enabled = getattr(_nff, "neuro_enabled", True)
        if neuro_enabled:
            from denis_unified_v1.graph.graph_client import get_graph_client as _ngc
            from denis_unified_v1.neuro.sequences import _read_layers, _read_consciousness

            _ng = _ngc()
            _nlayers = _read_layers(_ng)
            _ncs = _read_consciousness(_ng)
            _n_ok = sum(1 for l in _nlayers if l.status == "ok")
            _n_deg = sum(1 for l in _nlayers if l.status == "degraded")
            _avg_fresh = (
                round(sum(l.freshness_score for l in _nlayers) / len(_nlayers), 3)
                if _nlayers else 0.0
            )
            response_data["neuro"] = {
                "enabled": True,
                "layers_count": len(_nlayers),
                "layers_ok": _n_ok,
                "layers_degraded": _n_deg,
                "avg_freshness": _avg_fresh,
                "consciousness_mode": (_ncs or {}).get("mode", "unknown"),
                "guardrails_mode": (_ncs or {}).get("guardrails_mode", "unknown"),
                "fatigue_level": float((_ncs or {}).get("fatigue_level", 0)),
                "risk_level": float((_ncs or {}).get("risk_level", 0)),
                "confidence_level": float((_ncs or {}).get("confidence_level", 0)),
                "last_wake_ts": (_ncs or {}).get("last_wake_ts", ""),
                "last_turn_ts": (_ncs or {}).get("last_turn_ts", ""),
            }
        else:
            response_data["neuro"] = {"enabled": False}
    except Exception:
        response_data["neuro"] = {"enabled": False, "error": "unavailable"}

    # Control Room status (best-effort). Fail-open.
    try:
        import os as _os

        from denis_unified_v1.control_room.worker_state import snapshot_worker_state

        enabled = (_os.getenv("CONTROL_ROOM_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
        ws = snapshot_worker_state()
        worker_up: bool | None
        if not ws.get("heartbeat_ts"):
            worker_up = None
        else:
            # Best-effort: if heartbeat is recent enough, consider worker up.
            worker_up = True
        response_data["control_room"] = {
            "enabled": bool(enabled),
            "worker_up": worker_up,
            "worker": ws,
        }
    except Exception:
        response_data["control_room"] = {"enabled": False, "worker_up": None, "worker": {}}

    # Escribir DecisionTrace (siempre)
    try:
        maybe_write_decision_trace(
            trace_id=str(request.state.trace_id)
            if hasattr(request.state, "trace_id")
            else None,
            endpoint="/health",
            decision_type="ops_query",
            outcome="success",
            latency_ms=int((time.time() - start_time) * 1000),
            context={"sources_queried": ["memory"], "cache_hit": True},
        )
    except Exception:
        # Fail-open: no fallamos si no podemos escribir trace
        pass

    return JSONResponse(content=response_data)
