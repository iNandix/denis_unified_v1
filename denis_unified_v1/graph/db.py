"""Neo4j database connection utilities."""

import os
from typing import Any, Callable, Optional

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Leon1234$")

_driver = None


def get_driver():
    """Get Neo4j driver instance."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def neo4j_ping() -> bool:
    """Check if Neo4j is reachable."""
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run("RETURN 1 AS n")
            return result.single()["n"] == 1
    except Exception:
        return False


def read_tx(query: str, parameters: Optional[dict] = None) -> list[dict]:
    """Execute a read transaction."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [dict(record) for record in result]


def write_tx(query: str, parameters: Optional[dict] = None) -> list[dict]:
    """Execute a write transaction."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [dict(record) for record in result]


def close():
    """Close the driver connection."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None
