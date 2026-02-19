"""Best-effort Graph layer freshness probe (fail-open).

MVP for `/telemetry.graph.layer_freshness`.

We intentionally keep this lightweight and resilient:
- If Neo4j is unavailable or credentials are missing, return all layers as "unknown".
- Use short timeouts to avoid impacting `/telemetry` latency.

Layer IDs: 12 canonical neurolayers (L1..L12). Some may not exist in the graph yet.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


LAYER_IDS_12: list[str] = [
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


def _utc_now_ms() -> int:
    return int(time.time() * 1000)


def _parse_iso_to_ms(ts: str) -> int | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _coerce_any_ts_to_iso(v: Any) -> str | None:
    """Coerce Neo4j/Python date-times to ISO8601 string (UTC offset preserved)."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        dt = v
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    # neo4j.time.DateTime has `.to_native()` in modern drivers.
    to_native = getattr(v, "to_native", None)
    if callable(to_native):
        try:
            dt = to_native()
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
        except Exception:
            return None
    # Fallback: avoid leaking unexpected reprs into payload.
    return None


def _status_for(last_update_iso: str | None, *, now_ms: int, stale_threshold_ms: int) -> str:
    if not last_update_iso:
        return "unknown"
    last_ms = _parse_iso_to_ms(last_update_iso)
    if last_ms is None:
        return "unknown"
    age_ms = max(0, now_ms - last_ms)
    return "live" if age_ms < stale_threshold_ms else "stale"


def _default_stale_threshold_ms() -> int:
    # Simple global threshold for MVP. Tunable per deployment.
    return int(os.getenv("DENIS_GRAPH_LAYER_STALE_MS", "300000"))  # 5 minutes


def _fetch_layer_last_updates_from_neo4j(layer_ids: list[str]) -> dict[str, str | None]:
    """Return {layer_id: last_update_iso|None} for known layer_ids.

    Reads `(:NeuroLayer {node_ref})` and `nl.updated_at` (written by GraphWriter).
    """
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
    if not password:
        raise RuntimeError("neo4j_secret_missing")

    uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")

    connect_timeout_s = float(os.getenv("DENIS_GRAPH_PROBE_CONNECT_TIMEOUT_S", "0.3"))
    query_timeout_s = float(os.getenv("DENIS_GRAPH_PROBE_QUERY_TIMEOUT_S", "0.8"))

    try:
        from neo4j import GraphDatabase  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("neo4j_driver_missing") from exc

    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
        connection_timeout=connect_timeout_s,
    )
    out: dict[str, str | None] = {lid: None for lid in layer_ids}
    try:
        query = """
        MATCH (nl:NeuroLayer)
        WHERE nl.node_ref IN $layer_ids
        RETURN nl.node_ref AS layer_id, nl.updated_at AS updated_at
        """
        with driver.session() as session:
            res = session.run(query, layer_ids=layer_ids, timeout=query_timeout_s)
            for rec in res:
                lid = rec.get("layer_id")
                if not isinstance(lid, str) or lid not in out:
                    continue
                out[lid] = _coerce_any_ts_to_iso(rec.get("updated_at"))
        return out
    finally:
        try:
            driver.close()
        except Exception:
            pass


def get_graph_layer_freshness(
    *,
    layer_ids: list[str] | None = None,
    now_ms: int | None = None,
    stale_threshold_ms: int | None = None,
    fetch_last_updates: Callable[[list[str]], dict[str, str | None]] | None = None,
) -> dict[str, Any]:
    """Return telemetry `graph` block: layers freshness + summary."""
    ids = list(layer_ids or LAYER_IDS_12)
    now = int(now_ms if now_ms is not None else _utc_now_ms())
    thr = int(stale_threshold_ms if stale_threshold_ms is not None else _default_stale_threshold_ms())

    integrity_degraded = False
    last_updates: dict[str, str | None]
    try:
        fetch = fetch_last_updates or _fetch_layer_last_updates_from_neo4j
        last_updates = fetch(ids) or {}
    except Exception:
        integrity_degraded = True
        last_updates = {}

    layers: list[dict[str, Any]] = []
    live = stale = unknown = 0
    for lid in ids:
        ts = last_updates.get(lid)
        status = _status_for(ts, now_ms=now, stale_threshold_ms=thr)
        if status == "live":
            live += 1
        elif status == "stale":
            stale += 1
        else:
            unknown += 1
            ts = None  # contract: null when unknown
        layers.append({"layer_id": lid, "status": status, "last_update_ts": ts})

    return {
        "layers": layers,
        "summary": {
            "live_count": live,
            "stale_count": stale,
            "unknown_count": unknown,
            "integrity_degraded": bool(integrity_degraded),
        },
    }

