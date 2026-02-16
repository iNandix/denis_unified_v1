"""
Engine Registry - Graph-centric engine discovery and healthcheck.

Provides engine lookup, health monitoring, and selection logic.
Network-aware: prefers dedicated > lan > tailscale for internal services.
"""

from __future__ import annotations

import logging
import time
import httpx
import os
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


class EngineStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# Network priority (lower = better)
NETWORK_PRIORITY = {
    "dedicated": 1,
    "lan": 2,
    "tailscale": 3,
    "cloud": 4,
}


@dataclass
class Engine:
    """Engine definition from graph."""

    name: str
    endpoint: str
    model: str
    status: str
    node: Optional[str] = None
    capabilities: list = None
    last_health_ts: Optional[datetime] = None
    latency_ms: Optional[int] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


def get_engine(name: str) -> Optional[Engine]:
    """Get engine by name from graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.engines_uses_graph:
        return None

    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:Engine {name: $name})
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status, e.node as node, e.capabilities as capabilities,
                       e.last_health_ts as last_health_ts
            """,
                name=name,
            )

            record = result.single()
            if record:
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"] or "unknown",
                    node=record.get("node"),
                    capabilities=record.get("capabilities", []),
                    last_health_ts=record.get("last_health_ts"),
                )
    except Exception as e:
        logger.warning(f"Failed to get engine from graph: {e}")

    return None


def list_engines(status_filter: Optional[str] = None) -> list[Engine]:
    """List all engines from graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.engines_uses_graph:
        return []

    driver = _get_neo4j_driver()
    if not driver:
        return []

    query = """
        MATCH (e:Engine)
    """
    if status_filter:
        query += " WHERE e.status = $status"
        params = {"status": status_filter}
    else:
        params = {}

    query += """
        RETURN DISTINCT e.name as name, e.endpoint as endpoint, e.model as model,
               e.status as status, e.node as node, e.capabilities as capabilities
        ORDER BY e.name
    """

    try:
        with driver.session() as session:
            result = session.run(query, params)
            return [
                Engine(
                    name=r["name"],
                    endpoint=r["endpoint"] or "",
                    model=r["model"] or "",
                    status=r["status"] or "unknown",
                    node=r.get("node"),
                    capabilities=r.get("capabilities", []),
                )
                for r in result
            ]
    except Exception as e:
        logger.warning(f"Failed to list engines: {e}")
        return []


async def healthcheck_engine(
    engine: Engine,
    timeout_s: float = 2.0,
) -> tuple[EngineStatus, int]:
    """
    Healthcheck a single engine.

    Returns (status, latency_ms).
    """
    if not engine.endpoint:
        return EngineStatus.UNKNOWN, 0

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            start = time.time()
            response = await client.get(engine.endpoint.rstrip("/") + "/health")
            latency_ms = int((time.time() - start) * 1000)

            if response.status_code == 200:
                return EngineStatus.ACTIVE, latency_ms
            else:
                return EngineStatus.UNHEALTHY, latency_ms
    except httpx.TimeoutException:
        return EngineStatus.UNHEALTHY, 0
    except Exception as e:
        logger.debug(f"Healthcheck failed for {engine.name}: {e}")
        return EngineStatus.UNKNOWN, 0


async def healthcheck_all_engines() -> dict[str, dict]:
    """Healthcheck all engines and update graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    engines = list_engines()
    results = {}

    for engine in engines:
        status, latency = await healthcheck_engine(engine)
        results[engine.name] = {
            "status": status.value,
            "latency_ms": latency,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Update graph if enabled
        if flags.engines_uses_graph:
            try:
                driver = _get_neo4j_driver()
                if driver:
                    with driver.session() as session:
                        session.run(
                            """
                            MATCH (e:Engine {name: $name})
                            SET e.status = $status,
                                e.last_health_ts = datetime(),
                                e.latency_ms = $latency
                        """,
                            name=engine.name,
                            status=status.value,
                            latency=latency,
                        )
            except Exception as e:
                logger.warning(f"Failed to update engine status: {e}")

    return results


def select_engine_for_intent(intent: str) -> Optional[Engine]:
    """
    Select best engine for an intent based on graph preferences.

    Model: Node -> Service -> Engine
    Priority:
    1. Local node (via DENIS_NODE_NAME env)
    2. Intent preference (PREFERS_ENGINE)
    3. Any active engine
    4. Cloud fallback
    """
    import os
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()
    local_node = os.getenv("DENIS_NODE_NAME", "nodo1")

    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        with driver.session() as session:
            # 1. Try local node first (local-first routing)
            result = session.run(
                """
                MATCH (n:Node {name: $local})-[:HOSTS]->(:Service)-[:PROVIDES]->(e:Engine)
                WHERE e.status = 'active'
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status, n.name as node
                LIMIT 1
            """,
                local=local_node,
            )
            record = result.single()
            if record:
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                    node=record.get("node"),
                )

            # 2. Check intent preferences
            result = session.run(
                """
                MATCH (i:Intent {name: $intent})-[p:PREFERS_ENGINE]->(e:Engine)
                WHERE e.status = 'active'
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status
                ORDER BY p.reason
                LIMIT 1
            """,
                intent=intent,
            )
            record = result.single()
            if record:
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )

            # 3. Any active engine
            result = session.run(
                """
                MATCH (e:Engine)
                WHERE e.status = 'active'
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status
                LIMIT 1
            """
            )
            record = result.single()
            if record:
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )

            # 4. Cloud fallback
            result = session.run(
                """
                MATCH (s:Service {type: 'cloud'})-[:PROVIDES]->(e:Engine)
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status
                LIMIT 1
            """
            )
            record = result.single()
            if record:
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )
    except Exception as e:
        logger.warning(f"Failed to select engine: {e}")

    return None


# Network priority (lower = better)
NETWORK_PRIORITY = {
    "dedicated": 1,
    "lan": 2,
    "tailscale": 3,
    "cloud": 4,
    "unknown": 5,
}


def get_engine_network_kind(engine_name: str) -> str:
    """Get network kind for an engine (dedicated > lan > tailscale > cloud)."""
    driver = _get_neo4j_driver()
    if not driver:
        return "unknown"

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (s:Service)-[:LISTENS_ON]->(i:Interface)<-[:HAS_IFACE]-(n:Node)
                MATCH (s)-[:PROVIDES]->(e:Engine {name: $name})
                RETURN i.kind as kind
                LIMIT 1
            """,
                name=engine_name,
            )

            record = result.single()
            if record and record["kind"]:
                return record["kind"]

            result = session.run(
                """
                MATCH (s:Service {type: 'cloud'})-[:PROVIDES]->(e:Engine {name: $name})
                RETURN 'cloud' as kind
            """,
                name=engine_name,
            )

            record = result.single()
            if record:
                return "cloud"
    except Exception as e:
        logger.debug(f"Failed to get network kind: {e}")

    return "unknown"


def get_engines_by_node(node: str) -> list[Engine]:
    """Get all engines hosted on a specific node."""
    engines = list_engines()
    return [e for e in engines if e.node == node]
