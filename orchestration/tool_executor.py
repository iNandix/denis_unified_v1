"""Phase-5 orchestration executor with legacy fallback and cortex support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import time
from typing import Any, Awaitable, Callable

from denis_unified_v1.cortex.neo4j_config_resolver import ensure_neo4j_env_auto
from denis_unified_v1.cortex.world_interface import CortexWorldInterface


ToolCallable = Callable[[str], Awaitable[dict[str, Any]]] | Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ToolMapping:
    entity_id: str
    mode: str = "act"  # act|perceive
    action: str | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedTool:
    tool_id: str
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    timeout_sec: float | None = None
    fallback_tool_name: str | None = None


class ToolExecutor:
    """Incremental executor: cortex-aware, retry/backoff, circuit-breaker, logging."""

    def __init__(
        self,
        legacy_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        cortex: CortexWorldInterface | None = None,
        *,
        default_timeout_sec: float = 30.0,
        max_retries: int = 3,
        retry_backoff_sec: float = 0.25,
        circuit_threshold: int = 5,
        circuit_open_sec: float = 60.0,
    ) -> None:
        self.legacy_executor = legacy_executor
        self.cortex = cortex
        self.default_timeout_sec = default_timeout_sec
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self.circuit_threshold = circuit_threshold
        self.circuit_open_sec = circuit_open_sec
        self._tool_mappings: dict[str, ToolMapping] = {}
        self._failure_counts: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self._redis_client = None
        self._neo4j_driver = None

    def register_tool_mapping(self, tool_name: str, mapping: ToolMapping) -> None:
        self._tool_mappings[tool_name] = mapping

    def _is_circuit_open(self, tool_name: str) -> bool:
        open_until = self._circuit_open_until.get(tool_name, 0.0)
        if open_until <= 0:
            return False
        return time.time() < open_until

    def _mark_success(self, tool_name: str) -> None:
        self._failure_counts[tool_name] = 0
        self._circuit_open_until.pop(tool_name, None)

    def _mark_failure(self, tool_name: str) -> None:
        count = self._failure_counts.get(tool_name, 0) + 1
        self._failure_counts[tool_name] = count
        if count >= self.circuit_threshold:
            self._circuit_open_until[tool_name] = time.time() + self.circuit_open_sec

    async def _call_cortex(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.cortex is None:
            return {"status": "error", "error": "cortex_not_configured", "tool_name": tool_name}

        mapping = self._tool_mappings.get(tool_name)
        if mapping is None:
            return {"status": "error", "error": "tool_mapping_not_found", "tool_name": tool_name}

        merged = dict(mapping.kwargs)
        merged.update(params or {})

        if mapping.mode == "perceive":
            return await self.cortex.perceive(mapping.entity_id, **merged)

        action = mapping.action or tool_name
        return await self.cortex.act(mapping.entity_id, action=action, **merged)

    async def _call_legacy(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self.legacy_executor(tool_name, params)

    async def _execute_once(
        self,
        tool_name: str,
        params: dict[str, Any],
        timeout_sec: float,
        use_cortex: bool,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if use_cortex:
                coro = self._call_cortex(tool_name, params)
            else:
                coro = self._call_legacy(tool_name, params)
            payload = await asyncio.wait_for(coro, timeout=timeout_sec)
        except asyncio.TimeoutError:
            payload = {"status": "error", "error": "timeout", "tool_name": tool_name}
        except Exception as exc:
            payload = {"status": "error", "error": str(exc), "tool_name": tool_name}

        duration_ms = int((time.perf_counter() - start) * 1000)
        payload = dict(payload or {})
        payload.setdefault("status", "error")
        payload["duration_ms"] = duration_ms
        payload["used_cortex"] = use_cortex
        return payload

    async def execute(self, tool_name: str, **params: Any) -> dict[str, Any]:
        timeout_sec = float(params.pop("timeout_sec", self.default_timeout_sec))
        if self._is_circuit_open(tool_name):
            return {
                "status": "error",
                "error": "circuit_open",
                "tool_name": tool_name,
                "open_until_epoch": self._circuit_open_until.get(tool_name),
            }

        attempts: list[dict[str, Any]] = []
        for attempt in range(1, self.max_retries + 1):
            result = await self._execute_once(
                tool_name=tool_name,
                params=params,
                timeout_sec=timeout_sec,
                use_cortex=False,
            )
            attempts.append({"attempt": attempt, **result})
            if result.get("status") == "ok":
                self._mark_success(tool_name)
                return {
                    "status": "ok",
                    "tool_name": tool_name,
                    "attempts": attempts,
                    "result": result,
                }
            await asyncio.sleep(self.retry_backoff_sec * attempt)

        self._mark_failure(tool_name)
        return {
            "status": "error",
            "tool_name": tool_name,
            "attempts": attempts,
            "error": "legacy_execution_failed",
        }

    async def execute_with_cortex(self, tool_name: str, **params: Any) -> dict[str, Any]:
        timeout_sec = float(params.pop("timeout_sec", self.default_timeout_sec))
        if self._is_circuit_open(tool_name):
            return {
                "status": "error",
                "error": "circuit_open",
                "tool_name": tool_name,
                "open_until_epoch": self._circuit_open_until.get(tool_name),
            }

        orchestration_aug = _bool_env("DENIS_USE_ORCHESTRATION_AUG", False)
        use_cortex = (
            orchestration_aug
            and _bool_env("DENIS_USE_CORTEX", False)
            and tool_name in self._tool_mappings
        )
        attempts: list[dict[str, Any]] = []

        if use_cortex:
            first = await self._execute_once(
                tool_name=tool_name,
                params=params,
                timeout_sec=timeout_sec,
                use_cortex=True,
            )
            attempts.append({"attempt": 1, **first})
            if first.get("status") == "ok":
                self._mark_success(tool_name)
                return {
                    "status": "ok",
                    "tool_name": tool_name,
                    "path": "cortex",
                    "attempts": attempts,
                    "result": first,
                }

        legacy_result = await self.execute(tool_name, timeout_sec=timeout_sec, **params)
        if legacy_result.get("status") == "ok":
            legacy_result["path"] = "cortex_fallback" if use_cortex else "legacy_only"
            if attempts:
                legacy_result["cortex_attempt"] = attempts[0]
            return legacy_result

        self._mark_failure(tool_name)
        out: dict[str, Any] = {
            "status": "error",
            "tool_name": tool_name,
            "path": "cortex_then_legacy" if use_cortex else "legacy_only",
            "error": "all_paths_failed",
            "legacy": legacy_result,
        }
        if attempts:
            out["cortex_attempt"] = attempts[0]
        return out

    def _get_redis(self):
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis

            self._redis_client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
            return self._redis_client
        except Exception:
            self._redis_client = False
            return None

    def _get_neo4j(self):
        if self._neo4j_driver is not None:
            return self._neo4j_driver
        if not _bool_env("DENIS_PHASE5_LOG_NEO4J", True):
            self._neo4j_driver = False
            return None
        try:
            ensure_neo4j_env_auto()
        except Exception:
            pass
        uri = (os.getenv("NEO4J_URI") or "").strip()
        user = (os.getenv("NEO4J_USER") or "neo4j").strip()
        password = (os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "").strip()
        if not uri or not password:
            self._neo4j_driver = False
            return None
        try:
            from neo4j import GraphDatabase

            drv = GraphDatabase.driver(uri, auth=(user, password))
            self._neo4j_driver = drv
            return drv
        except Exception:
            self._neo4j_driver = False
            return None

    def _serialize_short(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        if len(raw) <= 3000:
            return raw
        return raw[:3000]

    def _log_execution(self, plan_id: str, item: dict[str, Any]) -> None:
        ts_ms = int(time.time() * 1000)
        tool_id = str(item.get("tool_id", "unknown"))
        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.zadd(f"execution:{plan_id}", {tool_id: ts_ms})
                redis_client.hset(
                    f"execution:{plan_id}:{tool_id}",
                    mapping={
                        "status": str(item.get("status")),
                        "duration_ms": str(item.get("duration_ms", "")),
                        "tool_name": str(item.get("tool_name", "")),
                        "result": self._serialize_short(item),
                    },
                )
                redis_client.expire(f"execution:{plan_id}", 86400)
                redis_client.expire(f"execution:{plan_id}:{tool_id}", 86400)
            except Exception:
                pass

        driver = self._get_neo4j()
        if not driver:
            return
        try:
            with driver.session() as session:
                session.run(
                    """
                    MERGE (a:Agent {agent_id:'denis'})
                    CREATE (te:ToolExecution {
                        tool_id: $tool_id,
                        tool_name: $tool_name,
                        status: $status,
                        duration_ms: $duration_ms,
                        ts_utc: datetime($ts_utc),
                        plan_id: $plan_id,
                        output: $output
                    })
                    MERGE (a)-[:EXECUTED]->(te)
                    """,
                    tool_id=tool_id,
                    tool_name=str(item.get("tool_name", "")),
                    status=str(item.get("status", "")),
                    duration_ms=int(item.get("duration_ms", 0)),
                    ts_utc=_utc_now(),
                    plan_id=plan_id,
                    output=self._serialize_short(item),
                ).consume()
        except Exception:
            pass

    async def _run_planned_tool(self, planned: PlannedTool) -> dict[str, Any]:
        started = time.perf_counter()
        result = await self.execute_with_cortex(planned.tool_name, **planned.params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = "ok" if result.get("status") == "ok" else "error"
        return {
            "tool_id": planned.tool_id,
            "tool_name": planned.tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "raw": result,
        }

    async def execute_plan(self, plan_id: str, tools: list[PlannedTool]) -> dict[str, Any]:
        plan_start = time.perf_counter()
        by_id = {t.tool_id: t for t in tools}
        done: dict[str, dict[str, Any]] = {}
        pending: set[str] = set(by_id.keys())

        while pending:
            runnable = [
                by_id[tid]
                for tid in sorted(pending)
                if all(dep in done for dep in by_id[tid].depends_on)
            ]
            if not runnable:
                cycle_ids = sorted(pending)
                for tid in cycle_ids:
                    done[tid] = {
                        "tool_id": tid,
                        "tool_name": by_id[tid].tool_name,
                        "status": "error",
                        "duration_ms": 0,
                        "raw": {"status": "error", "error": "dependency_cycle_or_missing"},
                    }
                break

            batch_results = await asyncio.gather(*(self._run_planned_tool(t) for t in runnable))
            for item in batch_results:
                tid = str(item["tool_id"])
                done[tid] = item
                pending.discard(tid)
                self._log_execution(plan_id, item)

        total_duration_ms = int((time.perf_counter() - plan_start) * 1000)
        results = [done[t.tool_id] for t in tools]
        tools_succeeded = sum(1 for r in results if r.get("status") == "ok")
        tools_failed = len(results) - tools_succeeded
        seq_ms = sum(int(r.get("duration_ms", 0)) for r in results)
        parallel_efficiency = round((seq_ms / total_duration_ms), 3) if total_duration_ms > 0 else 0.0
        status = "success" if tools_failed == 0 else "partial_success"
        return {
            "status": status,
            "plan_id": plan_id,
            "tools_executed": len(results),
            "tools_succeeded": tools_succeeded,
            "tools_failed": tools_failed,
            "total_duration_ms": total_duration_ms,
            "parallel_efficiency": parallel_efficiency,
            "results": results,
            "timestamp_utc": _utc_now(),
        }

    def snapshot_circuit(self) -> dict[str, Any]:
        return {
            "failure_counts": dict(self._failure_counts),
            "open_until_epoch": dict(self._circuit_open_until),
            "timestamp_utc": _utc_now(),
        }
