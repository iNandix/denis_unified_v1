import os
import sys

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from denis_unified_v1.graph.db import write_tx, read_tx


class SessionManager:
    def __init__(self, node_id: str = "nodo1"):
        self.node_id = node_id

    def ensure_session(self, session_id: str) -> dict:
        write_tx(
            "MERGE (s:Session {id:$sid}) "
            'ON CREATE SET s.date=date(), s.node=$node, s.status="active", s.created_at=datetime()',
            sid=session_id,
            node=self.node_id,
        )
        return {"session_id": session_id, "node": self.node_id}

    def close_session(self, session_id: str) -> None:
        write_tx(
            'MATCH (s:Session {id:$sid}) SET s.status="closed", s.closed_at=datetime()',
            sid=session_id,
        )

    def get_active_session(self):
        rows = read_tx(
            'MATCH (s:Session {status:"active"}) '
            "RETURN s.id AS id, s.date AS date ORDER BY s.created_at DESC LIMIT 1"
        )
        return rows[0] if rows else None
