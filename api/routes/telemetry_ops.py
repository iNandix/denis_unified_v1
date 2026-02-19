"""Telemetry endpoint for Ops monitoring.

P0: In-memory counters (no external deps). Always fail-open.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter()

@router.get("/telemetry", response_model=None)
async def get_telemetry(
    request: Request, accept: str = Header(default="application/json")
):
    """
    Returns telemetry metrics.

    Accept: application/json (default) o text/plain (Prometheus)
    """
    start_time = time.time()
    try:
        accept_norm = (accept or "").lower()

        from api.telemetry_store import get_telemetry_store

        store = get_telemetry_store()
        # Best-effort queue depth (fail-open). Keep in-memory only.
        try:
            from denis_unified_v1.async_min.config import get_async_config
            import redis  # type: ignore

            cfg = get_async_config()
            if cfg.enabled:
                r = redis.Redis.from_url(
                    cfg.broker_url,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                    retry_on_timeout=False,
                )
                r.ping()
                # Celery Redis transport uses list keys equal to queue names by default.
                store.queue_depth = int(r.llen("denis:async_min"))
            else:
                store.queue_depth = None
        except Exception:
            store.queue_depth = None
        snap = store.snapshot()

        # Best-effort graph freshness (fail-open). Never blocks /telemetry.
        try:
            from api.graph_freshness import get_graph_layer_freshness

            graph_block = get_graph_layer_freshness()
        except Exception:
            layer_ids_12 = [
                "neuro:layer:1",   # sensory_io
                "neuro:layer:2",   # attention
                "neuro:layer:3",   # intent_goals
                "neuro:layer:4",   # plans_procedures
                "neuro:layer:5",   # memory_short
                "neuro:layer:6",   # memory_long
                "neuro:layer:7",   # safety_governance
                "neuro:layer:8",   # ops_awareness
                "neuro:layer:9",   # social_persona
                "neuro:layer:10",  # self_monitoring
                "neuro:layer:11",  # learning_plasticity
                "neuro:layer:12",  # meta_consciousness
            ]
            graph_block = {
                "layers": [
                    {"layer_id": lid, "status": "unknown", "last_update_ts": None}
                    for lid in layer_ids_12
                ],
                "summary": {
                    "live_count": 0,
                    "stale_count": 0,
                    "unknown_count": 12,
                    "integrity_degraded": True,
                },
            }
        # Graph materializer stats (fail-open).
        try:
            from denis_unified_v1.graph.materializers.event_materializer import (
                get_materializer_stats,
            )

            graph_block["materializer"] = get_materializer_stats()
        except Exception:
            graph_block["materializer"] = {
                "last_mutation_ts": "",
                "last_event_ts": "",
                "lag_ms": 0,
                "errors_window": 0,
                "graph_up": None,
            }
        # Convenience keys (required by WS9 acceptance): graph.last_mutation_ts, graph.materializer.lag_ms, etc.
        try:
            graph_block["last_mutation_ts"] = str(graph_block.get("materializer", {}).get("last_mutation_ts") or "")
            graph_block["materializer_lag_ms"] = int(graph_block.get("materializer", {}).get("lag_ms") or 0)
            graph_block["materializer_errors_window"] = int(graph_block.get("materializer", {}).get("errors_window") or 0)
        except Exception:
            graph_block["last_mutation_ts"] = ""
            graph_block["materializer_lag_ms"] = 0
            graph_block["materializer_errors_window"] = 0
        # Graph SSoT client status (fail-open).
        try:
            from denis_unified_v1.graph.graph_client import get_graph_client

            gs = get_graph_client().status()
            graph_block["ssot"] = {
                "enabled": gs.enabled,
                "up": gs.up,
                "last_ok_ts": gs.last_ok_ts,
                "last_err_ts": gs.last_err_ts,
                "errors_window": gs.errors_window,
            }
        except Exception:
            graph_block["ssot"] = {
                "enabled": False,
                "up": None,
                "last_ok_ts": "",
                "last_err_ts": "",
                "errors_window": 0,
            }

        response_data = {
            "requests": {
                "total_1h": int(snap["requests"]["total"]),
                "error_rate_1h": 0.0,  # P0: not computed
                "latency_p95_ms": 0,  # P0: not computed
                "by_path": snap["requests"].get("by_path", {}),
                "by_status": snap["requests"].get("by_status", {}),
                "last_request_utc": snap["requests"].get("last_request_utc", ""),
            },
            "persona": _persona_emitter_status_fail_open(),
            "chat": snap.get("chat", {}),
            "async": snap.get("async", {}),
            "providers": {},  # P0 placeholder
            "graph": graph_block,
            "control_room": _control_room_status_fail_open(),
            "vectorstore": _vectorstore_status_fail_open(),
            "neuro": _neuro_status_fail_open(),
            "timestamp": snap.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "started_utc": snap.get("started_utc", ""),
        }

        # Escribir DecisionTrace (opcional, fail-open)
        try:
            from denis_unified_v1.chat_cp.graph_trace import maybe_write_decision_trace

            maybe_write_decision_trace(
                trace_id=str(request.state.trace_id)
                if hasattr(request.state, "trace_id")
                else None,
                endpoint="/telemetry",
                decision_type="ops_query",
                outcome="success",
                latency_ms=int((time.time() - start_time) * 1000),
                context={
                    "sources_queried": ["memory"],
                    "format": "prometheus" if "text/plain" in accept_norm else "json",
                },
            )
        except Exception:
            pass

        if "text/plain" in accept_norm:
            return PlainTextResponse(content=store.to_prometheus())
        return JSONResponse(content=response_data)
    except Exception:
        # Fail-open: nunca 500
        try:
            from api.graph_freshness import get_graph_layer_freshness

            graph_block = get_graph_layer_freshness()
        except Exception:
            layer_ids_12 = [
                "neuro:layer:1",   # sensory_io
                "neuro:layer:2",   # attention
                "neuro:layer:3",   # intent_goals
                "neuro:layer:4",   # plans_procedures
                "neuro:layer:5",   # memory_short
                "neuro:layer:6",   # memory_long
                "neuro:layer:7",   # safety_governance
                "neuro:layer:8",   # ops_awareness
                "neuro:layer:9",   # social_persona
                "neuro:layer:10",  # self_monitoring
                "neuro:layer:11",  # learning_plasticity
                "neuro:layer:12",  # meta_consciousness
            ]
            graph_block = {
                "layers": [
                    {"layer_id": lid, "status": "unknown", "last_update_ts": None}
                    for lid in layer_ids_12
                ],
                "summary": {
                    "live_count": 0,
                    "stale_count": 0,
                    "unknown_count": 12,
                    "integrity_degraded": True,
                },
            }
        try:
            from denis_unified_v1.graph.materializers.event_materializer import (
                get_materializer_stats,
            )

            graph_block["materializer"] = get_materializer_stats()
        except Exception:
            graph_block["materializer"] = {
                "last_mutation_ts": "",
                "last_event_ts": "",
                "lag_ms": 0,
                "errors_window": 0,
                "graph_up": None,
            }
        response_data = {
            "requests": {
                "total_1h": 0,
                "error_rate_1h": 0.0,
                "latency_p95_ms": 0,
                "by_path": {},
                "by_status": {},
                "last_request_utc": "",
            },
            "persona": _persona_emitter_status_fail_open(),
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
            "graph": graph_block,
            "control_room": _control_room_status_fail_open(),
            "vectorstore": _vectorstore_status_fail_open(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": {"code": "degraded", "msg": "telemetry_failed"},
        }
        return JSONResponse(status_code=200, content=response_data)


def _vectorstore_status_fail_open() -> dict:
    try:
        from denis_unified_v1.vectorstore.qdrant_client import get_vectorstore

        vs = get_vectorstore()
        return {
            "enabled": bool(vs.enabled),
            "collection": vs.collection_default,
            "last_upsert_ts": vs.last_upsert_ts or "",
            "upsert_count": int(vs.upsert_count),
            "search_count": int(vs.search_count),
            "fail_count": int(vs.fail_count),
            "qdrant_up": None,  # best-effort; avoid network probes in /telemetry
        }
    except Exception:
        return {
            "enabled": False,
            "collection": "",
            "last_upsert_ts": "",
            "upsert_count": 0,
            "search_count": 0,
            "fail_count": 0,
            "qdrant_up": None,
        }


def _persona_emitter_status_fail_open() -> dict:
    try:
        from api.persona.event_router import get_persona_emitter_stats

        return get_persona_emitter_stats()
    except Exception:
        return {
            "emitter": "denis_persona",
            "error": {"code": "degraded", "msg": "persona_stats_unavailable"},
        }


def _control_room_status_fail_open() -> dict:
    try:
        import os

        from denis_unified_v1.control_room.worker_state import snapshot_worker_state

        enabled = (os.getenv("CONTROL_ROOM_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
        return {
            "enabled": bool(enabled),
            "worker": snapshot_worker_state(),
        }
    except Exception:
        return {"enabled": False, "worker": {"heartbeat_ts": "", "queue_depth": None, "running_count": None}}


def _neuro_status_fail_open() -> dict:
    """WS23-G: neuro consciousness + layer stats for telemetry (fail-open)."""
    try:
        from denis_unified_v1.feature_flags import load_feature_flags

        ff = load_feature_flags()
        if not getattr(ff, "neuro_enabled", True):
            return {"enabled": False}

        from denis_unified_v1.graph.graph_client import get_graph_client
        from denis_unified_v1.neuro.sequences import _read_layers, _read_consciousness

        g = get_graph_client()
        layers = _read_layers(g)
        cs = _read_consciousness(g)

        layers_summary = []
        for l in layers:
            layers_summary.append({
                "layer_id": l.id,
                "layer_key": l.layer_key,
                "freshness_score": l.freshness_score,
                "status": l.status,
                "signals_count": l.signals_count,
            })

        ok_count = sum(1 for l in layers if l.status == "ok")
        deg_count = sum(1 for l in layers if l.status == "degraded")
        avg_fresh = (
            round(sum(l.freshness_score for l in layers) / len(layers), 3)
            if layers else 0.0
        )

        return {
            "enabled": True,
            "layers": layers_summary,
            "summary": {
                "layers_count": len(layers),
                "ok_count": ok_count,
                "degraded_count": deg_count,
                "avg_freshness": avg_fresh,
            },
            "consciousness": {
                "mode": (cs or {}).get("mode", "unknown"),
                "fatigue_level": float((cs or {}).get("fatigue_level", 0)),
                "risk_level": float((cs or {}).get("risk_level", 0)),
                "confidence_level": float((cs or {}).get("confidence_level", 0)),
                "guardrails_mode": (cs or {}).get("guardrails_mode", "unknown"),
                "memory_mode": (cs or {}).get("memory_mode", "unknown"),
                "voice_mode": (cs or {}).get("voice_mode", "unknown"),
                "ops_mode": (cs or {}).get("ops_mode", "unknown"),
                "last_wake_ts": (cs or {}).get("last_wake_ts", ""),
                "last_turn_ts": (cs or {}).get("last_turn_ts", ""),
            },
        }
    except Exception:
        return {"enabled": False, "error": "unavailable"}
