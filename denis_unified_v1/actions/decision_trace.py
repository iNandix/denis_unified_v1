"""
Decision Trace - Audit & Debugging for Denis decisions.

Traces: engine_selection, tool_approval, plan_selection, routing.
Never blocks the main flow - all writes are fire-and-forget with short timeout.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)

DECISION_KINDS = {
    "engine_selection",
    "tool_approval",
    "plan_selection",
    "routing",
    "research",
    "policy_eval",
    # Codecraft kinds
    "codecraft_classify",
    "codecraft_retrieve",
    "codecraft_rank_select",
    "codecraft_plan",
    "codecraft_compose",
    "codecraft_apply",
    "codecraft_verify",
    "codecraft_reuse",
}

DECISION_MODES = {
    "engine_selection": {"PRIMARY", "OFFLOAD", "DEGRADED", "FALLBACK", "SHADOW"},
    "tool_approval": {"APPROVED", "REQUIRES_HUMAN", "BLOCKED"},
    "plan_selection": {"SELECTED", "FALLBACK", "GATED"},
    "routing": {"DEDICATED", "LAN", "TAILSCALE", "CLOUD"},
    "research": {"FAST", "DEEP", "WEB_ONLY", "GRAPH_ONLY"},
    "policy_eval": {"PASSED", "BLOCKED", "FORCED", "SKIPPED"},
    # Codecraft modes
    "codecraft_classify": {
        "scaffold_arch",
        "impl_refactor",
        "integration_tooling",
        "quality_reliability",
    },
    "codecraft_retrieve": {"local_repo", "knowledge_base", "github", "huggingface"},
    "codecraft_rank_select": {"REUSE", "CHUNKS", "GENERATE"},
    "codecraft_plan": {"SIMPLE", "DECOMPOSED", "COMPOSED"},
    "codecraft_compose": {"ADAPTED", "COMPOSED", "GENERATED"},
    "codecraft_apply": {"APPLIED", "APPROVAL_REQUIRED", "BLOCKED"},
    "codecraft_verify": {"PASSED", "FAILED", "SKIPPED"},
    "codecraft_reuse": {"EXACT", "ADAPTED", "NONE"},
}


def emit_decision_trace(
    kind: str,
    mode: str,
    reason: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    request_id: Optional[str] = None,
    intent: Optional[str] = None,
    engine: Optional[str] = None,
    tool: Optional[str] = None,
    plan_candidate: Optional[str] = None,
    confidence: Optional[float] = None,
    confidence_band: Optional[str] = None,
    local_ok: Optional[bool] = None,
    local_required_total: Optional[int] = None,
    local_required_active: Optional[int] = None,
    policies: Optional[list[str]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """
    Emit a decision trace to Neo4j.

    Returns the trace_id if successful, None if failed (non-blocking).
    """
    import json

    if kind not in DECISION_KINDS:
        logger.warning(f"Unknown decision kind: {kind}")
        return None

    trace_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    session_id = session_id or os.getenv("DENIS_SESSION_ID", "unknown")

    # Convert extra dict to string (Neo4j doesn't support map properties)
    extra_str = json.dumps(extra) if extra else None

    driver = _get_neo4j_driver()
    if not driver:
        logger.debug("No Neo4j driver - skipping decision trace")
        return None

    try:
        with driver.session() as session:
            # Create DecisionTrace node
            query = """
                CREATE (d:DecisionTrace {
                    id: $id,
                    ts: $ts,
                    kind: $kind,
                    mode: $mode,
                    reason: $reason,
                    session_id: $session_id,
                    turn_id: $turn_id,
                    request_id: $request_id,
                    intent: $intent,
                    engine: $engine,
                    tool: $tool,
                    plan_candidate: $plan_candidate,
                    confidence: $confidence,
                    confidence_band: $confidence_band,
                    local_ok: $local_ok,
                    local_required_total: $local_required_total,
                    local_required_active: $local_required_active,
                    policies: $policies,
                    extra: $extra_str
                })
            """

            params = {
                "id": trace_id,
                "ts": ts,
                "kind": kind,
                "mode": mode,
                "reason": reason,
                "session_id": session_id,
                "turn_id": turn_id,
                "request_id": request_id,
                "intent": intent,
                "engine": engine,
                "tool": tool,
                "plan_candidate": plan_candidate,
                "confidence": confidence,
                "confidence_band": confidence_band,
                "local_ok": local_ok,
                "local_required_total": local_required_total,
                "local_required_active": local_required_active,
                "policies": policies or [],
                "extra_str": extra_str,
            }

            session.run(query, params)

            # Link to Intent if provided
            if intent:
                session.run(
                    """
                    MATCH (d:DecisionTrace {id: $id})
                    MATCH (i:Intent {name: $intent})
                    MERGE (d)-[:ABOUT_INTENT]->(i)
                """,
                    {"id": trace_id, "intent": intent},
                )

            # Link to Engine if provided
            if engine:
                session.run(
                    """
                    MATCH (d:DecisionTrace {id: $id})
                    MATCH (e:Engine {name: $engine})
                    MERGE (d)-[:SELECTED_ENGINE]->(e)
                """,
                    {"id": trace_id, "engine": engine},
                )

            # Link to Tool if provided
            if tool:
                session.run(
                    """
                    MATCH (d:DecisionTrace {id: $id})
                    MATCH (t:Tool {name: $tool})
                    MERGE (d)-[:ABOUT_TOOL]->(t)
                """,
                    {"id": trace_id, "tool": tool},
                )

            # Link to Turn if provided
            if turn_id:
                session.run(
                    """
                    MATCH (d:DecisionTrace {id: $id})
                    MATCH (t:Turn {id: $turn_id})
                    MERGE (d)-[:ABOUT_TURN]->(t)
                """,
                    {"id": trace_id, "turn_id": turn_id},
                )

            logger.debug(f"Decision trace emitted: {kind}/{mode}/{reason}")
            return trace_id

    except Exception as e:
        logger.warning(f"Failed to emit decision trace: {e}")
        return None


def trace_engine_selection(
    intent: str,
    engine: str,
    mode: str,
    reason: str,
    local_ok: bool,
    local_required_total: int = 6,
    local_required_active: int = 6,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    policies: Optional[list[str]] = None,
    candidates_considered: Optional[list[str]] = None,
    confidence: Optional[float] = None,
    confidence_band: Optional[str] = None,
) -> Optional[str]:
    """Convenience wrapper for engine selection traces."""
    return emit_decision_trace(
        kind="engine_selection",
        mode=mode,
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        engine=engine,
        local_ok=local_ok,
        local_required_total=local_required_total,
        local_required_active=local_required_active,
        policies=policies,
        extra={
            "candidates_considered": candidates_considered,
            "confidence": confidence,
            "confidence_band": confidence_band,
        },
    )


def trace_routing(
    interface_kind: str,
    service_name: str,
    endpoint: str,
    reason: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    intent: Optional[str] = None,
    engine: Optional[str] = None,
) -> Optional[str]:
    """Convenience wrapper for network routing traces."""
    return emit_decision_trace(
        kind="routing",
        mode=interface_kind.upper(),
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        engine=engine,
        extra={"service_name": service_name, "endpoint": endpoint},
    )


def trace_policy_eval(
    policy_id: str,
    decision: str,
    reason: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    intent: Optional[str] = None,
    policy_hits: Optional[list[str]] = None,
) -> Optional[str]:
    """Convenience wrapper for policy evaluation traces."""
    return emit_decision_trace(
        kind="policy_eval",
        mode=decision,
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        policies=policy_hits,
        extra={"policy_id": policy_id},
    )


def trace_research(
    mode: str,
    query: str,
    sources_count: int,
    reason: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    intent: Optional[str] = None,
    citations: Optional[list[str]] = None,
) -> Optional[str]:
    """Convenience wrapper for research traces."""
    return emit_decision_trace(
        kind="research",
        mode=mode,
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"query": query, "sources_count": sources_count, "citations": citations},
    )


def trace_tool_approval(
    tool: str,
    decision: str,
    reason: str,
    risk_level: Optional[str] = None,
    intent: Optional[str] = None,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Convenience wrapper for tool approval traces."""
    return emit_decision_trace(
        kind="tool_approval",
        mode=decision,
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        tool=tool,
        extra={"risk_level": risk_level, **(extra or {})},
    )


def trace_plan_selection(
    intent: str,
    candidate_id: str,
    mode: str,
    reason: str,
    confidence: Optional[float] = None,
    confidence_band: Optional[str] = None,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Convenience wrapper for plan selection traces."""
    return emit_decision_trace(
        kind="plan_selection",
        mode=mode,
        reason=reason,
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        plan_candidate=candidate_id,
        confidence=confidence,
        confidence_band=confidence_band,
    )


def get_recent_traces(
    session_id: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get recent decision traces for debugging."""
    driver = _get_neo4j_driver()
    if not driver:
        return []

    query = "MATCH (d:DecisionTrace)"
    params = {"limit": limit}

    if session_id:
        query += " WHERE d.session_id = $session_id"
        params["session_id"] = session_id

    if kind:
        if session_id:
            query += " AND d.kind = $kind"
        else:
            query += " WHERE d.kind = $kind"
        params["kind"] = kind

    query += " RETURN d ORDER BY d.ts DESC LIMIT $limit"

    try:
        with driver.session() as session:
            result = session.run(query, params)
            return [dict(r["d"]) for r in result]
    except Exception as e:
        logger.warning(f"Failed to get recent traces: {e}")
        return []


# =============================================================================
# CODECRAFT TRACE FUNCTIONS
# =============================================================================


def trace_codecraft_classify(
    specialty: str,
    confidence: float,
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft request classification."""
    return emit_decision_trace(
        kind="codecraft_classify",
        mode=specialty,
        reason=f"confidence_{confidence:.2f}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        confidence=confidence,
    )


def trace_codecraft_retrieve(
    sources: list[str],
    candidates_found: int,
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft retrieval step."""
    return emit_decision_trace(
        kind="codecraft_retrieve",
        mode="|".join(sources),
        reason=f"candidates_{candidates_found}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"candidates_found": candidates_found, "sources": sources},
    )


def trace_codecraft_rank_select(
    selection_mode: str,
    best_score: float,
    best_candidate_id: Optional[str],
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft rank and selection."""
    return emit_decision_trace(
        kind="codecraft_rank_select",
        mode=selection_mode,
        reason=f"score_{best_score:.2f}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"best_score": best_score, "best_candidate_id": best_candidate_id},
    )


def trace_codecraft_plan(
    plan_mode: str,
    tasks_count: int,
    specialty: str,
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft plan decomposition."""
    return emit_decision_trace(
        kind="codecraft_plan",
        mode=plan_mode,
        reason=f"tasks_{tasks_count}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"tasks_count": tasks_count, "specialty": specialty},
    )


def trace_codecraft_compose(
    compose_mode: str,
    chunks_used: list[str],
    diff_lines: int,
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft composition from chunks."""
    return emit_decision_trace(
        kind="codecraft_compose",
        mode=compose_mode,
        reason=f"diff_{diff_lines}_lines",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"chunks_used": chunks_used, "diff_lines": diff_lines},
    )


def trace_codecraft_apply(
    status: str,
    diff_lines: int,
    files_changed: list[str],
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft apply changes."""
    return emit_decision_trace(
        kind="codecraft_apply",
        mode=status,
        reason=f"files_{len(files_changed)}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"diff_lines": diff_lines, "files_changed": files_changed},
    )


def trace_codecraft_verify(
    status: str,
    tests_passed: Optional[int],
    tests_failed: Optional[int],
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft verification step."""
    return emit_decision_trace(
        kind="codecraft_verify",
        mode=status,
        reason=f"passed_{tests_passed}_failed_{tests_failed}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={"tests_passed": tests_passed, "tests_failed": tests_failed},
    )


def trace_codecraft_reuse(
    reuse_type: str,
    source: str,
    adaptation_score: float,
    snippet_id: Optional[str],
    intent: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[str]:
    """Trace codecraft reuse decision."""
    return emit_decision_trace(
        kind="codecraft_reuse",
        mode=reuse_type,
        reason=f"source_{source}_score_{adaptation_score:.2f}",
        session_id=session_id,
        turn_id=turn_id,
        intent=intent,
        extra={
            "source": source,
            "adaptation_score": adaptation_score,
            "snippet_id": snippet_id,
        },
    )
