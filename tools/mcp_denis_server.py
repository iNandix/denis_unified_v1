#!/usr/bin/env python3
"""
Denis Code Agent MCP Server.

Exposes all Denis capabilities as MCP tools for integration with PearAI,
Windsurf, Cursor, and other AI IDEs.

Run: python tools/mcp_denis_server.py
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add repo to path
REPO_PATH = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
sys.path.insert(0, str(REPO_PATH))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
WORK_DIR = os.getenv("DENIS_WORK_DIR", str(REPO_PATH))
MAX_OUTPUT_CHARS = 8000
COMMAND_TIMEOUT_SEC = 30


def _resolve_path(path: str) -> Optional[Path]:
    """Resolve path within workdir sandbox."""
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = WORK_DIR / p
    try:
        resolved = p.resolve()
    except Exception:
        resolved = p.absolute()

    wd = Path(WORK_DIR).resolve()
    try:
        if resolved == wd or resolved.is_relative_to(wd):
            return resolved
        return None
    except Exception:
        wd_s = str(wd)
        res_s = str(resolved)
        if res_s == wd_s or res_s.startswith(wd_s.rstrip(os.sep) + os.sep):
            return resolved
        return None


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... truncated ({len(text)} chars)"
    return text


# ============ TOOL IMPLEMENTATIONS ============


class ToolResult(BaseModel):
    success: bool
    result: str
    error: Optional[str] = None


class MCPServer:
    """MCP Server exposing all Denis tools."""

    def __init__(self):
        self.tools = self._build_tools()

    def _build_tools(self) -> dict:
        """Define all available MCP tools."""
        return {
            # === File Operations ===
            "denis_read_file": {
                "description": "Read contents of a file. Returns up to 200 lines by default.",
                "parameters": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to file (relative to workspace or absolute)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line offset to start from",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to read",
                        "default": 200,
                    },
                },
                "fn": self.tool_read_file,
            },
            "denis_write_file": {
                "description": "Write content to a file. Creates parent directories if needed.",
                "parameters": {
                    "file_path": {"type": "string", "description": "Path to file"},
                    "content": {"type": "string", "description": "Content to write"},
                    "append": {
                        "type": "boolean",
                        "description": "Append instead of overwrite",
                        "default": False,
                    },
                },
                "fn": self.tool_write_file,
            },
            "denis_edit_file": {
                "description": "Edit a file by replacing exact text strings.",
                "parameters": {
                    "file_path": {"type": "string", "description": "Path to file"},
                    "old_string": {"type": "string", "description": "Text to find and replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences",
                        "default": False,
                    },
                },
                "fn": self.tool_edit_file,
            },
            # === Search Operations ===
            "denis_grep": {
                "description": "Search for regex pattern in files (like grep).",
                "parameters": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "path": {
                        "type": "string",
                        "description": "Directory to search in",
                        "default": ".",
                    },
                    "include": {
                        "type": "string",
                        "description": "File filter (e.g., *.py)",
                        "default": "",
                    },
                },
                "fn": self.tool_grep,
            },
            "denis_glob": {
                "description": "Find files matching glob pattern.",
                "parameters": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
                    "path": {
                        "type": "string",
                        "description": "Directory to search",
                        "default": ".",
                    },
                },
                "fn": self.tool_glob,
            },
            "denis_list_dir": {
                "description": "List directory contents with metadata.",
                "parameters": {
                    "path": {"type": "string", "description": "Directory path", "default": "."}
                },
                "fn": self.tool_list_dir,
            },
            # === Execution ===
            "denis_execute": {
                "description": "Execute a shell command and return output.",
                "parameters": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Timeout in milliseconds",
                        "default": 30000,
                    },
                },
                "fn": self.tool_execute,
            },
            # === Git Operations ===
            "denis_git_status": {
                "description": "Get git status of repository.",
                "parameters": {},
                "fn": self.tool_git_status,
            },
            "denis_git_diff": {
                "description": "Get git diff of changes.",
                "parameters": {
                    "file": {
                        "type": "string",
                        "description": "Specific file to diff",
                        "default": "",
                    }
                },
                "fn": self.tool_git_diff,
            },
            "denis_git_log": {
                "description": "Get recent git commits.",
                "parameters": {
                    "n": {"type": "integer", "description": "Number of commits", "default": 10}
                },
                "fn": self.tool_git_log,
            },
            # === Knowledge Graph ===
            "denis_query_graph": {
                "description": "Query Neo4j knowledge graph for code context.",
                "parameters": {
                    "query": {"type": "string", "description": "Cypher query or keywords"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "fn": self.tool_query_graph,
            },
            "denis_search_memory": {
                "description": "Search Denis memory/context for relevant information.",
                "parameters": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5},
                },
                "fn": self.tool_search_memory,
            },
            # === Control Plane ===
            "denis_submit_intent": {
                "description": "Submit an intent to control plane for approval.",
                "parameters": {
                    "action": {"type": "string", "description": "Action description"},
                    "risk_score": {
                        "type": "integer",
                        "description": "Risk level 0-10",
                        "default": 5,
                    },
                    "details": {
                        "type": "string",
                        "description": "Additional details",
                        "default": "",
                    },
                },
                "fn": self.tool_submit_intent,
            },
            "denis_check_pending_intents": {
                "description": "Check pending intents in control plane.",
                "parameters": {},
                "fn": self.tool_check_pending_intents,
            },
            # === System ===
            "denis_workspace_info": {
                "description": "Get workspace configuration and info.",
                "parameters": {},
                "fn": self.tool_workspace_info,
            },
            "denis_search_symbol": {
                "description": "Search for code symbols (functions, classes) in codebase.",
                "parameters": {
                    "name": {"type": "string", "description": "Symbol name to search"},
                    "kind": {
                        "type": "string",
                        "description": "Type: function, class, const",
                        "default": "",
                    },
                },
                "fn": self.tool_search_symbol,
            },
        }

    # ============ TOOL FUNCTIONS ============

    def tool_read_file(self, file_path: str, offset: int = 0, limit: int = 200) -> ToolResult:
        try:
            resolved = _resolve_path(file_path)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            if not resolved.exists():
                return ToolResult(success=False, result="", error=f"file_not_found: {file_path}")

            text = resolved.read_text(errors="replace")
            lines = text.splitlines()
            off = max(0, offset)
            lim = max(1, limit)
            sliced = lines[off : off + lim]
            out = "\n".join(sliced)
            if off + lim < len(lines):
                out += f"\n... truncated ({len(lines)} total lines)"
            return ToolResult(success=True, result=out)
        except Exception as e:
            return ToolResult(success=False, result="", error=f"read_error: {e}")

    def tool_write_file(self, file_path: str, content: str, append: bool = False) -> ToolResult:
        try:
            resolved = _resolve_path(file_path)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with resolved.open(mode, encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, result=f"ok: wrote {len(content)} bytes to {file_path}")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"write_error: {e}")

    def tool_edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> ToolResult:
        try:
            resolved = _resolve_path(file_path)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            if not resolved.exists():
                return ToolResult(success=False, result="", error=f"file_not_found: {file_path}")

            text = resolved.read_text(errors="replace")
            if replace_all:
                count = text.count(old_string)
                if count == 0:
                    return ToolResult(success=False, result="", error="no_changes")
                new_text = text.replace(old_string, new_string)
            else:
                idx = text.find(old_string)
                if idx == -1:
                    return ToolResult(success=False, result="", error="no_changes")
                count = 1
                new_text = text[:idx] + new_string + text[idx + len(old_string) :]

            resolved.write_text(new_text, encoding="utf-8")
            return ToolResult(success=True, result=f"ok: replaced {count} occurrence(s)")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"edit_error: {e}")

    def tool_grep(self, pattern: str, path: str = ".", include: str = "") -> ToolResult:
        try:
            resolved = _resolve_path(path) if path != "." else Path(WORK_DIR)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")

            cmd = ["grep", "-rn", "--color=never", "-I"]
            if include:
                cmd.extend(["--include", include])
            cmd.extend([pattern, str(resolved)])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC, cwd=WORK_DIR
            )
            output = result.stdout.strip()
            if not output:
                return ToolResult(success=True, result="no_matches_found")
            return ToolResult(success=True, result=_truncate(output))
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, result="", error="grep_timeout")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"grep_error: {e}")

    def tool_glob(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            base = _resolve_path(path) if path != "." else Path(WORK_DIR)
            if not base:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            if not base.exists():
                return ToolResult(success=False, result="", error="directory_not_found")

            matches = sorted(base.glob(pattern))
            if not matches:
                return ToolResult(success=True, result="no_files_found")

            lines = [str(m.relative_to(Path(WORK_DIR))) for m in matches[:200]]
            result = "\n".join(lines)
            if len(matches) > 200:
                result += f"\n... and {len(matches) - 200} more"
            return ToolResult(success=True, result=result)
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_list_dir(self, path: str = ".") -> ToolResult:
        try:
            resolved = _resolve_path(path) if path != "." else Path(WORK_DIR)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            if not resolved.exists():
                return ToolResult(success=False, result="", error="directory_not_found")

            entries = []
            for child in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[
                :100
            ]:
                stat = child.stat() if child.exists() else None
                entries.append(
                    {
                        "name": child.name,
                        "type": "dir" if child.is_dir() else "file",
                        "size": getattr(stat, "st_size", 0) or 0,
                    }
                )
            return ToolResult(
                success=True, result=json.dumps({"path": str(resolved), "entries": entries})
            )
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_execute(self, command: str, timeout_ms: int = 30000) -> ToolResult:
        try:
            timeout_sec = max(1, timeout_ms // 1000)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=WORK_DIR,
            )
            output = result.stdout.strip()
            if result.returncode != 0:
                error = result.stderr.strip()
                output = f"exit_code={result.returncode}\n{output}\nSTDERR: {error}"
            return ToolResult(
                success=True,
                result=_truncate(output) if output else f"exit_code={result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, result="", error="command_timeout")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_git_status(self) -> ToolResult:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=WORK_DIR,
            )
            output = result.stdout.strip()
            if not output:
                return ToolResult(success=True, result="working tree clean")
            return ToolResult(success=True, result=output)
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_git_diff(self, file: str = "") -> ToolResult:
        try:
            cmd = ["git", "diff"] + ([file] if file else [])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=WORK_DIR)
            return ToolResult(success=True, result=_truncate(result.stdout.strip()))
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_git_log(self, n: int = 10) -> ToolResult:
        try:
            result = subprocess.run(
                ["git", "log", f"-{n}", "--oneline"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=WORK_DIR,
            )
            return ToolResult(success=True, result=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_query_graph(self, query: str, limit: int = 10) -> ToolResult:
        try:
            import httpx

            neo4j_url = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "Leon1234$")

            # Simple query via HTTP
            http_url = neo4j_url.replace("bolt", "http").replace("7687", "7474")
            resp = httpx.post(
                f"{http_url}/db/neo4j/tx/commit",
                headers={"Content-Type": "application/json"},
                auth=(neo4j_user, neo4j_pass),
                json={"statements": [{"statement": query, "limit": limit}]},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    return ToolResult(success=True, result=json.dumps(results[0].get("data", [])))
            return ToolResult(success=True, result="no_results")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"graph_query_error: {e}")

    def tool_search_memory(self, query: str, limit: int = 5) -> ToolResult:
        # Simplified memory search - would connect to Qdrant/Redis in production
        return ToolResult(
            success=True, result=f"Memory search for '{query}': Implement with Qdrant vector store"
        )

    def tool_submit_intent(self, action: str, risk_score: int = 5, details: str = "") -> ToolResult:
        try:
            import httpx

            cp_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8765")
            resp = httpx.post(
                f"{cp_url}/intent",
                json={
                    "agent_id": "pearai",
                    "session_id": "pearai-session",
                    "semantic_delta": {"action": action, "details": details},
                    "risk_score": risk_score,
                    "source_node": "pearai",
                },
                timeout=10.0,
            )
            if resp.status_code == 201:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(
                success=False, result="", error=f"intent_submission_failed: {resp.status_code}"
            )
        except Exception as e:
            return ToolResult(success=False, result="", error=f"intent_error: {e}")

    def tool_check_pending_intents(self) -> ToolResult:
        try:
            import httpx

            cp_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8765")
            resp = httpx.get(f"{cp_url}/intent/pending", timeout=10.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"check_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"intent_check_error: {e}")

    def tool_workspace_info(self) -> ToolResult:
        return ToolResult(
            success=True,
            result=json.dumps(
                {
                    "workdir": WORK_DIR,
                    "repo": "denis_unified_v1",
                    "version": "1.1.0",
                    "neo4j": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    "control_plane": os.getenv("CONTROL_PLANE_URL", "http://localhost:8765"),
                }
            ),
        )

    def tool_search_symbol(self, name: str, kind: str = "") -> ToolResult:
        try:
            from denis_unified_v1.kernel.ghost_ide.symbol_graph import search_symbol

            results = search_symbol(name, kind)
            return ToolResult(success=True, result=json.dumps(results[:20]))
        except Exception as e:
            return ToolResult(success=False, result="", error=f"symbol_search_error: {e}")

    # ============ MCP PROTOCOL ============

    def get_tools_schema(self) -> list:
        """Return MCP tools schema."""
        tools = []
        for name, spec in self.tools.items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": {
                        "type": "object",
                        "properties": spec["parameters"],
                        "required": [
                            p
                            for p in spec["parameters"]
                            if spec["parameters"][p].get("required", False)
                        ],
                    },
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool by name with arguments."""
        if name not in self.tools:
            return {"success": False, "error": f"unknown_tool: {name}"}

        spec = self.tools[name]
        fn = spec["fn"]

        # Filter to only expected params
        params = {k: v for k, v in arguments.items() if k in spec["parameters"]}

        # Handle async/sync functions
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

app = FastAPI(title="Denis MCP Server", version="1.0.0")
mcp_server = MCPServer()


@app.get("/health")
def health():
    return {"status": "ok", "tools": len(mcp_server.tools)}


@app.get("/tools")
def list_tools():
    return {"tools": mcp_server.get_tools_schema()}


@app.post("/tools/{tool_name}/call")
async def call_tool(tool_name: str, arguments: dict = {}):
    return await mcp_server.call_tool(tool_name, arguments)


@app.post("/mcp/tools/list")
async def mcp_list_tools():
    """MCP protocol: list tools."""
    return {"tools": mcp_server.get_tools_schema()}


@app.post("/mcp/tools/call")
async def mcp_call_tool(request: dict):
    """MCP protocol: call tool."""
    tool_name = request.get("name")
    arguments = request.get("arguments", {})
    result = await mcp_server.call_tool(tool_name, arguments)
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "9101"))
    uvicorn.run(app, host="0.0.0.0", port=port)
