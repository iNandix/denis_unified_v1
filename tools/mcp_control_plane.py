#!/usr/bin/env python3
"""
Control Plane MCP Tools.

Exposes control plane operations as MCP tools for approval workflow.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

REPO_PATH = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
sys.path.insert(0, str(REPO_PATH))


class ToolResult(BaseModel):
    success: bool
    result: str
    error: Optional[str] = None


class ControlPlaneTools:
    """Control Plane tools for approval workflow."""

    def __init__(self):
        self.cp_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8765")
        self.tools = {
            # ============ INTENT MANAGEMENT ============
            "cp_submit_intent": {
                "description": "Submit intent for human approval",
                "risk": "medium",
                "parameters": {
                    "action": {"type": "string"},
                    "risk_score": {"type": "integer", "default": 5},
                    "details": {"type": "string", "default": ""},
                },
                "fn": self.submit_intent,
            },
            "cp_check_pending": {
                "description": "List pending intents",
                "risk": "low",
                "parameters": {"limit": {"type": "integer", "default": 20}},
                "fn": self.check_pending,
            },
            "cp_check_decisions": {
                "description": "List recent decisions",
                "risk": "low",
                "parameters": {"n": {"type": "integer", "default": 20}},
                "fn": self.check_decisions,
            },
            "cp_resolve_intent": {
                "description": "Resolve intent (approve/reject)",
                "risk": "medium",
                "parameters": {
                    "intent_id": {"type": "string"},
                    "decision": {"type": "string"},
                    "notes": {"type": "string", "default": ""},
                },
                "fn": self.resolve_intent,
            },
            "cp_get_intent": {
                "description": "Get intent details by ID",
                "risk": "low",
                "parameters": {"intent_id": {"type": "string"}},
                "fn": self.get_intent,
            },
            # ============ AGENT MANAGEMENT ============
            "cp_register_agent": {
                "description": "Register new agent in control plane",
                "risk": "medium",
                "parameters": {
                    "agent_id": {"type": "string"},
                    "name": {"type": "string"},
                    "capabilities": {"type": "string", "default": "[]"},
                },
                "fn": self.register_agent,
            },
            "cp_list_agents": {
                "description": "List all registered agents",
                "risk": "low",
                "parameters": {},
                "fn": self.list_agents,
            },
            # ============ SESSION MANAGEMENT ============
            "cp_create_session": {
                "description": "Create new session for agent",
                "risk": "low",
                "parameters": {"agent_id": {"type": "string"}},
                "fn": self.create_session,
            },
            "cp_get_session": {
                "description": "Get session context",
                "risk": "low",
                "parameters": {"session_id": {"type": "string"}},
                "fn": self.get_session,
            },
            # ============ POLICY CHECKS ============
            "cp_check_policy": {
                "description": "Check if action is allowed by policy",
                "risk": "low",
                "parameters": {
                    "action": {"type": "string"},
                    "agent_id": {"type": "string", "default": ""},
                },
                "fn": self.check_policy,
            },
            # ============ SYSTEM ============
            "cp_health": {
                "description": "Control plane health check",
                "risk": "low",
                "parameters": {},
                "fn": self.health_check,
            },
            "cp_metrics": {
                "description": "Get control plane metrics",
                "risk": "low",
                "parameters": {},
                "fn": self.get_metrics,
            },
        }

    def submit_intent(self, action: str, risk_score: int = 5, details: str = "") -> ToolResult:
        try:
            resp = httpx.post(
                f"{self.cp_url}/intent",
                json={
                    "agent_id": "pearai_agent",
                    "session_id": "pearai-session",
                    "semantic_delta": {"action": action, "details": details},
                    "risk_score": risk_score,
                    "source_node": "pearai",
                },
                timeout=10.0,
            )
            if resp.status_code == 201:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"submit_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def check_pending(self, limit: int = 20) -> ToolResult:
        try:
            resp = httpx.get(f"{self.cp_url}/intent/pending?limit={limit}", timeout=10.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"check_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def check_decisions(self, n: int = 20) -> ToolResult:
        try:
            resp = httpx.get(f"{self.cp_url}/intent/decisions?n={n}", timeout=10.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"check_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def resolve_intent(self, intent_id: str, decision: str, notes: str = "") -> ToolResult:
        if decision not in ("approved", "rejected", "corrected"):
            return ToolResult(success=False, result="", error="Invalid decision")
        try:
            resp = httpx.post(
                f"{self.cp_url}/intent/{intent_id}/resolve",
                json={"human_id": "pearai", "decision": decision, "notes": notes},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"resolve_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def get_intent(self, intent_id: str) -> ToolResult:
        try:
            resp = httpx.get(f"{self.cp_url}/intent/{intent_id}", timeout=10.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"not_found: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def register_agent(self, agent_id: str, name: str, capabilities: str = "[]") -> ToolResult:
        try:
            caps = (
                json.loads(capabilities)
                if capabilities.startswith("[")
                else capabilities.split(",")
            )
            # Register in Neo4j
            neo4j_url = (
                os.getenv("NEO4J_URI", "bolt://localhost:7687")
                .replace("bolt", "http")
                .replace("7687", "7474")
            )
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "Leon1234$")

            resp = httpx.post(
                f"{neo4j_url}/db/neo4j/tx/commit",
                headers={"Content-Type": "application/json"},
                auth=(neo4j_user, neo4j_pass),
                json={
                    "statements": [
                        {
                            "statement": "MERGE (a:Agent {id: $id}) SET a.name = $name, a.capabilities = $caps RETURN a.id",
                            "parameters": {"id": agent_id, "name": name, "caps": caps},
                        }
                    ]
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                return ToolResult(success=True, result=f"Agent {agent_id} registered")
            return ToolResult(success=False, result="", error="registration_failed")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def list_agents(self) -> ToolResult:
        try:
            neo4j_url = (
                os.getenv("NEO4J_URI", "bolt://localhost:7687")
                .replace("bolt", "http")
                .replace("7687", "7474")
            )
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "Leon1234$")

            resp = httpx.post(
                f"{neo4j_url}/db/neo4j/tx/commit",
                headers={"Content-Type": "application/json"},
                auth=(neo4j_user, neo4j_pass),
                json={
                    "statements": [
                        {
                            "statement": "MATCH (a:Agent) RETURN a.id as id, a.name as name, a.capabilities as caps"
                        }
                    ]
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error="query_failed")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def create_session(self, agent_id: str) -> ToolResult:
        import uuid

        session_id = str(uuid.uuid4())
        return ToolResult(
            success=True, result=json.dumps({"session_id": session_id, "agent_id": agent_id})
        )

    def get_session(self, session_id: str) -> ToolResult:
        return ToolResult(success=True, result=f"Session: {session_id}")

    def check_policy(self, action: str, agent_id: str = "") -> ToolResult:
        # Simple policy check - can be expanded
        high_risk_actions = ["delete", "drop", "rm -rf", "systemctl restart"]
        for hra in high_risk_actions:
            if hra in action.lower():
                return ToolResult(
                    success=True,
                    result=json.dumps({"allowed": False, "reason": "high_risk_action"}),
                )
        return ToolResult(success=True, result=json.dumps({"allowed": True}))

    def health_check(self) -> ToolResult:
        try:
            resp = httpx.get(f"{self.cp_url}/health", timeout=5.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error="cp_down")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def get_metrics(self) -> ToolResult:
        try:
            resp = httpx.get(f"{self.cp_url}/metrics", timeout=5.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=True, result="{}")
        except Exception:
            return ToolResult(success=True, result="{}")

    def get_tools_schema(self) -> list:
        tools = []
        for name, spec in self.tools.items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "risk": spec.get("risk", "unknown"),
                    "inputSchema": {"type": "object", "properties": spec["parameters"]},
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.tools:
            return {"success": False, "error": f"unknown_tool: {name}"}

        spec = self.tools[name]
        fn = spec["fn"]
        params = {k: v for k, v in arguments.items() if k in spec["parameters"]}

        import inspect

        if inspect.iscoroutinefunction(fn):
            result = await fn(**params)
        else:
            result = fn(**params)

        return (
            result.model_dump()
            if hasattr(result, "model_dump")
            else {"success": True, "result": str(result)}
        )


# ============ FASTAPI APP ============

app = FastAPI(title="Denis Control Plane MCP", version="1.0.0")
cp_tools = ControlPlaneTools()


@app.get("/health")
def health():
    return {"status": "ok", "tools": len(cp_tools.tools)}


@app.get("/tools")
def list_tools():
    return {"tools": cp_tools.get_tools_schema()}


@app.post("/tools/{tool_name}/call")
async def call_tool(tool_name: str, arguments: dict = {}):
    return await cp_tools.call_tool(tool_name, arguments)


@app.post("/mcp/tools/list")
async def mcp_list_tools():
    return {"tools": cp_tools.get_tools_schema()}


@app.post("/mcp/tools/call")
async def mcp_call_tool(request: dict):
    tool_name = request.get("name")
    arguments = request.get("arguments", {})
    result = await cp_tools.call_tool(tool_name, arguments)
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


if __name__ == "__main__":
    port = int(os.getenv("CP_MCP_PORT", "9102"))
    uvicorn.run(app, host="0.0.0.0", port=port)
