#!/usr/bin/env python3
"""Denis Control Plane MCP Server.

Exposes safe tools for Denis operations via MCP protocol.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx

from ide_graph.ide_graph_client import IdeGraphClient


class DenisControlPlane:
    def __init__(self, repo_path: Path, base_url: str, ide_graph_uri: str = None, ide_graph_user: str = None, ide_graph_password: str = None, ide_graph_db: str = None):
        self.repo_path = repo_path
        self.base_url = base_url
        self.ide_graph = IdeGraphClient(ide_graph_uri, ide_graph_user, ide_graph_password, ide_graph_db) if ide_graph_uri else None

    async def health_check(self, base_url: str = None) -> Dict[str, Any]:
        """Perform health check on the given base URL."""
        url = base_url or self.base_url
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{url}/health")
            end = time.time()
            latency = (end - start) * 1000
            ok = response.status_code == 200
            result = {
                "status": response.status_code,
                "ok": ok,
                "content": response.text[:500]  # Truncate for safety
            }
            if self.ide_graph:
                try:
                    name = 'unified' if '8085' in url else 'legacy'
                    self.ide_graph.upsert_service(name, url, 'ok' if ok else 'error')
                except Exception:
                    pass  # Silent
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def run_smoke(self, phase: str = "11") -> Dict[str, Any]:
        """Run smoke test for the specified phase."""
        script_path = self.repo_path / "scripts" / f"phase{phase}_sprint_orchestrator_smoke.py"
        if not script_path.exists():
            return {"error": f"Smoke script for phase {phase} not found"}

        try:
            start = time.time()
            result = subprocess.run(
                [sys.executable, str(script_path), "--out-json", f"phase{phase}_smoke.json"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            end = time.time()
            duration = (end - start) * 1000
            ok = result.returncode == 0
            if self.ide_graph:
                try:
                    self.ide_graph.record_test_result(f"{phase}_smoke", "smoke", ok, int(duration), f"phase{phase}_smoke.json", datetime.now().isoformat())
                except Exception:
                    pass  # Silent
            return {
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:],  # Last 1000 chars
                "stderr": result.stderr[-1000:],
                "ok": ok
            }
        except subprocess.TimeoutExpired:
            return {"error": "Smoke test timed out"}
        except Exception as e:
            return {"error": str(e)}

    async def list_artifacts(self) -> List[str]:
        """List available artifacts."""
        artifacts_dir = self.repo_path / "artifacts"
        if not artifacts_dir.exists():
            return []
        return [f.name for f in artifacts_dir.glob("*.json")]

    async def read_artifact(self, path: str) -> Dict[str, Any]:
        """Read artifact content (only .json files)."""
        if not path.endswith(".json"):
            return {"error": "Only .json artifacts allowed"}
        artifact_path = self.repo_path / "artifacts" / path
        if not artifact_path.exists():
            return {"error": "Artifact not found"}
        try:
            with open(artifact_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}

    async def kill_port(self, port: int) -> Dict[str, Any]:
        """Kill process on specified port (DESTRUCTIVE - requires confirmation)."""
        # Note: This would be marked as DESTRUCTIVE in policy
        try:
            # Find PID using lsof or ss
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                pid = result.stdout.strip()
                return {"pid_found": pid, "message": f"PID {pid} found on port {port}. Confirmation required to kill."}
            else:
                return {"message": f"No process found on port {port}"}
        except Exception as e:
            return {"error": str(e)}


# MCP Protocol Implementation
class MCPHandler:
    def __init__(self, denis_cp: DenisControlPlane):
        self.denis_cp = denis_cp

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        params = request.get("params", {})

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "tools": [
                        {
                            "name": "denis.health_check",
                            "description": "Check health of Denis service",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "base_url": {"type": "string", "description": "Base URL to check"}
                                }
                            }
                        },
                        {
                            "name": "denis.run_smoke",
                            "description": "Run smoke test for phase",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string", "description": "Phase number (default: 11)"}
                                }
                            }
                        },
                        {
                            "name": "denis.list_artifacts",
                            "description": "List available artifacts",
                            "inputSchema": {"type": "object", "properties": {}}
                        },
                        {
                            "name": "denis.read_artifact",
                            "description": "Read artifact content",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Artifact filename"}
                                },
                                "required": ["path"]
                            }
                        },
                        {
                            "name": "get_context_for_request",
                            "description": "Get relevant context from IDE Graph for a request",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {"type": "string"},
                                    "file_path": {"type": "string"},
                                    "profile": {"type": "string"}
                                },
                                "required": ["prompt"]
                            }
                        }
                    ]
                }
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "denis.health_check":
                result = await self.denis_cp.health_check(arguments.get("base_url"))
            elif tool_name == "denis.run_smoke":
                result = await self.denis_cp.run_smoke(arguments.get("phase", "11"))
            elif tool_name == "denis.list_artifacts":
                result = await self.denis_cp.list_artifacts()
            elif tool_name == "denis.read_artifact":
                result = await self.denis_cp.read_artifact(arguments["path"])
            elif tool_name == "denis.kill_port":
                result = await self.denis_cp.kill_port(arguments["port"])
            elif tool_name == "get_context_for_request":
                from tools.ide_graph.context_provider import ContextProvider
                provider = ContextProvider(self.denis_cp.ide_graph)
                result = provider.get_relevant_context(arguments['prompt'], arguments.get('file_path', ''), arguments.get('profile', ''))
            else:
                result = {"error": "Unknown tool"}

            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": result
            }
        elif method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": True}
                    },
                    "serverInfo": {
                        "name": "denis-control-plane",
                        "version": "1.0.0"
                    }
                }
            }

        return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Path to Denis repo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8085", help="Base URL for health checks")
    parser.add_argument("--ide-graph-uri", default=os.getenv("IDE_GRAPH_URI"))
    parser.add_argument("--ide-graph-user", default=os.getenv("IDE_GRAPH_USER"))
    parser.add_argument("--ide-graph-password", default=os.getenv("IDE_GRAPH_PASSWORD"))
    parser.add_argument("--ide-graph-db", default=os.getenv("IDE_GRAPH_DB"))
    args = parser.parse_args()

    repo_path = Path(args.repo)
    denis_cp = DenisControlPlane(
        repo_path,
        args.base_url,
        args.ide_graph_uri,
        args.ide_graph_user,
        args.ide_graph_password,
        args.ide_graph_db
    )
    handler = MCPHandler(denis_cp)

    # MCP uses stdio
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            request = json.loads(line.decode().strip())
            response = await handler.handle_request(request)
            print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
