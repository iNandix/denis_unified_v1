"""Passive graph observer for Denis metagraph phase.

Read-only on Neo4j graph structure.
Optional persistence to Redis for dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from denis_unified_v1.cortex.neo4j_config_resolver import ensure_neo4j_env_auto

@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str


def resolve_neo4j_config() -> Neo4jConfig:
    # Reuse existing Denis config sources so manual export is not required daily.
    try:
        ensure_neo4j_env_auto()
    except Exception:
        pass
    return Neo4jConfig(
        uri=(os.getenv("NEO4J_URI") or "bolt://10.10.10.1:7687").strip(),
        user=(os.getenv("NEO4J_USER") or "neo4j").strip(),
        password=(os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "").strip(),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_password(cfg: Neo4jConfig) -> None:
    if not cfg.password:
        raise ValueError("Missing Neo4j password (set NEO4J_PASSWORD or NEO4J_PASS)")


def _run_scalar(session, query: str, **params: Any) -> int:
    row = session.run(query, **params).single()
    if not row:
        return 0
    value = row[0]
    return int(value) if value is not None else 0


def collect_graph_metrics(
    label_limit: int = 80,
    hub_limit: int = 30,
    sample_node_limit: int = 300,
) -> dict[str, Any]:
    cfg = resolve_neo4j_config()
    _require_password(cfg)
    driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))
    try:
        with driver.session() as session:
            total_nodes = _run_scalar(session, "MATCH (n) RETURN count(n)")
            total_edges = _run_scalar(session, "MATCH ()-[r]->() RETURN count(r)")
            orphan_nodes = _run_scalar(
                session,
                "MATCH (n) WHERE NOT (n)--() RETURN count(n)",
            )
            missing_timestamp_nodes = _run_scalar(
                session,
                """
                MATCH (n)
                WHERE n.timestamp IS NULL
                  AND n.created_at IS NULL
                  AND n.updated_at IS NULL
                RETURN count(n)
                """,
            )
            two_hop_cycles = _run_scalar(
                session,
                """
                MATCH (a)-[]->(b)-[]->(a)
                RETURN count(*) AS c
                """,
            )

            label_distribution = session.run(
                """
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS cnt
                ORDER BY cnt DESC
                LIMIT $limit
                """,
                limit=label_limit,
            ).data()

            top_hubs = session.run(
                """
                MATCH (n)
                WITH n, COUNT { (n)--() } AS degree
                ORDER BY degree DESC
                LIMIT $limit
                RETURN
                  coalesce(n.node_id, n.id, n.name, toString(id(n))) AS node_ref,
                  labels(n) AS labels,
                  degree
                """,
                limit=hub_limit,
            ).data()

            sampled_orphan_labels = session.run(
                """
                MATCH (n)
                WHERE NOT (n)--()
                WITH n
                LIMIT $limit
                UNWIND labels(n) AS label
                RETURN label, count(*) AS cnt
                ORDER BY cnt DESC
                """,
                limit=sample_node_limit,
            ).data()

        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "neo4j": {"uri": cfg.uri, "user": cfg.user, "password_set": bool(cfg.password)},
            "metrics": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "orphan_nodes": orphan_nodes,
                "missing_timestamp_nodes": missing_timestamp_nodes,
                "two_hop_cycles": two_hop_cycles,
            },
            "label_distribution": label_distribution,
            "top_hubs": top_hubs,
            "sampled_orphan_labels": sampled_orphan_labels,
        }
    except (Neo4jError, ValueError) as exc:
        return {
            "status": "error",
            "timestamp_utc": _utc_now(),
            "error": str(exc),
            "neo4j": {"uri": cfg.uri, "user": cfg.user, "password_set": bool(cfg.password)},
        }
    finally:
        try:
            driver.close()
        except Exception:
            pass


def persist_metrics_redis(
    payload: dict[str, Any],
    ttl_seconds: int = 3600,
    redis_url: str | None = None,
) -> dict[str, Any]:
    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        raw = json.dumps(payload, sort_keys=True)
        client.setex("metagraph:metrics:latest", ttl_seconds, raw)
        client.hset(
            "metagraph:last_run",
            mapping={
                "timestamp_utc": payload.get("timestamp_utc", ""),
                "status": payload.get("status", ""),
            },
        )
        return {"status": "ok", "redis_url": url, "ttl_seconds": ttl_seconds}
    except Exception as exc:
        return {"status": "error", "redis_url": url, "error": str(exc)}


def load_metrics_redis(redis_url: str | None = None) -> dict[str, Any] | None:
    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        raw = client.get("metagraph:metrics:latest")
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None
