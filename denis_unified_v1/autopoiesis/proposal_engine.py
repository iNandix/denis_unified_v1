"""Phase-4 autopoiesis proposal engine (supervised, no auto-apply)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any

from denis_unified_v1.metagraph.observer import collect_graph_metrics, load_metrics_redis
from denis_unified_v1.metagraph.pattern_detector import detect_patterns


PROPOSALS_KEY = "autopoiesis:proposals"
APPROVED_KEY = "autopoiesis:approved"
REJECTED_KEY = "autopoiesis:rejected"
LAST_RUN_KEY = "autopoiesis:last_run"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redis_client(redis_url: str | None = None):
    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


def _proposal_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _proposal_fix_orphans(orphan_nodes: int) -> dict[str, Any]:
    proposal: dict[str, Any] = {
        "type": "repair_orphans",
        "description": f"Link orphan nodes to similar hubs (detected={orphan_nodes})",
        "impact": "medium",
        "reversible": True,
        "requires_human_approval": True,
        "contracts": ["level0", "level1"],
        "cypher": """
            MATCH (orphan)
            WHERE NOT (orphan)--()
            WITH orphan LIMIT $orphan_limit
            MATCH (candidate)
            WHERE candidate <> orphan
            WITH orphan, candidate
            ORDER BY rand()
            LIMIT $pair_limit
            MERGE (orphan)-[:SIMILAR_TO {source:'autopoiesis_supervised'}]->(candidate)
            RETURN count(*) AS linked
        """,
        "params": {"orphan_limit": 20, "pair_limit": 20},
        "undo": """
            MATCH ()-[r:SIMILAR_TO {source:'autopoiesis_supervised'}]->()
            DELETE r
            RETURN count(r) AS removed
        """,
    }
    proposal["proposal_id"] = _proposal_id("repair_orphans", proposal)
    return proposal


def _proposal_fill_timestamps(missing_timestamp_nodes: int) -> dict[str, Any]:
    proposal: dict[str, Any] = {
        "type": "fill_missing_timestamps",
        "description": (
            f"Backfill timestamp for nodes without time fields "
            f"(detected={missing_timestamp_nodes})"
        ),
        "impact": "low",
        "reversible": True,
        "requires_human_approval": True,
        "contracts": ["level0", "level1"],
        "cypher": """
            MATCH (n)
            WHERE n.timestamp IS NULL
              AND n.created_at IS NULL
              AND n.updated_at IS NULL
            WITH n LIMIT $limit
            SET n.timestamp = datetime()
            RETURN count(n) AS updated
        """,
        "params": {"limit": 200},
        "undo": """
            MATCH (n)
            WHERE n.timestamp IS NOT NULL
              AND n.created_at IS NULL
              AND n.updated_at IS NULL
            WITH n LIMIT $limit
            REMOVE n.timestamp
            RETURN count(n) AS reverted
        """,
    }
    proposal["proposal_id"] = _proposal_id("fill_timestamps", proposal)
    return proposal


def _build_proposals_from_patterns(patterns_payload: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for anomaly in patterns_payload.get("anomalies", []):
        anomaly_type = str(anomaly.get("type") or "")
        value = int(anomaly.get("value") or 0)
        if anomaly_type == "orphan_pressure" and value > 0:
            proposals.append(_proposal_fix_orphans(value))
        if anomaly_type == "missing_timestamp_nodes" and value > 0:
            proposals.append(_proposal_fill_timestamps(value))
    return proposals


def generate_proposals(
    persist_redis: bool = True,
    redis_ttl_seconds: int = 86400,
) -> dict[str, Any]:
    metrics = load_metrics_redis()
    metrics_source = "redis"
    if not metrics or metrics.get("status") != "ok":
        metrics = collect_graph_metrics()
        metrics_source = "live"

    patterns = detect_patterns(metrics)
    proposals = _build_proposals_from_patterns(patterns)

    payload = {
        "status": "ok" if metrics.get("status") == "ok" else "error",
        "timestamp_utc": _utc_now(),
        "metrics_source": metrics_source,
        "metrics_status": metrics.get("status"),
        "patterns_status": patterns.get("status"),
        "generated_count": len(proposals),
        "proposals": proposals,
    }

    if not persist_redis:
        return payload

    try:
        client = _redis_client()
        pipe = client.pipeline()
        pipe.delete(PROPOSALS_KEY)
        for proposal in proposals:
            pid = str(proposal["proposal_id"])
            row = dict(proposal)
            row["status"] = "pending"
            row["created_at"] = payload["timestamp_utc"]
            pipe.hset(PROPOSALS_KEY, pid, json.dumps(row, sort_keys=True))
        pipe.expire(PROPOSALS_KEY, redis_ttl_seconds)
        pipe.hset(
            LAST_RUN_KEY,
            mapping={
                "timestamp_utc": payload["timestamp_utc"],
                "generated_count": str(len(proposals)),
                "metrics_source": metrics_source,
                "metrics_status": str(metrics.get("status")),
            },
        )
        pipe.expire(LAST_RUN_KEY, redis_ttl_seconds)
        pipe.execute()
        payload["redis"] = {
            "status": "ok",
            "key": PROPOSALS_KEY,
            "ttl_seconds": redis_ttl_seconds,
        }
    except Exception as exc:
        payload["redis"] = {
            "status": "error",
            "error": str(exc),
            "key": PROPOSALS_KEY,
        }
        payload["status"] = "error"

    return payload


def load_proposals(redis_url: str | None = None) -> list[dict[str, Any]]:
    client = _redis_client(redis_url=redis_url)
    rows = client.hgetall(PROPOSALS_KEY)
    proposals: list[dict[str, Any]] = []
    for _, raw in rows.items():
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                proposals.append(obj)
        except Exception:
            continue
    proposals.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return proposals

