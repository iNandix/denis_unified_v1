"""CP Queue — Persistent queue for ContextPacks."""

import json
import os
from pathlib import Path
from typing import List, Optional

from control_plane.models import ContextPack


class CPQueue:
    """Persistent queue for ContextPacks."""

    def __init__(self, path: str = "/tmp/denis_cp_queue.json"):
        self.path = path
        self._queue: List[ContextPack] = []
        self._load()

    def _load(self) -> None:
        """Load queue from disk."""
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                    self._queue = [ContextPack.from_dict(d) for d in data]
            except Exception:
                self._queue = []

    def _save(self) -> None:
        """Save queue to disk."""
        data = [cp.to_dict() for cp in self._queue]
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def push(self, cp: ContextPack) -> None:
        """Add ContextPack to queue."""
        if len(self._queue) >= 5:
            self._queue.pop(0)
        self._queue.append(cp)
        self._save()

    def pop(self) -> Optional[ContextPack]:
        """Remove and return first ContextPack."""
        if not self._queue:
            return None
        cp = self._queue.pop(0)
        self._save()
        return cp

    def peek(self) -> Optional[ContextPack]:
        """Return first ContextPack without removing."""
        if self._queue:
            return self._queue[0]
        return None

    def list_pending(self) -> List[ContextPack]:
        """Return copy of queue."""
        return list(self._queue)

    def mark_approved(self, cp_id: str, notes: str = "") -> bool:
        """Mark a ContextPack as approved."""
        for cp in self._queue:
            if cp.cp_id == cp_id:
                cp.human_validated = True
                cp.notes = notes
                self._save()
                self._persist_to_neo4j(cp, "approved")
                return True
        return False

    def mark_rejected(self, cp_id: str, reason: str = "") -> bool:
        """Remove a ContextPack from queue."""
        for i, cp in enumerate(self._queue):
            if cp.cp_id == cp_id:
                self._queue.pop(i)
                self._save()
                self._persist_to_neo4j(cp, "rejected")
                return True
        return False

    def _persist_to_neo4j(self, cp: ContextPack, decision: str) -> None:
        """Persist ContextPack to Neo4j with full context."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                # Get session_id if exists
                session_id = "unknown"
                try:
                    with open("/tmp/denis/session_id.txt") as f:
                        session_id = f.read().strip()
                except:
                    pass

                # Create/merge ContextPack node
                session.run(
                    """
                    MERGE (cp:ContextPack {id: $cpid})
                    SET cp.intent = $intent,
                        cp.mission = $mission,
                        cp.success = $success,
                        cp.decision = $decision,
                        cp.risk = $risk,
                        cp.repo_id = $repo_id,
                        cp.repo_name = $repo_name,
                        cp.branch = $branch,
                        cp.notes = $notes,
                        cp.validated_by = $validated_by,
                        cp.created_at = datetime()
                    """,
                    cpid=cp.cp_id,
                    intent=cp.intent,
                    mission=cp.mission[:200],
                    success=cp.success,
                    decision=decision,
                    risk=cp.risk_level,
                    repo_id=cp.repo_id or "",
                    repo_name=cp.repo_name,
                    branch=cp.branch,
                    notes=cp.notes or "",
                    validated_by=cp.validated_by or "",
                )

                # Link to YoDenisAgent (canonical identity)
                session.run(
                    """
                    MATCH (y:YoDenisAgent)
                    WHERE y.agent_id IS NOT NULL
                    WITH y LIMIT 1
                    MATCH (cp:ContextPack {id: $cpid})
                    MERGE (cp)-[:MANAGED_BY]->(y)
                    """,
                    cpid=cp.cp_id,
                )

                # Optional: link to Session
                if session_id and session_id != "unknown":
                    session.run(
                        """
                        MERGE (s:Session {session_id: $sid})
                        ON CREATE SET s.created_at = datetime()
                        WITH s
                        MATCH (cp:ContextPack {id: $cpid})
                        MERGE (cp)-[:IN_SESSION]->(s)
                        """,
                        sid=session_id,
                        cpid=cp.cp_id,
                    )

            driver.close()
        except Exception:
            pass

    @staticmethod
    def _persist_human_input(delta: dict, cpid: str) -> None:
        """Persist human input to Neo4j."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                session.run(
                    "MERGE (h:HumanInput {cpid: $cpid, timestamp: datetime()}) SET h.raw = $raw, h.constraints = $constraints, h.do_not_touch = $dnt, h.mission_delta = $delta",
                    cpid=cpid,
                    raw=delta.get("raw_preserved", ""),
                    constraints=str(delta.get("new_constraints", [])),
                    dnt=str(delta.get("new_do_not_touch", [])),
                    delta=delta.get("mission_delta", ""),
                )
                session.run(
                    "MATCH (cp:ContextPack {id: $cpid}) MERGE (cp)-[:ENRICHED_BY]->(h)", cpid=cpid
                )
            driver.close()
        except Exception:
            pass

    def purge_expired(self) -> int:
        """Remove expired ContextPacks."""
        original = len(self._queue)
        self._queue = [cp for cp in self._queue if not cp.is_expired()]
        removed = original - len(self._queue)
        if removed > 0:
            self._save()
        return removed

    @staticmethod
    def cleanup_temp_files(max_age_hours: int = 24) -> int:
        """Clean up old temp CP files."""
        import glob
        import time

        temp_patterns = [
            "/tmp/denis_cp_*.json",
            "/tmp/denis_agent_result.json",
        ]

        removed = 0
        now = time.time()
        max_seconds = max_age_hours * 3600

        for pattern in temp_patterns:
            for filepath in glob.glob(pattern):
                try:
                    if os.path.isfile(filepath):
                        age = now - os.path.getmtime(filepath)
                        if age > max_seconds:
                            os.remove(filepath)
                            removed += 1
                except Exception:
                    pass

        return removed


def get_cp_queue() -> CPQueue:
    """Get singleton CPQueue instance."""
    if not hasattr(get_cp_queue, "_instance"):
        get_cp_queue._instance = CPQueue()
    return get_cp_queue._instance


__all__ = ["CPQueue", "get_cp_queue"]
