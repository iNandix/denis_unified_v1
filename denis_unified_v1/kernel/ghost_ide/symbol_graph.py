"""SymbolGraph — escribe símbolos en Neo4j y los vincula a sesiones.
Este módulo es el EJE CENTRAL del sistema Denis.
Sin él no hay contexto vivo, no hay harvester, no hay conversación anclada.
"""

import sys
import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")


# ── Upsert básico de símbolo ──────────────────────────────────────────────────
def upsert_symbol(name: str, path: str, kind: str = "function", lineno: int = 0) -> None:
    """Escribe o actualiza un símbolo en Neo4j."""
    from denis_unified_v1.graph.db import write_tx

    write_tx(
        "MERGE (s:Symbol {name:$name, path:$path}) "
        "ON CREATE SET s.kind=$kind, s.lineno=$lineno, s.created_at=datetime() "
        "ON MATCH  SET s.kind=$kind, s.lineno=$lineno, s.updated_at=datetime()",
        {"name": name, "path": path, "kind": kind, "lineno": lineno},
    )


def get_symbols_for_path(path: str) -> list:
    """Retorna todos los símbolos registrados para un path."""
    from denis_unified_v1.graph.db import read_tx

    return read_tx(
        "MATCH (s:Symbol {path:$path}) RETURN s.name AS name, s.kind AS kind, s.lineno AS lineno",
        {"path": path},
    )


def search_symbol(name: str, kind: str = "") -> list:
    """Búsqueda de símbolo por nombre parcial y kind opcional."""
    from denis_unified_v1.graph.db import read_tx

    if kind:
        q = "MATCH (s:Symbol) WHERE s.name CONTAINS $name AND s.kind=$kind RETURN s.name AS name, s.path AS path, s.kind AS kind LIMIT 30"
        return read_tx(q, {"name": name, "kind": kind})
    else:
        q = "MATCH (s:Symbol) WHERE s.name CONTAINS $name RETURN s.name AS name, s.path AS path, s.kind AS kind LIMIT 30"
        return read_tx(q, {"name": name})


# ── Métodos session-aware (EJE del ContextHarvester) ─────────────────────────


def ensure_session(session_id: str, node_id: str = "nodo1") -> None:
    """Crea la sesión en Neo4j si no existe."""
    from denis_unified_v1.graph.db import write_tx

    write_tx(
        "MERGE (s:Session {id:$sid}) "
        'ON CREATE SET s.date=date(), s.node=$node, s.status="active", s.created_at=datetime()',
        {"sid": session_id, "node": node_id},
    )


def link_symbol_to_session(
    symbol_name: str, symbol_path: str, session_id: str, kind: str = "unknown"
) -> None:
    """Vincula un símbolo a una sesión con relación MODIFIED_IN."""
    from denis_unified_v1.graph.db import write_tx

    write_tx(
        "MERGE (sym:Symbol {name:$name, path:$path}) "
        "ON CREATE SET sym.kind=$kind, sym.created_at=datetime() "
        "WITH sym "
        "MERGE (sess:Session {id:$sid}) "
        'ON CREATE SET sess.date=date(), sess.status="active", sess.created_at=datetime() '
        "MERGE (sym)-[:MODIFIED_IN]->(sess)",
        {"name": symbol_name, "path": symbol_path, "kind": kind, "sid": session_id},
    )


def get_session_symbols(session_id: str) -> list:
    """Retorna todos los símbolos vinculados a una sesión."""
    from denis_unified_v1.graph.db import read_tx

    return read_tx(
        "MATCH (sym:Symbol)-[:MODIFIED_IN]->(s:Session {id:$sid}) "
        "RETURN sym.name AS name, sym.path AS path, sym.kind AS kind "
        "ORDER BY sym.name",
        {"sid": session_id},
    )


def get_today_modified_paths(session_id: str) -> list:
    """Paths modificados hoy en la sesión dada."""
    from denis_unified_v1.graph.db import read_tx

    rows = read_tx(
        "MATCH (sym:Symbol)-[:MODIFIED_IN]->(s:Session) "
        "WHERE s.date = date() AND s.id = $sid "
        "RETURN DISTINCT sym.path AS path",
        {"sid": session_id},
    )
    return [r["path"] for r in rows if r.get("path")]


def get_all_sessions_today() -> list:
    """Retorna sesiones activas hoy con conteo de símbolos."""
    from denis_unified_v1.graph.db import read_tx

    return read_tx(
        "MATCH (s:Session) WHERE s.date = date() "
        "OPTIONAL MATCH (sym:Symbol)-[:MODIFIED_IN]->(s) "
        "RETURN s.id AS session_id, s.node AS node, s.status AS status, count(sym) AS n_symbols "
        "ORDER BY s.created_at DESC LIMIT 20"
    )


# ── PRODUCTION FEATURES: Live Learning & Pattern Detection ─────────────────────


def record_execution(
    intent: str, constraints: List[str], tasks: List[str], session_id: str = "default"
) -> None:
    """Registra ejecución para aprendizaje (RedundancyDetector)."""
    from denis_unified_v1.graph.db import write_tx

    task_list = ",".join(tasks[:10]) if tasks else ""
    constraint_list = ",".join(constraints[:5]) if constraints else ""

    write_tx(
        """
        MERGE (e:Execution {intent:$intent, date:date()})
        ON CREATE SET e.count=1, e.tasks=$tasks, e.constraints=$constraints, e.last_session=$session_id
        ON MATCH SET e.count=e.count+1, e.last_session=$session_id
        """,
        {
            "intent": intent,
            "tasks": task_list,
            "constraints": constraint_list,
            "session_id": session_id,
        },
    )


def get_learned_patterns(intent: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Obtiene patrones aprendidos para un intent."""
    from denis_unified_v1.graph.db import read_tx

    results = read_tx(
        """
        MATCH (e:Execution {intent:$intent})
        WHERE e.count >= 2
        RETURN e.tasks AS tasks, e.constraints AS constraints, e.count AS count
        ORDER BY e.count DESC
        LIMIT $limit
        """,
        {"intent": intent, "limit": limit},
    )
    return results


def get_auto_inject_tasks(intent: str, constraints: List[str] = None) -> List[str]:
    """Auto-inyecta tareas aprendidas basándose en intent y constraints."""
    patterns = get_learned_patterns(intent)

    if not patterns:
        return []

    tasks = []
    for p in patterns:
        if p.get("tasks"):
            task_list = p["tasks"].split(",")
            tasks.extend([t.strip() for t in task_list if t.strip()])

    return list(dict.fromkeys(tasks))[:5]


def upsert_repo(repo_id: str, repo_name: str, branch: str, remote_url: str = "") -> None:
    """Registra repositorio en el grafo."""
    from denis_unified_v1.graph.db import write_tx

    write_tx(
        """
        MERGE (r:Repository {repo_id:$repo_id})
        ON CREATE SET r.name=$name, r.branch=$branch, r.remote=$remote, r.created_at=datetime()
        ON MATCH SET r.branch=$branch, r.last_seen=datetime()
        """,
        {"repo_id": repo_id, "name": repo_name, "branch": branch, "remote": remote_url},
    )


def link_symbol_to_intent(symbol_path: str, intent: str, session_id: str = "default") -> None:
    """Vincula un path a un intent para aprender preferencias."""
    from denis_unified_v1.graph.db import write_tx

    write_tx(
        """
        MERGE (sym:Symbol {path:$path})
        WITH sym
        MERGE (i:Intent {name:$intent})
        WITH sym, i
        MERGE (sym)-[:USED_IN]->(i)
        """,
        {"path": symbol_path, "intent": intent},
    )


def get_intent_symbols(intent: str, limit: int = 10) -> List[str]:
    """Obtiene símbolos frecuentemente usados con un intent."""
    from denis_unified_v1.graph.db import read_tx

    results = read_tx(
        """
        MATCH (sym:Symbol)-[:USED_IN]->(i:Intent {name:$intent})
        RETURN sym.path AS path, sym.name AS name
        LIMIT $limit
        """,
        {"intent": intent, "limit": limit},
    )
    return [r["path"] for r in results if r.get("path")]


def record_cp_approval(
    cp_id: str, intent: str, risk_level: str, approved: bool, session_id: str = "default"
) -> None:
    """Registra aprobación de ContextPack para analytics."""
    from denis_unified_v1.graph.db import write_tx

    status = "approved" if approved else "rejected"
    write_tx(
        """
        MERGE (cp:ContextPack {cp_id:$cp_id})
        ON CREATE SET cp.intent=$intent, cp.risk_level=$risk_level, 
                      cp.status=$status, cp.session_id=$session_id, 
                      cp.created_at=datetime()
        ON MATCH SET cp.status=$status
        """,
        {
            "cp_id": cp_id,
            "intent": intent,
            "risk_level": risk_level,
            "status": status,
            "session_id": session_id,
        },
    )


def get_cp_analytics(days: int = 7) -> Dict[str, Any]:
    """Obtiene analytics de ContextPacks."""
    from denis_unified_v1.graph.db import read_tx

    total = read_tx(
        "MATCH (cp:ContextPack) WHERE cp.created_at >= datetime() - duration({days:$days}) RETURN count(cp) AS total",
        {"days": days},
    )
    approved = read_tx(
        "MATCH (cp:ContextPack {status:'approved'}) WHERE cp.created_at >= datetime() - duration({days:$days}) RETURN count(cp) AS approved",
        {"days": days},
    )
    by_intent = read_tx(
        """
        MATCH (cp:ContextPack)
        WHERE cp.created_at >= datetime() - duration({days:$days})
        RETURN cp.intent AS intent, count(cp) AS count
        ORDER BY count DESC
        """,
        {"days": days},
    )

    return {
        "total": total[0]["total"] if total else 0,
        "approved": approved[0]["approved"] if approved else 0,
        "by_intent": [{"intent": r["intent"], "count": r["count"]} for r in by_intent],
    }


def ensure_constraints() -> None:
    """Asegura que las contraintes del grafo existan."""
    from denis_unified_v1.graph.db import write_tx

    write_tx("""
        CREATE CONSTRAINT IF NOT EXISTS FOR (s:Symbol) REQUIRE s.path IS NOT NULL
    """)
    write_tx("""
        CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS NOT NULL
    """)
    write_tx("""
        CREATE CONSTRAINT IF NOT EXISTS FOR (r:Repository) REQUIRE r.repo_id IS NOT NULL
    """)


# ── SymbolGraph wrapper class for OOP usage ──────────────────────────────────


class SymbolGraph:
    """Wrapper class for SymbolGraph operations."""

    def __init__(self):
        self._connected = False

    def verify_connectivity(self) -> bool:
        """Verifica conectividad a Neo4j."""
        from denis_unified_v1.graph.db import neo4j_ping

        self._connected = neo4j_ping()
        return self._connected

    def ensure_session(self, session_id: str, node_id: str = "nodo1") -> None:
        """Wrapper for ensure_session."""
        ensure_session(session_id, node_id)

    def upsert_symbols(self, symbols: List[Any], paths: List[str]) -> None:
        """Upsert multiple symbols."""
        for sym in symbols:
            if hasattr(sym, "symbol"):
                upsert_symbol(sym.symbol.name, sym.file_path, getattr(sym, "kind", "function"), 0)

    def link_symbol_to_session(self, name: str, path: str, session_id: str) -> None:
        """Wrapper for link_symbol_to_session."""
        link_symbol_to_session(name, path, session_id)

    def search(self, name: str, kind: str = "") -> List[Dict]:
        """Search symbols."""
        return search_symbol(name, kind)

    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get full session context."""
        symbols = get_session_symbols(session_id)
        paths = get_today_modified_paths(session_id)
        return {"symbols": symbols, "modified_paths": paths, "session_id": session_id}

    def get_repo_recent_symbols(self, repo_id: str, days: int = 7) -> List[Dict]:
        """Get recent symbols for repo."""
        from denis_unified_v1.graph.db import read_tx

        return read_tx(
            """
            MATCH (sym:Symbol)-[:MODIFIED_IN]->(s:Session)
            WHERE s.date >= date() - duration({days:$days})
            RETURN sym.path AS path, sym.name AS name, sym.kind AS kind
            ORDER BY sym.updated_at DESC
            LIMIT 50
            """,
            {"days": days},
        )

    def close(self) -> None:
        """Close connection."""
        self._connected = False


# ── Singleton helper ──────────────────────────────────────────────────────────

_symbol_graph_instance = None


def get_symbol_graph() -> Optional[SymbolGraph]:
    """Get singleton SymbolGraph instance."""
    global _symbol_graph_instance
    if _symbol_graph_instance is None:
        _symbol_graph_instance = SymbolGraph()
        if not _symbol_graph_instance.verify_connectivity():
            return None
    return _symbol_graph_instance
