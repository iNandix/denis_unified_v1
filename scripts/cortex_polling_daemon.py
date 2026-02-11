#!/usr/bin/env python3
"""Cortex polling daemon - keeps entity registry synced with real world state.

Features:
- Polls HASS entities every 5s (configurable)
- Polls infrastructure nodes (ping + optional SSH)
- Updates Tailscale IPs dynamically from tailscale status
- Writes status to Redis for downstream consumers
- Supports graceful shutdown via SIGTERM/SIGINT

Usage:
    python3 scripts/cortex_polling_daemon.py --poll-interval 5 --hass-url http://192.168.1.34:8123 --redis-url redis://localhost:6379/0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from denis_unified_v1.cortex.adapters.home_assistant_adapter import HomeAssistantAdapter
from denis_unified_v1.cortex.adapters.infrastructure_adapter import InfrastructureAdapter
from denis_unified_v1.cortex.entity_registry import EntityRegistry
from denis_unified_v1.cortex.world_interface import CortexWorldInterface, WorldEntity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("cortex_daemon")

REDIS_AVAILABLE = True
try:
    import redis
except ImportError:
    REDIS_AVAILABLE = False
    log.warning("redis module not available, Redis publishing disabled")


DEFAULT_POLL_INTERVAL = 5
DEFAULT_HASS_URL = "http://192.168.1.34:8123"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redis_client(redis_url: str):
    if not REDIS_AVAILABLE:
        return None
    try:
        return redis.Redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        log.warning(f"Redis connect failed: {e}")
        return None


def _publish_redis(redis_cli, key: str, data: dict[str, Any], ttl: int = 30) -> None:
    if not redis_cli:
        return
    try:
        redis_cli.setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        log.warning(f"Redis publish failed: {e}")


async def _poll_hass(
    adapter: HomeAssistantAdapter, entity_ids: list[str]
) -> dict[str, Any]:
    """Poll HASS entities and return their states."""
    results: dict[str, Any] = {}
    for entity_id in entity_ids:
        try:
            state = await adapter.perceive(entity_id)
            results[entity_id] = state
        except Exception as e:
            results[entity_id] = {"error": str(e), "entity_id": entity_id}
    return results


async def _poll_infra(
    adapter: InfrastructureAdapter, node_ids: list[str]
) -> dict[str, Any]:
    """Poll infrastructure nodes."""
    results: dict[str, Any] = {}
    for node_id in node_ids:
        try:
            state = await adapter.perceive(node_id)
            results[node_id] = state
        except Exception as e:
            results[node_id] = {"error": str(e), "entity_id": node_id}
    return results


async def run_daemon(
    poll_interval: int,
    hass_url: str,
    redis_url: str,
    hass_token: str | None,
) -> None:
    """Main polling loop."""
    registry = EntityRegistry(default_ttl_seconds=60)
    cortex = CortexWorldInterface()

    ha_adapter = HomeAssistantAdapter()
    infra_adapter = InfrastructureAdapter()

    cortex.register_adapter("hass", ha_adapter)
    cortex.register_adapter("infra", infra_adapter)

    entity_ids = ["light.led_mesa_1", "light.led_mesa_2"]
    node_ids = ["node1", "node2", "node3", "nodomac"]

    for eid in entity_ids:
        registry.upsert(
            entity_id=eid, source="hass", category="home_assistant", metadata={}
        )
        cortex.register_entity(
            WorldEntity(entity_id=eid, category="home_assistant", source="hass")
        )

    for nid in node_ids:
        registry.upsert(
            entity_id=nid, source="infra", category="infrastructure", metadata={}
        )
        cortex.register_entity(
            WorldEntity(entity_id=nid, category="infrastructure", source="infra")
        )

    redis_cli = _redis_client(redis_url)

    shutdown_event = asyncio.Event()

    def signal_handler():
        log.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, signal_handler)

    log.info(f"Starting cortex polling daemon (interval={poll_interval}s)")

    iteration = 0
    while not shutdown_event.is_set():
        iteration += 1
        ts = _utc_now()

        ts_updates = await infra_adapter.refresh_tailscale_ips()
        for node_id, ip in ts_updates.items():
            log.info("Tailscale IP updated: %s -> %s", node_id, ip)

        hass_states, infra_states = await asyncio.gather(
            _poll_hass(ha_adapter, entity_ids),
            _poll_infra(infra_adapter, node_ids),
        )

        snapshot = {
            "ts_utc": ts,
            "iteration": iteration,
            "tailscale_updates": ts_updates,
            "hass": hass_states,
            "infrastructure": infra_states,
            "registry_active": [e.entity_id for e in registry.list_active()],
        }

        log.debug(
            f"Iteration {iteration}: hass={len(hass_states)}, infra={len(infra_states)}"
        )

        if redis_cli:
            _publish_redis(
                redis_cli, "denis:cortex:snapshot", snapshot, ttl=poll_interval + 10
            )
            _publish_redis(
                redis_cli, "denis:cortex:hass", hass_states, ttl=poll_interval + 10
            )
            _publish_redis(
                redis_cli,
                "denis:cortex:infrastructure",
                infra_states,
                ttl=poll_interval + 10,
            )

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            pass

    log.info("Daemon shutdown complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cortex polling daemon")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--hass-url", default=DEFAULT_HASS_URL)
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL)
    parser.add_argument(
        "--hass-token", default=os.getenv("HASS_TOKEN") or os.getenv("HA_TOKEN")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.hass_token:
        os.environ["HASS_TOKEN"] = args.hass_token

    try:
        asyncio.run(
            run_daemon(
                args.poll_interval, args.hass_url, args.redis_url, args.hass_token
            )
        )
    except KeyboardInterrupt:
        log.info("Interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
