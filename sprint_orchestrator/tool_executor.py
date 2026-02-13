"""Tool executor for local tools (qcli, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from sprint_orchestrator.event_bus import EventBus, publish_event
from sprint_orchestrator.models import SprintEvent
from sprint_orchestrator.session_store import SessionStore
from sprint_orchestrator.qcli_integration import get_qcli
import asyncio


class ToolExecutor:
    """Executes local tool calls (qcli, etc.)"""

    def __init__(self, config, store: SessionStore, bus: EventBus | None = None):
        self.config = config
        self.store = store
        self.bus = bus
        self.qcli = get_qcli()

    async def execute(
        self, session_id: str, worker_id: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch and execute a tool call."""
        publish_event(
            self.store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="tool.execute.start",
                message=f"Executing tool: {tool_name}",
                payload={"tool": tool_name, "arguments": arguments},
            ),
            self.bus,
        )

        try:
            if tool_name.startswith("qcli."):
                result = await self._execute_qcli(tool_name, arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")

            publish_event(
                self.store,
                SprintEvent(
                    session_id=session_id,
                    worker_id=worker_id,
                    kind="tool.execute.done",
                    message=f"Tool {tool_name} completed",
                    payload={"result": result},
                ),
                self.bus,
            )
            return result
        except Exception as exc:
            publish_event(
                self.store,
                SprintEvent(
                    session_id=session_id,
                    worker_id=worker_id,
                    kind="tool.execute.error",
                    message=f"Tool {tool_name} failed: {exc}",
                    payload={"error": str(exc)},
                ),
                self.bus,
            )
            raise

    async def _execute_qcli(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute qcli tool."""
        if tool_name == "qcli.search":
            query = arguments.get("query", "")
            limit = int(arguments.get("limit", 20))
            results = self.qcli.search(query=query, limit=limit)
            return {
                "status": "ok",
                "query": query,
                "total": len(results.get("results", [])),
                "summary": results.get("summary", ""),
                "results": results.get("results", [])[:limit],
            }
        elif tool_name == "qcli.crossref":
            symbol = arguments.get("symbol", "")
            file = arguments.get("file")
            refs = self.qcli.crossref(symbol=symbol, file=file)
            return {"status": "ok", "refs": refs}
        elif tool_name == "qcli.context":
            ctx = self.qcli.context()
            return {"status": "ok", "context": ctx}
        elif tool_name == "qcli.index":
            paths = arguments.get("paths", [])
            result = self.qcli.index_project(
                paths=[Path(p) for p in paths] if paths else None
            )
            return {"status": "ok", "result": result}
        else:
            raise ValueError(f"Unknown qcli tool: {tool_name}")
