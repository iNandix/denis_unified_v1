#!/usr/bin/env python3
"""Phase-5 orchestration smoke (cortex + legacy fallback + circuit breaker)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.cortex.adapters.infrastructure_adapter import InfrastructureAdapter
from denis_unified_v1.cortex.world_interface import CortexWorldInterface, WorldEntity
from denis_unified_v1.orchestration.tool_executor import PlannedTool, ToolExecutor, ToolMapping


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-5 orchestration smoke")
    parser.add_argument(
        "--out-json",
        default="/home/jotah/denis_unified_v1/phase5_orchestration_smoke.json",
        help="Output json path",
    )
    return parser.parse_args()


async def _build_executor() -> ToolExecutor:
    os.environ["DENIS_USE_CORTEX"] = "true"
    os.environ["DENIS_USE_ORCHESTRATION_AUG"] = "true"
    os.environ.setdefault("DENIS_PHASE5_LOG_NEO4J", "true")

    legacy_calls: dict[str, int] = {}

    async def legacy_executor(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        legacy_calls[tool_name] = legacy_calls.get(tool_name, 0) + 1
        if tool_name == "legacy.always_fail":
            return {"status": "error", "error": "forced_failure"}
        if tool_name == "legacy.fail_once":
            if legacy_calls[tool_name] == 1:
                return {"status": "error", "error": "transient_failure"}
            return {"status": "ok", "value": "recovered_on_retry", "params": params}
        return {"status": "ok", "value": "legacy_ok", "tool_name": tool_name, "params": params}

    cortex = CortexWorldInterface()
    infra = InfrastructureAdapter()
    cortex.register_adapter("infra", infra)
    for node in ("node2", "nodomac"):
        cortex.register_entity(WorldEntity(entity_id=node, category="infrastructure", source="infra"))

    executor = ToolExecutor(
        legacy_executor=legacy_executor,
        cortex=cortex,
        max_retries=2,
        retry_backoff_sec=0.2,
        circuit_threshold=2,
        circuit_open_sec=45.0,
        default_timeout_sec=8.0,
    )
    executor.register_tool_mapping(
        "infra.perceive.node2",
        ToolMapping(entity_id="node2", mode="perceive"),
    )
    executor.register_tool_mapping(
        "infra.perceive.nodomac",
        ToolMapping(entity_id="nodomac", mode="perceive"),
    )
    return executor


async def run_smoke() -> dict[str, Any]:
    executor = await _build_executor()
    plan_id = f"phase5-{int(datetime.now(timezone.utc).timestamp())}"
    plan = [
        PlannedTool(tool_id="t1", tool_name="infra.perceive.node2"),
        PlannedTool(tool_id="t2", tool_name="infra.perceive.nodomac"),
        PlannedTool(tool_id="t3", tool_name="legacy.echo", params={"message": "hello"}, depends_on=["t1"]),
        PlannedTool(tool_id="t4", tool_name="legacy.fail_once", params={"kind": "retry-check"}, depends_on=["t3"]),
    ]
    plan_result = await executor.execute_plan(plan_id=plan_id, tools=plan)

    circuit_runs: list[dict[str, Any]] = []
    for idx in range(1, 4):
        result = await executor.execute("legacy.always_fail", probe=idx)
        circuit_runs.append(result)

    circuit = executor.snapshot_circuit()
    degraded_observed = bool(circuit.get("open_until_epoch", {}).get("legacy.always_fail"))

    status = "ok"
    if plan_result.get("status") != "success":
        status = "error"
    if not degraded_observed:
        status = "error"

    return {
        "status": status,
        "timestamp_utc": _utc_now(),
        "plan": plan_result,
        "circuit_runs": circuit_runs,
        "circuit_snapshot": circuit,
        "checks": {
            "plan_success": plan_result.get("status") == "success",
            "circuit_degraded_observed": degraded_observed,
        },
    }


def main() -> int:
    args = parse_args()
    payload = asyncio.run(run_smoke())

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote json: {out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
