"""
Denis Kernel - Tool Runtime Node
=================================
Executes tools based on Governor decisions.
Includes HASS (Home Assistant) adapter for smart home control.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import logging
import aiohttp

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class HassConfig:
    """Home Assistant connection configuration."""

    host: str = "http://homeassistant.local"
    port: int = 8123
    token: str = ""
    timeout: int = 10
    ws_connected: bool = False


class HassAdapter:
    """
    Home Assistant Adapter - provides tools to interact with HASS.

    MVP Tools:
    - hass.state.snapshot: Get current state of entities
    - hass.entity.search: Search for entities by name
    - hass.service.call: Call a HASS service
    - hass.capabilities: Get what HASS can do
    """

    def __init__(self, config: Optional[HassConfig] = None):
        self.config = config or HassConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._subscriptions: Dict[str, Callable] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
        return self._session

    async def close(self):
        """Close connections."""
        if self._ws:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _api_call(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API call to HASS."""
        url = f"{self.config.host}:{self.config.port}/api/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }

        try:
            session = await self._get_session()
            async with session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    return {"status": "error", "error": f"HTTP {resp.status}: {text}"}
                if resp.content_type == "application/json":
                    return {"status": "success", "data": await resp.json()}
                return {"status": "success", "data": await resp.text()}
        except aiohttp.ClientError as e:
            return {"status": "error", "error": str(e)}
        except Exception as e:
            return {"status": "error", "error": f"Unexpected: {str(e)}"}

    async def get_state_snapshot(
        self, filter_config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Get HASS state snapshot.

        Args:
            filter_config: Optional filter with keys:
                - domain: list of domains (e.g., ["light", "switch"])
                - entity_id: specific entity_id
                - state: filter by state (on, off, etc.)
        """
        result = await self._api_call("GET", "states")

        if result.get("status") != "success":
            return result

        entities = result.get("data", [])

        if filter_config:
            domain_filter = filter_config.get("domain", [])
            entity_filter = filter_config.get("entity_id")
            state_filter = filter_config.get("state")

            if domain_filter:
                entities = [
                    e
                    for e in entities
                    if e.get("entity_id", "").split(".")[0] in domain_filter
                ]
            if entity_filter:
                entities = [
                    e for e in entities if entity_filter in e.get("entity_id", "")
                ]
            if state_filter:
                entities = [e for e in entities if e.get("state") == state_filter]

        return {
            "status": "success",
            "output": {
                "entities": entities,
                "count": len(entities),
                "domains": list(
                    set(e.get("entity_id", "").split(".")[0] for e in entities)
                ),
            },
        }

    async def search_entities(self, query: str) -> Dict[str, Any]:
        """
        Search for entities by friendly name or entity_id.

        Args:
            query: Search string
        """
        result = await self._api_call("GET", "states")

        if result.get("status") != "success":
            return result

        entities = result.get("data", [])
        query_lower = query.lower()

        matches = []
        for entity in entities:
            entity_id = entity.get("entity_id", "")
            friendly_name = entity.get("attributes", {}).get("friendly_name", "")

            if query_lower in entity_id.lower() or query_lower in friendly_name.lower():
                matches.append(
                    {
                        "entity_id": entity_id,
                        "state": entity.get("state"),
                        "friendly_name": friendly_name,
                        "domain": entity_id.split(".")[0],
                    }
                )

        return {
            "status": "success",
            "output": {
                "matches": matches,
                "count": len(matches),
                "query": query,
            },
        }

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Call a HASS service.

        Args:
            domain: Domain (light, switch, climate, etc.)
            service: Service (turn_on, turn_off, etc.)
            entity_id: Target entity
            data: Additional service data
        """
        payload = {}
        if entity_id:
            payload["entity_id"] = entity_id
        if data:
            payload.update(data)

        result = await self._api_call(
            "POST",
            f"services/{domain}/{service}",
            json=payload,
        )

        if result.get("status") != "success":
            return result

        return {
            "status": "success",
            "output": {
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "success": True,
            },
        }

    async def get_capabilities(self) -> Dict[str, Any]:
        """Get HASS capabilities (available services)."""
        result = await self._api_call("GET", "services")

        if result.get("status") != "success":
            return result

        services = result.get("data", {})

        domains = {}
        for domain, domain_services in services.items():
            domains[domain] = list(domain_services.keys())

        return {
            "status": "success",
            "output": {
                "domains": domains,
                "domain_count": len(domains),
                "version": "unknown",
            },
        }


# Global HASS adapter instance
_hass_adapter: Optional[HassAdapter] = None


def get_hass_adapter(config: Optional[HassConfig] = None) -> HassAdapter:
    """Get or create HASS adapter."""
    global _hass_adapter
    if _hass_adapter is None:
        _hass_adapter = HassAdapter(config)
    return _hass_adapter


@dataclass
class ToolDefinition:
    """Tool definition."""

    name: str
    description: str
    parameters: Dict[str, Any]
    requires_approval: bool = False
    async_execute: bool = True
    scope: Optional[str] = None
    risk_tag: Optional[str] = None


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register default tools."""
        self.register(
            ToolDefinition(
                name="time.now",
                description="Get current time",
                parameters={},
                requires_approval=False,
            )
        )
        self.register(
            ToolDefinition(
                name="echo",
                description="Echo back text",
                parameters={"text": {"type": "string"}},
                requires_approval=False,
            )
        )
        self.register(
            ToolDefinition(
                name="file.read",
                description="Read a file",
                parameters={"path": {"type": "string"}},
                requires_approval=True,
            )
        )
        self.register(
            ToolDefinition(
                name="file.list",
                description="List files in directory",
                parameters={"path": {"type": "string"}},
                requires_approval=False,
            )
        )
        self.register(
            ToolDefinition(
                name="deployment.execute",
                description="Execute deployment",
                parameters={"service": {"type": "string"}, "env": {"type": "string"}},
                requires_approval=True,
            )
        )
        # HASS Tools (Home Assistant)
        self.register(
            ToolDefinition(
                name="hass.capabilities",
                description="Get HASS capabilities (available services/domains)",
                parameters={},
                requires_approval=False,
                scope="hass_lights",
            )
        )
        self.register(
            ToolDefinition(
                name="hass.state.snapshot",
                description="Get HASS entity states (all or filtered)",
                parameters={
                    "filter": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "array", "items": {"type": "string"}},
                            "entity_id": {"type": "string"},
                            "state": {"type": "string"},
                        },
                    }
                },
                requires_approval=False,
                scope="hass_lights",
            )
        )
        self.register(
            ToolDefinition(
                name="hass.entity.search",
                description="Search HASS entities by name",
                parameters={"query": {"type": "string"}},
                requires_approval=False,
                scope="hass_lights",
            )
        )
        self.register(
            ToolDefinition(
                name="hass.service.call",
                description="Call HASS service (turn_on, turn_off, etc.)",
                parameters={
                    "domain": {"type": "string"},
                    "service": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "data": {"type": "object"},
                },
                requires_approval=True,
                scope="hass_lights",
            )
        )

    def register(self, tool: ToolDefinition):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """List all tools."""
        return list(self._tools.values())


class ToolExecutor:
    """Executes tools."""

    def __init__(
        self, registry: ToolRegistry, hass_adapter: Optional[HassAdapter] = None
    ):
        self.registry = registry
        self.hass_adapter = hass_adapter or get_hass_adapter()
        self._executors: Dict[str, Callable] = {}
        self._register_default_executors()

    def _register_default_executors(self):
        """Register default tool executors."""
        self.register_executor("time.now", self._exec_time_now)
        self.register_executor("echo", self._exec_echo)
        self.register_executor("file.read", self._exec_file_read)
        self.register_executor("file.list", self._exec_file_list)
        self.register_executor("deployment.execute", self._exec_deployment)
        # HASS executors
        self.register_executor("hass.capabilities", self._exec_hass_capabilities)
        self.register_executor("hass.state.snapshot", self._exec_hass_state_snapshot)
        self.register_executor("hass.entity.search", self._exec_hass_entity_search)
        self.register_executor("hass.service.call", self._exec_hass_service_call)

    def register_executor(self, name: str, func: Callable):
        """Register executor function."""
        self._executors[name] = func

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool."""
        executor = self._executors.get(tool_name)
        if not executor:
            return {"status": "error", "error": f"Tool {tool_name} not found"}

        try:
            if asyncio.iscoroutinefunction(executor):
                result = await executor(params)
            else:
                result = executor(params)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _exec_time_now(self, params: Dict) -> Dict:
        """Execute time.now."""
        now = datetime.now(timezone.utc)
        return {
            "status": "success",
            "output": {
                "utc": now.isoformat(),
                "unix": int(now.timestamp()),
                "timezone": str(now.tzinfo),
            },
        }

    def _exec_echo(self, params: Dict) -> Dict:
        """Execute echo."""
        text = params.get("text", "")
        return {"status": "success", "output": {"echo": text}}

    def _exec_file_read(self, params: Dict) -> Dict:
        """Execute file.read."""
        import os

        path = params.get("path", "")
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read(1000)
                return {
                    "status": "success",
                    "output": {"content": content, "path": path},
                }
            return {"status": "error", "error": f"File not found: {path}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _exec_file_list(self, params: Dict) -> Dict:
        """Execute file.list."""
        import os

        path = params.get("path", ".")
        try:
            files = os.listdir(path)
            return {"status": "success", "output": {"files": files[:20], "path": path}}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _exec_deployment(self, params: Dict) -> Dict:
        """Execute deployment (mock)."""
        service = params.get("service", "unknown")
        env = params.get("env", "prod")
        return {
            "status": "success",
            "output": {
                "service": service,
                "env": env,
                "deployed": True,
                "version": "1.0.0",
            },
        }

    async def _exec_hass_capabilities(self, params: Dict) -> Dict:
        """Execute hass.capabilities."""
        return await self.hass_adapter.get_capabilities()

    async def _exec_hass_state_snapshot(self, params: Dict) -> Dict:
        """Execute hass.state.snapshot."""
        filter_config = params.get("filter")
        return await self.hass_adapter.get_state_snapshot(filter_config)

    async def _exec_hass_entity_search(self, params: Dict) -> Dict:
        """Execute hass.entity.search."""
        query = params.get("query", "")
        return await self.hass_adapter.search_entities(query)

    async def _exec_hass_service_call(self, params: Dict) -> Dict:
        """Execute hass.service.call."""
        domain = params.get("domain", "")
        service = params.get("service", "")
        entity_id = params.get("entity_id")
        data = params.get("data", {})

        if not domain or not service:
            return {"status": "error", "error": "domain and service are required"}

        return await self.hass_adapter.call_service(domain, service, entity_id, data)


class ToolRuntime:
    """
    Tool Runtime node.

    Consumes:
    - policy.route.commit (if route = TOOL)
    - tool.proposal (from plugins)

    Emits:
    - tool.call
    - tool.progress
    - tool.result
    - tool.error
    """

    def __init__(
        self,
        event_bus=None,
        registry: Optional[ToolRegistry] = None,
        hass_adapter: Optional[HassAdapter] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.registry = registry or ToolRegistry()
        self.hass_adapter = hass_adapter or get_hass_adapter()
        self.executor = ToolExecutor(self.registry, self.hass_adapter)

        self._pending_approvals: Dict[str, Dict] = {}

        self._subscribe()
        logger.info(
            f"ToolRuntime initialized with {len(self.registry.list_tools())} tools"
        )

    def _subscribe(self):
        """Subscribe to events."""
        self.event_bus.subscribe("policy.route.commit", self._on_route_commit)
        self.event_bus.subscribe("tool.proposal", self._on_tool_proposal)
        self.event_bus.subscribe("policy.confirm.granted", self._on_confirmation)

    async def _on_route_commit(self, event: Event):
        """Handle route commit - execute tool if route = tool."""
        route_id = event.payload.get("route_id", "")

        if route_id != "tool":
            return

        tool_name: str = event.payload.get("tool_name", "")
        args = event.payload.get("args", {})
        requires_confirmation = event.payload.get("requires_confirmation", False)

        if not tool_name:
            logger.warning(
                f"Tool route committed but no tool_name in payload for {event.trace_id}"
            )
            return

        trace_id = event.trace_id
        session_id = event.session_id

        logger.info(f"Tool route committed: {tool_name} for {trace_id}")

        tool_def = self.registry.get(tool_name)
        if not tool_def:
            await self._emit_error(
                tool_name, trace_id, session_id, f"Tool {tool_name} not found"
            )
            return

        if requires_confirmation or tool_def.requires_approval:
            self._pending_approvals[trace_id] = {
                "tool_name": tool_name,
                "args": args,
                "waiting": True,
            }
            logger.info(f"Tool {tool_name} requires approval for {trace_id}")
            return

        await self._execute_tool(tool_name, args, trace_id, session_id)

    async def _on_tool_proposal(self, event: Event):
        """Handle tool proposal."""
        tool_name: str = event.payload.get("tool_name", "")
        args = event.payload.get("args", {})
        requires_approval = event.payload.get("requires_confirmation", False)

        if not tool_name:
            logger.warning(
                f"tool.proposal received without tool_name for {event.trace_id}"
            )
            return

        trace_id = event.trace_id
        session_id = event.session_id

        tool_def = self.registry.get(tool_name)
        if not tool_def:
            await self._emit_error(
                tool_name, trace_id, session_id, f"Tool {tool_name} not found"
            )
            return

        if requires_approval or tool_def.requires_approval:
            self._pending_approvals[trace_id] = {
                "tool_name": tool_name,
                "args": args,
                "waiting": True,
            }
            logger.info(f"Tool {tool_name} requires approval for {trace_id}")
            return

        await self._execute_tool(tool_name, args, trace_id, session_id)

    async def _on_confirmation(self, event: Event):
        """Handle confirmation granted."""
        trace_id = event.trace_id
        pending = self._pending_approvals.get(trace_id)

        if not pending:
            return

        tool_name: str = pending.get("tool_name", "")
        args = pending.get("args", {})

        if not tool_name:
            return

        await self._execute_tool(
            tool_name,
            args,
            trace_id,
            event.session_id,
        )

        del self._pending_approvals[trace_id]

    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict,
        trace_id: str,
        session_id: str,
    ):
        """Execute a tool."""
        await self._emit_call(tool_name, args, trace_id, session_id)

        result = await self.executor.execute(tool_name, args)

        if result.get("status") == "error":
            await self._emit_error(
                tool_name, trace_id, session_id, result.get("error", "Unknown error")
            )
        else:
            await self._emit_result(tool_name, result, trace_id, session_id)

    async def _emit_call(
        self, tool_name: str, args: Dict, trace_id: str, session_id: str
    ):
        """Emit tool.call event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="tool_runtime",
            type="tool.call",
            priority=-1,
            payload={
                "tool_name": tool_name,
                "args": args,
            },
        )
        await self.event_bus.emit(event)

    async def _emit_result(
        self, tool_name: str, result: Dict, trace_id: str, session_id: str
    ):
        """Emit tool.result event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="tool_runtime",
            type="tool.result",
            priority=0,
            payload={
                "tool_name": tool_name,
                "status": result.get("status", "success"),
                "output": result.get("output", {}),
            },
        )
        await self.event_bus.emit(event)
        logger.info(f"Tool {tool_name} executed for {trace_id}")

    async def _emit_error(
        self, tool_name: str, trace_id: str, session_id: str, error: str
    ):
        """Emit tool.error event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="tool_runtime",
            type="tool.error",
            priority=-2,
            payload={
                "tool_name": tool_name,
                "error": error,
            },
        )
        await self.event_bus.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get runtime stats."""
        return {
            "tools_count": len(self.registry.list_tools()),
            "pending_approvals": len(self._pending_approvals),
        }


# Global instance
_tool_runtime: Optional[ToolRuntime] = None


def get_tool_runtime() -> ToolRuntime:
    """Get or create Tool Runtime."""
    global _tool_runtime
    if _tool_runtime is None:
        _tool_runtime = ToolRuntime()
    return _tool_runtime
