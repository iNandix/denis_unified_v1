"""WS10-G: Graph-first Intent/Plan/Tasks creation.

This module provides functions to persist user intent and plan in Neo4j graph
as the single source of truth (SSoT).

Flow:
1. create_intent() - creates Intent node with sha256(user_text) + metadata
2. create_plan() - creates Plan node linked to Intent
3. create_specialty_tasks() - creates 4 Tasks (S1-S4) linked to Plan

All functions are fail-open: if Neo4j is unavailable, they return False
and log a metric but do NOT block the chat response.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.guardrails.graph_write_policy import sanitize_graph_props

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


SPECIALTIES = [
    ("S1_CORE_GRAPH_CONTROLROOM", "ws10g_plan_subtask"),
    ("S2_VOICE_PIPECAT", "ws10g_plan_subtask"),
    ("S3_FRONT_UI_VISUALIZATION", "ws10g_plan_subtask"),
    ("S4_GOV_OPS_SAFETY", "ws10g_plan_subtask"),
]


def create_intent(
    *,
    conversation_id: str,
    turn_id: str,
    user_text: str,
    modality: str = "text",
) -> tuple[bool, str | None]:
    """Create Intent node in graph.

    Returns:
        (success, intent_id or None)
    """
    from denis_unified_v1.graph.graph_client import get_graph_client

    gc = get_graph_client()
    if not gc.enabled:
        logger.warning("graph_intent_disabled: cannot create Intent")
        return False, None

    intent_id = _sha256(f"{conversation_id}:{turn_id}")
    user_text_hash = _sha256(user_text)
    user_text_len = len(user_text)
    ts = _utc_now_iso()

    safe_props = {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "ts": ts,
        "user_text_sha256": user_text_hash,
        "user_text_len": user_text_len,
        "user_text_preview": f"[redacted:{user_text_len}chars]" if user_text_len > 0 else "",
        "modality": modality,
        "status": "planned",
    }
    safe_props = sanitize_graph_props(safe_props).props

    cypher = """
    MERGE (i:Intent {id: $id})
    SET i.conversation_id = $conversation_id,
        i.turn_id = $turn_id,
        i.ts = $ts,
        i.user_text_sha256 = $user_text_sha256,
        i.user_text_len = $user_text_len,
        i.user_text_preview = $user_text_preview,
        i.modality = $modality,
        i.status = $status
    """

    ok = gc.run_write(
        cypher,
        {
            "id": intent_id,
            **safe_props,
            "ts": ts,
        },
    )

    if ok:
        logger.info(f"graph_intent_created: {intent_id}")
    else:
        logger.warning(f"graph_intent_failed: {intent_id}")

    return ok, intent_id if ok else None


def create_plan(
    *,
    intent_id: str,
    specialties: list[str] | None = None,
    no_overlap_contract_hash: str = "",
) -> tuple[bool, str | None]:
    """Create Plan node linked to Intent.

    Returns:
        (success, plan_id or None)
    """
    from denis_unified_v1.graph.graph_client import get_graph_client

    gc = get_graph_client()
    if not gc.enabled:
        logger.warning("graph_plan_disabled: cannot create Plan")
        return False, None

    plan_id = f"{intent_id}:plan"
    specialties = specialties or ["S1", "S2", "S3", "S4"]
    ts = _utc_now_iso()

    cypher = """
    MATCH (i:Intent {id: $intent_id})
    MERGE (p:Plan {id: $plan_id})
    SET p.intent_id = $intent_id,
        p.ts = $ts,
        p.status = 'active',
        p.specialties = $specialties,
        p.no_overlap_contract_hash = $no_overlap_contract_hash
    MERGE (i)-[:HAS_PLAN]->(p)
    """

    ok = gc.run_write(
        cypher,
        {
            "intent_id": intent_id,
            "plan_id": plan_id,
            "ts": ts,
            "specialties": specialties,
            "no_overlap_contract_hash": no_overlap_contract_hash,
        },
    )

    if ok:
        logger.info(f"graph_plan_created: {plan_id}")
    else:
        logger.warning(f"graph_plan_failed: {plan_id}")

    return ok, plan_id if ok else None


def create_specialty_tasks(
    *,
    plan_id: str,
    intent_id: str,
    conversation_id: str,
    turn_id: str,
    payload_redacted_hash: str = "",
) -> tuple[bool, list[str]]:
    """Create 4 Tasks (one per specialty) linked to Plan.

    Returns:
        (success, list of task_ids)
    """
    from denis_unified_v1.graph.graph_client import get_graph_client

    gc = get_graph_client()
    if not gc.enabled:
        logger.warning("graph_tasks_disabled: cannot create Tasks")
        return False, []

    ts = _utc_now_iso()
    task_ids: list[str] = []

    for specialty, reason_safe in SPECIALTIES:
        task_id = f"{plan_id}:task:{specialty}"

        cypher = """
        MATCH (p:Plan {id: $plan_id})
        MERGE (t:Task {id: $task_id})
        SET t.type = 'backfill',
            t.status = 'queued',
            t.reason_safe = $reason_safe,
            t.specialty = $specialty,
            t.conversation_id = $conversation_id,
            t.turn_id = $turn_id,
            t.intent_id = $intent_id,
            t.plan_id = $plan_id,
            t.payload_redacted_hash = $payload_redacted_hash,
            t.created_ts = $ts,
            t.updated_ts = $ts
        MERGE (p)-[rel:HAS_TASK]->(t)
        SET rel.specialty = $specialty
        """

        ok = gc.run_write(
            cypher,
            {
                "plan_id": plan_id,
                "task_id": task_id,
                "specialty": specialty,
                "reason_safe": reason_safe,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "intent_id": intent_id,
                "payload_redacted_hash": payload_redacted_hash,
                "ts": ts,
            },
        )

        if ok:
            task_ids.append(task_id)
            logger.info(f"graph_task_created: {task_id}")
        else:
            logger.warning(f"graph_task_failed: {task_id}")

    return len(task_ids) == 4, task_ids


def create_intent_plan_tasks(
    *,
    conversation_id: str,
    turn_id: str,
    user_text: str,
    modality: str = "text",
) -> dict[str, Any]:
    """Full WS10-G flow: create Intent + Plan + 4 Tasks.

    This is the main entry point for the frontdoor hook.

    Returns:
        dict with keys: success, intent_id, plan_id, task_ids, warning
    """
    result = {
        "success": False,
        "intent_id": None,
        "plan_id": None,
        "task_ids": [],
        "warning": None,
    }

    ok, intent_id = create_intent(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_text=user_text,
        modality=modality,
    )

    if not ok or not intent_id:
        result["warning"] = "graph_unavailable"
        return result

    intent_id_str: str = intent_id
    ok, plan_id = create_plan(intent_id=intent_id_str)

    if not ok or not plan_id:
        result["warning"] = "plan_creation_failed"
        return result

    plan_id_str: str = plan_id
    ok, task_ids = create_specialty_tasks(
        plan_id=plan_id_str,
        intent_id=intent_id_str,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )

    if not ok:
        result["warning"] = "tasks_creation_failed"
        return result

    result["success"] = True
    result["intent_id"] = intent_id
    result["plan_id"] = plan_id
    result["task_ids"] = task_ids

    return result
