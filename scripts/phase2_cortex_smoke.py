#!/usr/bin/env python3
"""Phase-2 cortex smoke checks (wrapper-only, legacy-safe)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.cortex.adapters.home_assistant_adapter import HomeAssistantAdapter
from denis_unified_v1.cortex.adapters.infrastructure_adapter import (
    InfrastructureAdapter,
)
from denis_unified_v1.cortex.entity_registry import EntityRegistry
from denis_unified_v1.cortex.world_interface import CortexWorldInterface, WorldEntity


async def run_smoke(execute: bool) -> dict[str, Any]:
    registry = EntityRegistry(default_ttl_seconds=600)
    cortex = CortexWorldInterface()
    ha_adapter = HomeAssistantAdapter()
    infra_adapter = InfrastructureAdapter()

    cortex.register_adapter("hass", ha_adapter)
    cortex.register_adapter("infra", infra_adapter)

    entities = [
        WorldEntity(
            entity_id="light.led_mesa_1", category="home_assistant", source="hass"
        ),
        WorldEntity(
            entity_id="light.led_mesa_2", category="home_assistant", source="hass"
        ),
        WorldEntity(entity_id="node1", category="infrastructure", source="infra"),
        WorldEntity(entity_id="node2", category="infrastructure", source="infra"),
        WorldEntity(entity_id="node3", category="infrastructure", source="infra"),
        WorldEntity(entity_id="nodomac", category="infrastructure", source="infra"),
    ]
    for ent in entities:
        registry.upsert(
            entity_id=ent.entity_id,
            source=ent.source,
            category=ent.category,
            metadata={},
        )
        cortex.register_entity(ent)

    output: dict[str, Any] = {
        "status": "ok",
        "mode": "execute" if execute else "dry_run",
        "registry_active": [e.entity_id for e in registry.list_active()],
        "adapter_info": {"hass": ha_adapter.describe()},
        "checks": [],
    }

    try:
        if not execute:
            output["checks"].append(
                {
                    "check": "dry_run",
                    "result": "No external calls executed in dry-run mode.",
                }
            )
            return output

        output["checks"].append(
            {
                "check": "perceive_hass",
                "result": await cortex.perceive("light.led_mesa_1", domain="light"),
            }
        )
        output["checks"].append(
            {"check": "perceive_node1", "result": await cortex.perceive("node1")}
        )
        output["checks"].append(
            {"check": "perceive_node2", "result": await cortex.perceive("node2")}
        )
        output["checks"].append(
            {"check": "perceive_node3", "result": await cortex.perceive("node3")}
        )
        output["checks"].append(
            {"check": "perceive_nodomac", "result": await cortex.perceive("nodomac")}
        )
        return output
    finally:
        try:
            import ha_async_client  # type: ignore

            close_fn = getattr(ha_async_client, "close_ha_client", None)
            if close_fn is not None:
                await close_fn()
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cortex smoke checks")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute real perceive calls (HASS + infra).",
    )
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase2_cortex_smoke.json",
        help="Output report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_smoke(execute=args.execute))
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote json: {out}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
