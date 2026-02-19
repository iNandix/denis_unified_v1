import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from denis_unified_v1.graph.db import write_tx, read_tx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_intent(
    agent_id: str,
    session_id: str,
    semantic_delta: Dict[str, Any],
    risk_score: int,
    source_node: str = "nodo1",
) -> str:
    intent_id = f"intent_{uuid.uuid4().hex[:12]}"
    payload = json.dumps(semantic_delta, sort_keys=True, ensure_ascii=False)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    now = _now()
    write_tx(
        """
        MERGE (a:Agent {id: $agent_id})
        MERGE (s:Session {id: $session_id})
          ON CREATE SET s.created_at = $now, s.status = 'active', s.source_node = $source_node
        CREATE (i:Intent {
            id: $intent_id,
            status: 'pending',
            semantic_delta: $payload,
            sha256: $sha256,
            risk_score: $risk_score,
            source_node: $source_node,
            created_at: $now
        })
        MERGE (a)-[:PROPOSES]->(i)
        MERGE (i)-[:IN_SESSION]->(s)
        """,
        {
            "agent_id": agent_id,
            "session_id": session_id,
            "intent_id": intent_id,
            "payload": payload,
            "sha256": sha256,
            "risk_score": risk_score,
            "source_node": source_node,
            "now": now,
        },
    )
    return intent_id


def resolve_intent(
    intent_id: str,
    human_id: str,
    decision: str,
    notes: str = "",
    consult_source: Optional[str] = None,
    corrected_delta: Optional[Dict[str, Any]] = None,
) -> None:
    assert decision in ("approved", "rejected", "corrected"), f"Invalid decision: {decision}"
    severity_map = {"approved": 0, "corrected": 3, "rejected": 7}
    experience_signal = severity_map[decision]
    final_delta = json.dumps(corrected_delta, sort_keys=True) if corrected_delta else None
    now = _now()
    write_tx(
        """
        MATCH (i:Intent {id: $intent_id})
        SET i.status = $decision,
            i.resolved_at = $now,
            i.experience_signal = $experience_signal
        WITH i
        CREATE (h:HumanInput {
            id: randomUUID(),
            human_id: $human_id,
            decision: $decision,
            notes: $notes,
            consult_source: $consult_source,
            corrected_delta: $final_delta,
            experience_signal: $experience_signal,
            created_at: $now
        })
        MERGE (h)-[:RESOLVES]->(i)
        """,
        {
            "intent_id": intent_id,
            "decision": decision,
            "now": now,
            "experience_signal": experience_signal,
            "human_id": human_id,
            "notes": notes,
            "consult_source": consult_source,
            "final_delta": final_delta,
        },
    )


def get_pending_intents(limit: int = 20) -> List[Dict[str, Any]]:
    return read_tx(
        """
        MATCH (i:Intent {status: 'pending'})
        OPTIONAL MATCH (a:Agent)-[:PROPOSES]->(i)
        RETURN i.id AS id, i.semantic_delta AS delta, i.risk_score AS risk,
               i.created_at AS created_at, a.id AS agent_id
        ORDER BY i.created_at ASC
        LIMIT $limit
        """,
        {"limit": limit},
    )


def get_last_n_decisions(n: int = 20) -> List[Dict[str, Any]]:
    return read_tx(
        """
        MATCH (h:HumanInput)-[:RESOLVES]->(i:Intent)-[:IN_SESSION]->(s:Session)
        RETURN i.id AS intent_id, i.status AS decision, h.notes AS notes,
               i.resolved_at AS resolved_at, s.id AS session_id,
               i.experience_signal AS severity
        ORDER BY i.resolved_at DESC
        LIMIT $n
        """,
        {"n": n},
    )
