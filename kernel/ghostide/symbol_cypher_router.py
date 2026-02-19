"""Symbol Cypher Router - Graph-centric intent routing.

Cypher queries for:
- get_engine_for_intent: Find best engine from Neo4j
- get_symbols_context: Get relevant symbols from graph
- get_implicit_tasks: Detect implicit tasks from session
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EngineMatch:
    """Engine match from graph query."""

    engine_id: str
    model: str
    endpoint: str
    priority: int
    healthy: bool
    vram_used: float
    queue_length: int


@dataclass
class SymbolContext:
    """Symbol context from graph."""

    path: str
    name: str
    kind: str
    line: int
    templates: List[str]


class SymbolCypherRouter:
    """
    Graph-centric routing using Neo4j as source of truth.

    Queries:
    - get_engine_for_intent: Match (Engine)-[:BEST_FOR]->(Intent)
    - get_symbols_context: Match (Symbol)-[:IN_FILE]->(File)
    - get_implicit_tasks: Match (Session)-[:HAS_TASK]->(Task)
    """

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        """Get Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                import os

                uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                logger.warning(f"Neo4j driver failed: {e}")
        return self._driver

    def get_engine_for_intent(self, intent: str, healthy_only: bool = True) -> List[EngineMatch]:
        """
        Get best engine for intent from Neo4j.

        Cypher: MATCH (e:Engine)-[:BEST_FOR]->(i:Intent {name: $intent})
        """
        driver = self._get_driver()
        if not driver:
            return []

        query = """
        MATCH (e:Engine)
        WHERE e.healthy = true
        OPTIONAL MATCH (e)-[r:BEST_FOR]->(i:Intent {name: $intent})
        WITH e, r
        ORDER BY e.priority ASC
        RETURN e.name as engine_id, e.model as model, e.endpoint as endpoint,
               e.priority as priority, e.healthy as healthy,
               e.vram_used_mb as vram_used, e.queue_length as queue_length
        LIMIT 5
        """

        try:
            with driver.session() as session:
                result = session.run(query, intent=intent)
                return [
                    EngineMatch(
                        engine_id=r.get("engine_id"),
                        model=r.get("model", ""),
                        endpoint=r.get("endpoint", ""),
                        priority=r.get("priority", 100),
                        healthy=r.get("healthy", False),
                        vram_used=r.get("vram_used", 0),
                        queue_length=r.get("queue_length", 0),
                    )
                    for r in result
                ]
        except Exception as e:
            logger.warning(f"get_engine_for_intent failed: {e}")
            return []

    def get_symbols_context(
        self, intent: str, session_id: str = None, limit: int = 10
    ) -> List[SymbolContext]:
        """
        Get relevant symbols from graph for intent.

        Cypher: MATCH (s:Symbol)-[:IN_FILE]->(f:File)
                WHERE s.intent CONTAINS $intent
        """
        driver = self._get_driver()
        if not driver:
            return []

        query = """
        MATCH (s:Symbol)
        WHERE s.name CONTAINS $keyword OR s.type = $intent
        """

        if session_id:
            query += """
            MATCH (sess:Session {id: $sessionId})-[:TOUCHES]->(s)
            """

        query += """
        RETURN s.name as name, s.file as path, s.type as kind, s.lineno as line,
               s.templates as templates
        LIMIT $limit
        """

        params = {"keyword": intent, "intent": intent, "sessionId": session_id, "limit": limit}

        try:
            with driver.session() as session:
                result = session.run(query, params)
                return [
                    SymbolContext(
                        path=r.get("path", ""),
                        name=r.get("name", ""),
                        kind=r.get("kind", "unknown"),
                        line=r.get("line", 0),
                        templates=r.get("templates", []) or [],
                    )
                    for r in result
                ]
        except Exception as e:
            logger.warning(f"get_symbols_context failed: {e}")
            return []

    def get_implicit_tasks(self, session_id: str) -> List[str]:
        """
        Get implicit tasks for session from graph.

        Cypher: MATCH (s:Session {id: $sessionId})-[:HAS_TASK]->(t:Task)
        """
        driver = self._get_driver()
        if not driver:
            return []

        query = """
        MATCH (s:Session {id: $sessionId})-[:HAS_TASK|IMPLICIT_TASK]->(t:Task)
        RETURN t.name as task, t.description as description
        """

        try:
            with driver.session() as session:
                result = session.run(query, sessionId=session_id)
                tasks = [r.get("task", "") for r in result if r.get("task")]
                return tasks
        except Exception as e:
            logger.warning(f"get_implicit_tasks failed: {e}")
            return []

    def link_engine_to_intent(self, engine_id: str, intent: str, score: float = 1.0) -> bool:
        """Link engine to intent in graph."""
        driver = self._get_driver()
        if not driver:
            return False

        query = """
        MATCH (e:Engine {name: $engine_id})
        MERGE (i:Intent {name: $intent})
        MERGE (e)-[:BEST_FOR {score: $score}]->(i)
        """

        try:
            with driver.session() as session:
                session.run(query, engine_id=engine_id, intent=intent, score=score)
            return True
        except Exception as e:
            logger.warning(f"link_engine_to_intent failed: {e}")
            return False


# Singleton
_router: Optional[SymbolCypherRouter] = None


def get_symbol_cypher_router() -> SymbolCypherRouter:
    """Get SymbolCypherRouter singleton."""
    global _router
    if _router is None:
        _router = SymbolCypherRouter()
    return _router
