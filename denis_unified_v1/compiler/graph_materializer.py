"""Compiler graph materializer - fail-open SSoT for Makina pipeline.

Materializa Run/Step/Artifact al grafo desde eventos del compiler.
Usa el GraphClient existente con fail-open.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def materialize_compiler_run(
    trace_id: str,
    run_id: str,
    actor_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    """Materializa un evento del compiler al grafo.

    Crea nodos Run, Step y Artifact según el tipo de evento.
    Returns True si se materializó, False si falló (fail-open).
    """
    try:
        from denis_unified_v1.graph.graph_client import get_graph_client

        gc = get_graph_client()
        if not gc.enabled:
            logger.debug("Graph disabled, skipping materialization")
            return False

        driver = gc._get_driver()
        if not driver:
            logger.debug("Graph driver unavailable, skipping materialization")
            return False

        with driver.session() as session:
            if event_type == "compiler.start":
                _create_run_node(session, run_id, trace_id, actor_id, payload)
                _create_step_node(session, run_id, "compiler_start", payload)

            elif event_type == "retrieval.start":
                _create_step_node(session, run_id, "retrieval_start", payload)

            elif event_type == "retrieval.result":
                _create_step_node(session, run_id, "retrieval_result", payload)

            elif event_type == "compiler.plan":
                _create_step_node(session, run_id, "compiler_plan", payload)

            elif event_type == "compiler.result":
                step_id = _create_step_node(session, run_id, "compiler_result", payload)
                if step_id:
                    _create_artifact_node(session, run_id, step_id, payload)

            elif event_type == "compiler.error":
                _create_step_node(session, run_id, "compiler_error", payload)

        return True

    except Exception as e:
        logger.warning(f"Graph materialization failed (fail-open): {e}")
        return False


def _create_run_node(session, run_id: str, trace_id: str, actor_id: str | None, payload: dict):
    """Crea nodo Run si no existe."""
    query = """
    MERGE (r:Run {id: $run_id})
    SET r.trace_id = $trace_id,
        r.actor_id = $actor_id,
        r.created_at = $created_at,
        r.updated_at = $created_at
    """
    session.run(
        query,
        run_id=run_id,
        trace_id=trace_id,
        actor_id=actor_id or "unknown",
        created_at=_utc_now_iso(),
    )


def _create_step_node(session, run_id: str, step_type: str, payload: dict) -> str | None:
    """Crea nodo Step y lo vincula a Run."""
    step_id = f"{run_id}_{step_type}"

    query = """
    MATCH (r:Run {id: $run_id})
    MERGE (s:Step {id: $step_id})
    SET s.type = $step_type,
        s.trace_id = $trace_id,
        s.created_at = $created_at,
        s.payload_hash = $payload_hash
    WITH r, s
    MERGE (r)-[:HAS_STEP]->(s)
    """
    session.run(
        query,
        run_id=run_id,
        step_id=step_id,
        step_type=step_type,
        trace_id=payload.get("trace_id", ""),
        created_at=_utc_now_iso(),
        payload_hash=_sha256(str(payload)),
    )

    return step_id


def _create_artifact_node(session, run_id: str, step_id: str, payload: dict):
    """Crea nodo Artifact (Makina) y lo vincula a Step."""
    artifact_id = f"{run_id}_makina"

    query = """
    MATCH (s:Step {id: $step_id})
    MERGE (a:Artifact {id: $artifact_id})
    SET a.type = 'makina',
        a.compiler = $compiler,
        a.degraded = $degraded,
        a.confidence = $confidence,
        a.created_at = $created_at,
        a.prompt_hash = $prompt_hash
    WITH s, a
    MERGE (s)-[:PRODUCED]->(a)
    """
    session.run(
        query,
        step_id=step_id,
        artifact_id=artifact_id,
        compiler=payload.get("compiler", "unknown"),
        degraded=payload.get("degraded", False),
        confidence=payload.get("confidence", 0.0),
        created_at=_utc_now_iso(),
        prompt_hash=_sha256(payload.get("prompt_hash_sha256", "")),
    )
