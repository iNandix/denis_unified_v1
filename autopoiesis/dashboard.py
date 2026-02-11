"""Phase-4 autopoiesis supervised dashboard helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
from typing import Any

from neo4j import GraphDatabase

from denis_unified_v1.autopoiesis.proposal_engine import (
    APPROVED_KEY,
    PROPOSALS_KEY,
    REJECTED_KEY,
    generate_proposals,
    load_proposals,
)
from denis_unified_v1.cortex.neo4j_config_resolver import ensure_neo4j_env_auto
from denis_unified_v1.feature_flags import load_feature_flags


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redis_client(redis_url: str | None = None):
    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


def _neo4j_cfg() -> tuple[str, str, str]:
    try:
        ensure_neo4j_env_auto()
    except Exception:
        pass
    uri = (os.getenv("NEO4J_URI") or "bolt://10.10.10.1:7687").strip()
    user = (os.getenv("NEO4J_USER") or "neo4j").strip()
    password = (os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "").strip()
    return uri, user, password


def list_proposals(redis_url: str | None = None) -> dict[str, Any]:
    proposals = load_proposals(redis_url=redis_url)
    return {
        "status": "ok",
        "timestamp_utc": _utc_now(),
        "count": len(proposals),
        "proposals": proposals,
    }


def _find_proposal(proposal_id: str, redis_url: str | None = None) -> dict[str, Any] | None:
    client = _redis_client(redis_url=redis_url)
    raw = client.hget(PROPOSALS_KEY, proposal_id)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def simulate_in_sandbox(
    proposal: dict[str, Any],
    timeout_sec: float = 8.0,
) -> dict[str, Any]:
    uri, user, password = _neo4j_cfg()
    if not password:
        return {
            "status": "error",
            "error": "missing_neo4j_password",
            "timestamp_utc": _utc_now(),
            "neo4j": {"uri": uri, "user": user, "password_set": False},
        }

    query = str(proposal.get("cypher") or "").strip()
    params = proposal.get("params") or {}
    if not query:
        return {
            "status": "error",
            "error": "proposal_without_cypher",
            "timestamp_utc": _utc_now(),
        }

    if not isinstance(params, dict):
        params = {}

    start = time.perf_counter()
    driver = None
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=timeout_sec,
        )
        with driver.session() as session:
            tx = session.begin_transaction()
            try:
                result = tx.run(query, **params)
                summary = result.consume()
                counters = summary.counters
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                tx.rollback()
                return {
                    "status": "ok",
                    "timestamp_utc": _utc_now(),
                    "sandbox": "rollback",
                    "duration_ms": elapsed_ms,
                    "neo4j": {"uri": uri, "user": user, "password_set": True},
                    "counters": {
                        "contains_updates": bool(counters.contains_updates),
                        "nodes_created": int(counters.nodes_created),
                        "nodes_deleted": int(counters.nodes_deleted),
                        "relationships_created": int(counters.relationships_created),
                        "relationships_deleted": int(counters.relationships_deleted),
                        "properties_set": int(counters.properties_set),
                    },
                }
            except Exception as exc:
                tx.rollback()
                return {
                    "status": "error",
                    "timestamp_utc": _utc_now(),
                    "sandbox": "rollback",
                    "error": str(exc),
                    "neo4j": {"uri": uri, "user": user, "password_set": True},
                }
    except Exception as exc:
        return {
            "status": "error",
            "timestamp_utc": _utc_now(),
            "error": str(exc),
            "neo4j": {"uri": uri, "user": user, "password_set": bool(password)},
        }
    finally:
        try:
            if driver is not None:
                driver.close()
        except Exception:
            pass


def approve_proposal(proposal_id: str, redis_url: str | None = None) -> dict[str, Any]:
    flags = load_feature_flags()
    if flags.denis_autopoiesis_mode not in {"supervised", "manual"}:
        return {
            "status": "error",
            "error": f"autopoiesis_mode_not_allowed:{flags.denis_autopoiesis_mode}",
            "timestamp_utc": _utc_now(),
        }

    proposal = _find_proposal(proposal_id, redis_url=redis_url)
    if not proposal:
        return {
            "status": "error",
            "error": "proposal_not_found",
            "proposal_id": proposal_id,
            "timestamp_utc": _utc_now(),
        }

    sandbox = simulate_in_sandbox(proposal)
    if sandbox.get("status") != "ok":
        return {
            "status": "rejected",
            "proposal_id": proposal_id,
            "reason": "sandbox_failed",
            "sandbox": sandbox,
            "timestamp_utc": _utc_now(),
        }

    now = _utc_now()
    proposal["status"] = "approved"
    proposal["approved_at"] = now
    proposal["last_sandbox"] = sandbox

    client = _redis_client(redis_url=redis_url)
    raw = json.dumps(proposal, sort_keys=True)
    client.hset(PROPOSALS_KEY, proposal_id, raw)
    client.hset(APPROVED_KEY, proposal_id, raw)
    client.expire(APPROVED_KEY, 86400)

    return {
        "status": "approved",
        "proposal_id": proposal_id,
        "timestamp_utc": now,
        "sandbox": sandbox,
        "execution": "scheduled_manual_only",
    }


def reject_proposal(
    proposal_id: str,
    reason: str = "manual_rejection",
    redis_url: str | None = None,
) -> dict[str, Any]:
    proposal = _find_proposal(proposal_id, redis_url=redis_url)
    if not proposal:
        return {
            "status": "error",
            "error": "proposal_not_found",
            "proposal_id": proposal_id,
            "timestamp_utc": _utc_now(),
        }

    now = _utc_now()
    proposal["status"] = "rejected"
    proposal["rejected_at"] = now
    proposal["rejection_reason"] = reason

    client = _redis_client(redis_url=redis_url)
    raw = json.dumps(proposal, sort_keys=True)
    client.hset(PROPOSALS_KEY, proposal_id, raw)
    client.hset(REJECTED_KEY, proposal_id, raw)
    client.expire(REJECTED_KEY, 86400)

    return {
        "status": "rejected",
        "proposal_id": proposal_id,
        "reason": reason,
        "timestamp_utc": now,
    }


def build_router():
    try:
        from fastapi import APIRouter, HTTPException
    except Exception:
        return None

    router = APIRouter(prefix="/autopoiesis", tags=["autopoiesis"])

    @router.get("/proposals")
    def get_proposals() -> dict[str, Any]:
        return list_proposals()

    @router.post("/proposals/refresh")
    def refresh_proposals() -> dict[str, Any]:
        return generate_proposals(persist_redis=True)

    @router.post("/proposals/{proposal_id}/approve")
    def approve(proposal_id: str) -> dict[str, Any]:
        out = approve_proposal(proposal_id)
        if out.get("status") == "error":
            raise HTTPException(status_code=400, detail=out)
        return out

    @router.post("/proposals/{proposal_id}/reject")
    def reject(proposal_id: str) -> dict[str, Any]:
        out = reject_proposal(proposal_id)
        if out.get("status") == "error":
            raise HTTPException(status_code=404, detail=out)
        return out

    return router

