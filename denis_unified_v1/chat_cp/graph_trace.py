"""Graph and in-memory trace for chat control plane runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
import threading
import uuid
from typing import Any

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver


_TRACES: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_run(run_id: str, policy_id: str, chain: list[str]) -> None:
    with _LOCK:
        _TRACES.setdefault(
            run_id,
            {
                "run_id": run_id,
                "policy_id": policy_id,
                "provider_chain": list(chain),
                "decisions": [],
                "outcome": None,
                "created_at": _ts(),
            },
        )


def append_decision(
    run_id: str,
    *,
    policy_id: str,
    provider: str,
    status: str,
    latency_ms: int,
    error_code: str | None,
    message_hash: str,
    shadow: bool = False,
) -> str:
    decision_id = f"chat_decision_{uuid.uuid4()}"
    row = {
        "decision_id": decision_id,
        "provider": provider,
        "status": status,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "shadow": shadow,
        "message_hash": message_hash,
        "ts": _ts(),
    }
    with _LOCK:
        run = _TRACES.setdefault(
            run_id,
            {
                "run_id": run_id,
                "policy_id": policy_id,
                "provider_chain": [],
                "decisions": [],
                "outcome": None,
                "created_at": _ts(),
            },
        )
        run["decisions"].append(row)

    _write_graph_decision(
        run_id=run_id,
        policy_id=policy_id,
        decision_id=decision_id,
        provider=provider,
        status=status,
        latency_ms=latency_ms,
        error_code=error_code,
        shadow=shadow,
        message_hash=message_hash,
    )
    return decision_id


def set_outcome(
    run_id: str,
    *,
    decision_id: str | None,
    provider: str,
    success: bool,
    latency_ms: int,
    error_code: str | None,
) -> str:
    outcome_id = f"chat_outcome_{uuid.uuid4()}"
    outcome = {
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "provider": provider,
        "success": success,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "ts": _ts(),
    }
    with _LOCK:
        run = _TRACES.setdefault(
            run_id,
            {
                "run_id": run_id,
                "policy_id": "control_plane_chat_default",
                "provider_chain": [],
                "decisions": [],
                "outcome": None,
                "created_at": _ts(),
            },
        )
        run["outcome"] = outcome

    _write_graph_outcome(
        run_id=run_id,
        outcome_id=outcome_id,
        decision_id=decision_id,
        provider=provider,
        success=success,
        latency_ms=latency_ms,
        error_code=error_code,
    )
    return outcome_id


def get_trace(run_id: str) -> dict[str, Any] | None:
    with _LOCK:
        payload = _TRACES.get(run_id)
        return deepcopy(payload) if payload is not None else None


def _write_graph_decision(
    *,
    run_id: str,
    policy_id: str,
    decision_id: str,
    provider: str,
    status: str,
    latency_ms: int,
    error_code: str | None,
    shadow: bool,
    message_hash: str,
) -> None:
    if os.getenv("DENIS_CHAT_CP_GRAPH_WRITE", "0") != "1":
        return
    driver = _get_neo4j_driver()
    if not driver:
        return
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (p:ChatPolicy {id: $policy_id})
                MERGE (prov:Provider {name: $provider})
                MERGE (p)-[:POLICY_SELECTS_PROVIDER]->(prov)
                CREATE (d:Decision {
                    id: $decision_id,
                    run_id: $run_id,
                    ts: $ts,
                    status: $status,
                    latency_ms: $latency_ms,
                    error_code: $error_code,
                    shadow: $shadow,
                    message_hash: $message_hash
                })
                MERGE (prov)-[:PROVIDER_MADE_DECISION]->(d)
                """,
                {
                    "policy_id": policy_id,
                    "provider": provider,
                    "decision_id": decision_id,
                    "run_id": run_id,
                    "ts": _ts(),
                    "status": status,
                    "latency_ms": latency_ms,
                    "error_code": error_code,
                    "shadow": shadow,
                    "message_hash": message_hash,
                },
            )
    except Exception:
        # fail-soft by design
        pass


def _write_graph_outcome(
    *,
    run_id: str,
    outcome_id: str,
    decision_id: str | None,
    provider: str,
    success: bool,
    latency_ms: int,
    error_code: str | None,
) -> None:
    if os.getenv("DENIS_CHAT_CP_GRAPH_WRITE", "0") != "1":
        return
    driver = _get_neo4j_driver()
    if not driver:
        return
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (prov:Provider {name: $provider})
                CREATE (o:Outcome {
                    id: $outcome_id,
                    run_id: $run_id,
                    ts: $ts,
                    success: $success,
                    latency_ms: $latency_ms,
                    error_code: $error_code
                })
                WITH prov, o
                OPTIONAL MATCH (d:Decision {id: $decision_id})
                FOREACH (_ IN CASE WHEN d IS NULL THEN [] ELSE [1] END |
                    MERGE (d)-[:DECISION_RESULTED_IN]->(o)
                )
                MERGE (prov)-[:PROVIDER_OUTCOME]->(o)
                """,
                {
                    "provider": provider,
                    "outcome_id": outcome_id,
                    "run_id": run_id,
                    "ts": _ts(),
                    "success": success,
                    "latency_ms": latency_ms,
                    "error_code": error_code,
                    "decision_id": decision_id,
                },
            )
    except Exception:
        # fail-soft by design
        pass


def maybe_write_decision_trace(
    *,
    trace_id: str | None,
    endpoint: str,
    decision_type: str,
    outcome: str,
    latency_ms: int,
    context: dict | None = None,
) -> None:
    """Write DecisionTrace for ops endpoints (/health, /hass/entities, /telemetry).

    P0: Writes to Graph if DENIS_CHAT_CP_GRAPH_WRITE=1
    P1: Enrich with more context
    """
    if os.getenv("DENIS_CHAT_CP_GRAPH_WRITE", "0") != "1":
        return

    driver = _get_neo4j_driver()
    if not driver:
        return

    decision_id = trace_id or f"ops_decision_{uuid.uuid4()}"

    try:
        with driver.session() as session:
            session.run(
                """
                CREATE (d:Decision {
                    id: $decision_id,
                    endpoint: $endpoint,
                    decision_type: $decision_type,
                    outcome: $outcome,
                    latency_ms: $latency_ms,
                    context: $context,
                    ts: $ts
                })
                """,
                {
                    "decision_id": decision_id,
                    "endpoint": endpoint,
                    "decision_type": decision_type,
                    "outcome": outcome,
                    "latency_ms": latency_ms,
                    "context": str(context) if context else "{}",
                    "ts": _ts(),
                },
            )
    except Exception:
        # fail-soft: no fallar si no podemos escribir trace
        pass
