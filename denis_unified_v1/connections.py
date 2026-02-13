"""Centralized connection utilities for DENIS.

This module provides single-source functions for:
- Redis connections (sync and async)
- Neo4j connections (sync and async)
- Connection pooling with fail-open behavior

All other modules should import from here instead of redefining these functions.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Optional, Any
from datetime import datetime, timezone

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# Global connection pools (singleton pattern)
_redis_pool: Optional[Any] = None
_neo4j_driver: Optional[Any] = None
_async_neo4j_driver: Optional[Any] = None
_connection_attempts: int = 0
_last_successful_connection: Optional[str] = None

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Leon1234$")


def _log_connection_event(
    event_type: str, service: str, status: str, details: dict = None
):
    """Log structured connection events."""
    global _connection_attempts, _last_successful_connection

    log_data = {
        "event": event_type,
        "service": service,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_attempts": _connection_attempts,
    }

    if status == "success":
        _last_successful_connection = service
        log_data["last_successful"] = _last_successful_connection

    if details:
        log_data.update(details)

    logger.info(json.dumps(log_data))


# ============== REDIS ==============


def get_redis_pool() -> Optional[Any]:
    """Get Redis connection pool (singleton)."""
    global _redis_pool, _connection_attempts
    _connection_attempts += 1

    if _redis_pool is None:
        try:
            import redis

            _redis_pool = redis.ConnectionPool.from_url(
                REDIS_URL, decode_responses=True, max_connections=20
            )
            _log_connection_event("connect", "redis", "success")
        except Exception as e:
            _log_connection_event("connect", "redis", "failed", {"error": str(e)[:100]})
            _redis_pool = None

    return _redis_pool


def get_redis() -> Optional[Any]:
    """Get Redis client from pool (sync)."""
    pool = get_redis_pool()
    if pool:
        try:
            import redis

            return redis.Redis(connection_pool=pool)
        except Exception as e:
            logger.warning(f"Redis client creation failed: {e}")
    return None


async def get_redis_async() -> Optional[Any]:
    """Get async Redis client."""
    try:
        import redis.asyncio as aioredis

        return await aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning(f"Async Redis client creation failed: {e}")
        return None


# ============== NEO4J ==============


def get_neo4j_driver() -> Optional[Any]:
    """Get Neo4j driver (singleton)."""
    global _neo4j_driver, _connection_attempts
    _connection_attempts += 1

    if _neo4j_driver is None:
        try:
            from neo4j import GraphDatabase

            _neo4j_driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            _log_connection_event("connect", "neo4j", "success")
        except Exception as e:
            _log_connection_event("connect", "neo4j", "failed", {"error": str(e)[:100]})
            _neo4j_driver = None
    return _neo4j_driver


def get_neo4j() -> Optional[Any]:
    """Get Neo4j driver (sync version for backward compatibility)."""
    return get_neo4j_driver()


async def get_neo4j_async_driver() -> Optional[Any]:
    """Get async Neo4j driver."""
    global _async_neo4j_driver
    if _async_neo4j_driver is None:
        try:
            from neo4j import AsyncGraphDatabase

            _async_neo4j_driver = await AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            logger.info("Async Neo4j driver initialized")
        except Exception as e:
            logger.warning(f"Async Neo4j driver initialization failed: {e}")
            _async_neo4j_driver = None
    return _async_neo4j_driver


async def get_neo4j_async() -> Optional[Any]:
    """Get async Neo4j driver (backward compatible name)."""
    return await get_neo4j_async_driver()


# ============== HEALTH CHECKS ==============


def check_redis_health() -> dict[str, Any]:
    """Check Redis connection health."""
    try:
        client = get_redis()
        if client:
            client.ping()
            return {"status": "healthy", "service": "redis"}
    except Exception as e:
        return {"status": "unhealthy", "service": "redis", "error": str(e)}
    return {"status": "unavailable", "service": "redis"}


def check_neo4j_health() -> dict[str, Any]:
    """Check Neo4j connection health."""
    try:
        driver = get_neo4j_driver()
        if driver:
            with driver.session() as session:
                result = session.run("RETURN 1")
                result.single()
            return {"status": "healthy", "service": "neo4j"}
    except Exception as e:
        return {"status": "unhealthy", "service": "neo4j", "error": str(e)}
    return {"status": "unavailable", "service": "neo4j"}


async def check_all_connections() -> dict[str, Any]:
    """Check health of all connections."""
    redis_health = check_redis_health()
    neo4j_health = check_neo4j_health()

    return {
        "redis": redis_health,
        "neo4j": neo4j_health,
        "overall": "healthy"
        if redis_health["status"] == "healthy" and neo4j_health["status"] == "healthy"
        else "degraded",
    }


# ============== CLEANUP ==============


def close_all_connections():
    """Close all connection pools (for graceful shutdown)."""
    global _redis_pool, _neo4j_driver, _async_neo4j_driver

    if _redis_pool:
        _redis_pool = None
        logger.info("Redis pool closed")

    if _neo4j_driver:
        _neo4j_driver.close()
        _neo4j_driver = None
        logger.info("Neo4j driver closed")

    # Note: async drivers need to be closed in async context


# Aliases for backward compatibility
get_redis_client = get_redis
