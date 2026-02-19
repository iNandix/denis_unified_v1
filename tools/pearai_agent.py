#!/usr/bin/env python3
"""
Denis Agent for PearAI.

This agent integrates with PearAI to provide Denis's capabilities as a premium code agent.
It connects to the MCP server and Control Plane for full Denis functionality.

Usage:
    python tools/pearai_agent.py [--port PORT] [--api-url URL]

Or as a module:
    from tools.pearai_agent import PearAIDenisAgent
    agent = PearAIDenisAgent()
    response = agent.chat("Create a new file called hello.py")
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

REPO_PATH = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
sys.path.insert(0, str(REPO_PATH))


class DenisCapabilities:
    """Denis tool capabilities mapped to MCP tools."""

    TOOL_MAPPING = {
        # File operations
        "read_file": "denis_read_file",
        "write_file": "denis_write_file",
        "edit_file": "denis_edit_file",
        "list_dir": "denis_list_dir",
        # Search
        "grep": "denis_grep",
        "glob": "denis_glob",
        "search_symbol": "denis_search_symbol",
        # Git
        "git_status": "denis_git_status",
        "git_diff": "denis_git_diff",
        "git_log": "denis_git_log",
        # Knowledge
        "query_graph": "denis_query_graph",
        "search_memory": "denis_search_memory",
        # Control Plane
        "submit_intent": "denis_submit_intent",
        "check_intents": "denis_check_pending_intents",
        # Execution
        "execute": "denis_execute",
    }

    RISK_LEVELS = {
        "denis_read_file": "LOW",
        "denis_list_dir": "LOW",
        "denis_grep": "LOW",
        "denis_glob": "LOW",
        "denis_search_symbol": "LOW",
        "denis_git_status": "LOW",
        "denis_git_diff": "LOW",
        "denis_git_log": "LOW",
        "denis_query_graph": "LOW",
        "denis_search_memory": "LOW",
        "denis_write_file": "HIGH",
        "denis_edit_file": "HIGH",
        "denis_execute": "CRITICAL",
        "denis_submit_intent": "MEDIUM",
    }

    @classmethod
    def get_tool_for_capability(cls, capability: str) -> str:
        return cls.TOOL_MAPPING.get(capability, capability)

    @classmethod
    def get_risk_level(cls, tool_name: str) -> str:
        return cls.RISK_LEVELS.get(tool_name, "UNKNOWN")


class PearAIDenisAgent:
    """Denis Agent for PearAI integration."""

    def __init__(
        self,
        mcp_url: str = "http://localhost:9101",
        api_url: str = "http://localhost:9100",
        control_plane_url: str = "http://localhost:8765",
        session_id: str = None,
        user_id: str = "pearai_user",
    ):
        self.mcp_url = mcp_url
        self.api_url = api_url
        self.cp_url = control_plane_url
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id
        self.capabilities = DenisCapabilities()
        self.conversation_history = []

    async def call_mcp_tool(self, tool_name: str, arguments: dict = None) -> dict:
        """Call an MCP tool directly."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.mcp_url}/tools/{tool_name}/call", json={"arguments": arguments or {}}
                )
                return response.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def chat(self, message: str, context: dict = None) -> dict:
        """
        Main chat interface for PearAI.

        This sends the message to Denis's main API which handles
        the full cognition pipeline including intent submission
        if needed.
        """
        # Build messages for API
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
        ]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": message})

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    json={
                        "model": "denis-unified-v1",
                        "messages": messages,
                        "max_tokens": 4000,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    assistant_msg = result["choices"][0]["message"]["content"]

                    # Save to history
                    self.conversation_history.append({"role": "user", "content": message})
                    self.conversation_history.append(
                        {"role": "assistant", "content": assistant_msg}
                    )

                    return {
                        "success": True,
                        "message": assistant_msg,
                        "session_id": self.session_id,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status_code}",
                        "details": response.text[:500],
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Connection error: {str(e)}",
                }

    async def execute_capability(
        self,
        capability: str,
        arguments: dict = None,
        require_approval: bool = True,
    ) -> dict:
        """
        Execute a specific capability using the appropriate tool.

        If require_approval is True and the tool is high/critical risk,
        submits an intent to the control plane first.
        """
        tool_name = self.capabilities.get_tool_for_capability(capability)
        risk = self.capabilities.get_risk_level(tool_name)

        # Check if approval needed
        if require_approval and risk in ("HIGH", "CRITICAL"):
            intent_result = await self._submit_intent(
                action=f"{tool_name}: {capability}",
                risk_score=8 if risk == "CRITICAL" else 6,
                details=json.dumps(arguments or {}),
            )
            if not intent_result.get("approved"):
                return {
                    "success": False,
                    "error": "Action requires human approval",
                    "intent_id": intent_result.get("intent_id"),
                }

        # Execute tool
        result = await self.call_mcp_tool(tool_name, arguments)
        return result

    async def _submit_intent(self, action: str, risk_score: int, details: str) -> dict:
        """Submit an intent to the control plane."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.cp_url}/intent",
                    json={
                        "agent_id": "pearai_agent",
                        "session_id": self.session_id,
                        "semantic_delta": {
                            "action": action,
                            "details": details,
                        },
                        "risk_score": risk_score,
                        "source_node": "pearai",
                    },
                )
                if response.status_code == 201:
                    data = response.json()
                    return {
                        "intent_id": data.get("intent_id"),
                        "status": "pending",
                        "approved": False,
                    }
            except Exception:
                pass
        return {"status": "error", "approved": False}

    def _build_system_prompt(self) -> str:
        return """You are Denis, an expert AI code agent with deep knowledge of software engineering.

## Capabilities
- **File Operations**: read, write, edit files in the workspace
- **Search**: grep, glob, search symbols in code
- **Git**: status, diff, log, commit (requires approval)
- **Execution**: run shell commands (requires approval)
- **Knowledge Graph**: query code context from Neo4j

## Workflow
1. Understand the user's request
2. If the task involves risky actions (writing files, executing commands), 
   check if approval is needed
3. Execute the task using appropriate tools
4. Report results clearly

## Safety
- Always sandbox file operations to the workspace
- Never execute destructive commands without explicit approval
- Use the control plane for high-risk operations

## Integration
You are running as a PearAI agent. Use MCP tools for file operations and search.
"""

    async def get_tools(self) -> list:
        """Get list of available tools."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.mcp_url}/tools")
                if response.status_code == 200:
                    return response.json().get("tools", [])
            except Exception:
                pass
        return []

    async def health_check(self) -> dict:
        """Check health of all services."""
        results = {
            "mcp_server": False,
            "api_server": False,
            "control_plane": False,
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check MCP
            try:
                r = await client.get(f"{self.mcp_url}/health")
                results["mcp_server"] = r.status_code == 200
            except Exception:
                pass

            # Check API
            try:
                r = await client.get(f"{self.api_url}/health")
                results["api_server"] = r.status_code == 200
            except Exception:
                pass

            # Check Control Plane
            try:
                r = await client.get(f"{self.cp_url}/health")
                results["control_plane"] = r.status_code == 200
            except Exception:
                pass

        return results


async def interactive_mode():
    """Run agent in interactive mode."""
    print("Denis Agent for PearAI - Interactive Mode")
    print("=" * 50)

    agent = PearAIDenisAgent()

    # Health check
    health = await agent.health_check()
    print(f"\nHealth Check:")
    for service, status in health.items():
        print(f"  {service}: {'✓' if status else '✗'}")

    if not any(health.values()):
        print("\nERROR: No services available. Please start:")
        print("  - MCP Server: python tools/mcp_denis_server.py")
        print("  - API Server: python -m uvicorn api.fastapi_server:create_app")
        print("  - Control Plane: python -m uvicorn control_plane.intent_queue_app:app")
        return

    print("\nTools available:")
    tools = await agent.get_tools()
    for tool in tools[:10]:
        print(f"  - {tool['name']}")
    if len(tools) > 10:
        print(f"  ... and {len(tools) - 10} more")

    print("\n" + "=" * 50)
    print("Chat with Denis (type 'exit' to quit, 'tools' to list tools)")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower() in ("exit", "quit"):
                break
            if user_input.lower() == "tools":
                tools = await agent.get_tools()
                for tool in tools:
                    print(f"  {tool['name']}: {tool.get('description', '')}")
                continue

            result = await agent.chat(user_input)
            if result.get("success"):
                print(f"\n{result['message']}")
            else:
                print(f"\nError: {result.get('error')}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")


async def test_mode():
    """Run basic tests."""
    agent = PearAIDenisAgent()

    print("Testing MCP connection...")
    result = await agent.call_mcp_tool("denis_workspace_info")
    print(f"Workspace info: {result}")

    print("\nTesting file read...")
    result = await agent.call_mcp_tool("denis_read_file", {"file_path": "README.md"})
    print(f"Read result: {result.get('result', result.get('error'))[:200]}")

    print("\nTesting health check...")
    health = await agent.health_check()
    print(f"Health: {health}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Denis Agent for PearAI")
    parser.add_argument("--mode", choices=["interactive", "test"], default="interactive")
    parser.add_argument("--mcp-url", default="http://localhost:9101")
    parser.add_argument("--api-url", default="http://localhost:9100")
    parser.add_argument("--cp-url", default="http://localhost:8765")

    args = parser.parse_args()

    if args.mode == "interactive":
        asyncio.run(interactive_mode())
    else:
        asyncio.run(test_mode())
