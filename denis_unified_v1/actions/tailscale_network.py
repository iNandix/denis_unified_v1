"""
Tailscale Network Module - Graph-centric node discovery via Tailscale.

Provides automatic node/service discovery using Tailscale DERP map.
"""

from __future__ import annotations

import logging
import socket
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Node:
    """Network node discovered via Tailscale."""

    name: str
    ip: str  # Tailscale IP
    hostname: str
    online: bool = True


# Known Tailscale peers (from graph + auto-discovery)
_TAILSCALE_NODES: dict[str, Node] = {}


def discover_nodes_via_tailscale() -> dict[str, Node]:
    """
    Discover nodes from Tailscale.

    In production: use tailscale CLI or API to get peer list.
    For now: load from graph + fallback to known nodes.
    """
    from denis_unified_v1.feature_flags import load_feature_flags
    from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

    flags = load_feature_flags()
    nodes = {}

    # Try graph first
    if flags.engines_uses_graph:
        driver = _get_neo4j_driver()
        if driver:
            try:
                with driver.session() as session:
                    result = session.run("""
                        MATCH (n:Node)
                        RETURN n.name as name, n.ip as ip, n.hostname as hostname
                    """)
                    for record in result:
                        nodes[record["name"]] = Node(
                            name=record["name"],
                            ip=record["ip"] or "",
                            hostname=record["hostname"] or "",
                        )
            except Exception as e:
                logger.warning(f"Failed to get nodes from graph: {e}")

    # Fallback to environment
    nodemac_ip = _resolve_tailscale_ip("nodomac")
    nodo2_ip = _resolve_tailscale_ip("nodo2")

    if nodemac_ip and "nodomac" not in nodes:
        nodes["nodomac"] = Node(name="nodomac", ip=nodemac_ip, hostname="nodomac")
    if nodo2_ip and "nodo2" not in nodes:
        nodes["nodo2"] = Node(name="nodo2", ip=nodo2_ip, hostname="nodo2")

    return nodes


def _resolve_tailscale_ip(hostname: str) -> Optional[str]:
    """Resolve Tailscale IP from hostname."""
    import socket

    try:
        # Try DNS resolution (Tailscale MagicDNS)
        ip = socket.gethostbyname(f"{hostname}.tail-scale.ts.net.")
        return ip
    except socket.gaierror:
        pass

    # Try environment override
    import os

    ip = os.getenv(f"TAILSCALE_{hostname.upper()}_IP")
    if ip:
        return ip

    # Known local node (this machine)
    if hostname.lower() in ("nodo1", "nodomac", "this"):
        return "127.0.0.1"

    return None


def register_node_in_graph(node: Node) -> bool:
    """Register node in graph for tracking."""
    from denis_unified_v1.feature_flags import load_feature_flags
    from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

    flags = load_feature_flags()
    if not flags.engines_uses_graph:
        return False

    driver = _get_neo4j_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (n:Node {name: $name})
                SET n.ip = $ip,
                    n.hostname = $hostname,
                    n.last_seen = datetime()
            """,
                name=node.name,
                ip=node.ip,
                hostname=node.hostname,
            )
        return True
    except Exception as e:
        logger.warning(f"Failed to register node: {e}")
        return False


def get_node_for_service(service_name: str) -> Optional[Node]:
    """
    Get best node for a service based on graph topology.

    Rule: prefer local node, fallback to remote.
    """
    nodes = discover_nodes_via_tailscale()

    if not nodes:
        return None

    # Try to find preferred node from graph
    from denis_unified_v1.feature_flags import load_feature_flags
    from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

    flags = load_feature_flags()
    if flags.engines_uses_graph:
        driver = _get_neo4j_driver()
        if driver:
            try:
                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (s:Service {name: $service_name})-[:HOSTS]-(n:Node)
                        RETURN n.name as name, n.ip as ip, n.hostname as hostname
                        LIMIT 1
                    """,
                        service_name=service_name,
                    )
                    record = result.single()
                    if record and record["name"] in nodes:
                        return nodes[record["name"]]
            except Exception as e:
                logger.warning(f"Failed to get preferred node: {e}")

    # Fallback: first available node
    return list(nodes.values())[0] if nodes else None


def get_service_endpoint(service_name: str, port: int) -> Optional[str]:
    """Get full endpoint URL for a service via Tailscale."""
    node = get_node_for_service(service_name)
    if not node:
        return None
    return f"http://{node.ip}:{port}"
