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


def select_engine_for_intent(
    intent: str,
    task_heavy: bool = False,
    force_booster: bool = False,
) -> Optional[Engine]:
    """
    Select best engine based on role/tier policy.

    Policy:
    1. If intent has PREFERS_ENGINE and active -> use it
    2. If local primary engines healthy (>= 1 active):
       - Heavy tasks -> prefer primary/heavy
       - Light tasks -> prefer booster/free if available, else primary/light
    3. If local unhealthy (no active primary):
       - Use any active engine (degraded mode)
    4. Booster usage:
       - Only when local cluster is healthy (not degraded mode)
       - Marked as 'offload' in telemetry

    Args:
        intent: The intent to select engine for
        task_heavy: True if task requires heavy engine (coding, planning)
        force_booster: Force using booster (for optimization, not failure)
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
            # 0. Check if local cluster is healthy
            result = session.run("""
                MATCH (e:Engine)
                WHERE coalesce(e.status, 'unknown') = 'active' 
                  AND coalesce(e.role, 'primary') = 'primary' 
                  AND coalesce(e.cost_class, 'local') = 'local'
                RETURN count(e) as local_active
            """)
            rec = result.single()
            local_active = rec["local_active"] if rec else 0
            local_healthy = local_active >= 1

            # 1. Intent preference (highest priority)
            result = session.run(
                """
                MATCH (i:Intent {name: $intent})-[p:PREFERS_ENGINE]->(e:Engine)
                WHERE coalesce(e.status, 'unknown') = 'active'
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status, e.role as role, e.tier as tier, e.cost_class as cost_class
                ORDER BY p.reason
                LIMIT 1
            """,
                intent=intent,
            )
            record = result.single()
            if record:
                from denis_unified_v1.actions.decision_trace import (
                    trace_engine_selection,
                )

                trace_engine_selection(
                    intent=intent,
                    engine=record["name"],
                    mode="PRIMARY",
                    reason="intent_preference",
                    local_ok=local_healthy,
                    local_required_active=local_active,
                )
                # Trace routing for intent preference
                endpoint = record["endpoint"] or ""
                network_kind = "unknown"
                if endpoint.startswith("http://10.10.10."):
                    network_kind = "dedicated"
                elif endpoint.startswith("http://192.168."):
                    network_kind = "lan"
                elif "tailscale" in endpoint.lower():
                    network_kind = "tailscale"
                elif endpoint.startswith("http://"):
                    network_kind = "cloud"
                from denis_unified_v1.actions.decision_trace import trace_routing

                trace_routing(
                    interface_kind=network_kind,
                    service_name="intent_preferred",
                    endpoint=endpoint,
                    reason="intent_preference",
                    intent=intent,
                    engine=record["name"],
                )
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )

            # 2. Policy-based selection
            if local_healthy:
                if task_heavy:
                    result = session.run("""
                        MATCH (e:Engine)
                        WHERE coalesce(e.status, 'unknown') = 'active' 
                          AND coalesce(e.tier, 'light') = 'heavy' 
                          AND coalesce(e.role, 'primary') = 'primary'
                        RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                               e.status as status, e.role as role
                        LIMIT 1
                    """)
                elif force_booster:
                    result = session.run("""
                        MATCH (e:Engine)
                        WHERE coalesce(e.status, 'unknown') = 'active' 
                          AND coalesce(e.role, 'primary') = 'booster'
                        RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                               e.status as status, e.role as role
                        LIMIT 1
                    """)
                else:
                    result = session.run("""
                        MATCH (e:Engine)
                        WHERE coalesce(e.status, 'unknown') = 'active' 
                          AND coalesce(e.cost_class, 'local') = 'free'
                        RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                               e.status as status, e.role as role
                        LIMIT 1
                    """)
                    record = result.single()
                    if not record:
                        result = session.run("""
                            MATCH (e:Engine)
                            WHERE coalesce(e.status, 'unknown') = 'active' 
                              AND coalesce(e.tier, 'heavy') = 'light'
                            RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                                   e.status as status, e.role as role
                            LIMIT 1
                        """)
            else:
                logger.warning(
                    f"Local cluster unhealthy ({local_active} active), using degraded mode"
                )
                result = session.run("""
                    MATCH (e:Engine)
                    WHERE coalesce(e.status, 'unknown') = 'active'
                    RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                           e.status as status, e.role as role
                    LIMIT 1
                """)

            record = result.single()
            if record:
                engine_name = record["name"]
                endpoint = record["endpoint"] or ""

                # Determine network kind and trace routing
                network_kind = "unknown"
                service_name = "unknown"
                if endpoint.startswith("http://10.10.10."):
                    network_kind = "dedicated"
                    service_name = "llama_cpp_local"
                elif endpoint.startswith("http://192.168."):
                    network_kind = "lan"
                    service_name = "llama_cpp_lan"
                elif "tailscale" in endpoint.lower():
                    network_kind = "tailscale"
                    service_name = "llama_cpp_tailscale"
                elif endpoint.startswith("http://"):
                    network_kind = "cloud"
                    service_name = "cloud_inference"

                from denis_unified_v1.actions.decision_trace import trace_routing

                trace_routing(
                    interface_kind=network_kind,
                    service_name=service_name,
                    endpoint=endpoint,
                    reason="engine_selected",
                    intent=intent,
                    engine=engine_name,
                )

                mode = (
                    "OFFLOAD"
                    if force_booster
                    else ("DEGRADED" if not local_healthy else "PRIMARY")
                )
                reason = (
                    "heavy_task"
                    if task_heavy
                    else ("booster_requested" if force_booster else "light_task_free")
                )
                if not local_healthy:
                    mode = "DEGRADED"
                    reason = "local_cluster_unhealthy"

                from denis_unified_v1.actions.decision_trace import (
                    trace_engine_selection,
                )

                trace_engine_selection(
                    intent=intent,
                    engine=record["name"],
                    mode=mode,
                    reason=reason,
                    local_ok=local_healthy,
                    local_required_active=local_active,
                )
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )

            # 3. Any active as last resort
            result = session.run("""
                MATCH (e:Engine)
                WHERE coalesce(e.status, 'unknown') = 'active'
                RETURN e.name as name, e.endpoint as endpoint, e.model as model,
                       e.status as status
                LIMIT 1
            """)
            record = result.single()
            if record:
                from denis_unified_v1.actions.decision_trace import (
                    trace_engine_selection,
                )

                trace_engine_selection(
                    intent=intent,
                    engine=record["name"],
                    mode="FALLBACK",
                    reason="no_active_engines",
                    local_ok=False,
                    local_required_active=0,
                )
                return Engine(
                    name=record["name"],
                    endpoint=record["endpoint"] or "",
                    model=record["model"] or "",
                    status=record["status"],
                )

    except Exception as e:
        logger.warning(f"Failed to select engine: {e}")

    return None


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
