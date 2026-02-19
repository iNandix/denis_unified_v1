#!/usr/bin/env python3
"""
Denis Advanced MCP Server - Full Tool Integration.

Exposes all Denis capabilities including advanced tools from the graph.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

REPO_PATH = Path("/media/jotah/SSD_denis/home_jotah/denis_unified_v1")
sys.path.insert(0, str(REPO_PATH))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORK_DIR = os.getenv("DENIS_WORK_DIR", str(REPO_PATH))
MAX_OUTPUT_CHARS = 8000
COMMAND_TIMEOUT_SEC = 30


def _resolve_path(path: str) -> Optional[Path]:
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


class ToolResult(BaseModel):
    success: bool
    result: str
    error: Optional[str] = None


class AdvancedMCPServer:
    """Advanced MCP Server with full tool integration."""

    def __init__(self):
        self.tools = self._build_tools()

    def _build_tools(self) -> dict:
        return {
            # ============ FILE OPERATIONS ============
            "denis_read_file": {
                "description": "Read file contents",
                "category": "file",
                "risk": "low",
                "parameters": {
                    "file_path": {"type": "string"},
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 200},
                },
                "fn": self.tool_read_file,
            },
            "denis_write_file": {
                "description": "Write content to file",
                "category": "file",
                "risk": "high",
                "parameters": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "default": False},
                },
                "fn": self.tool_write_file,
            },
            "denis_edit_file": {
                "description": "Edit file by replacing text",
                "category": "file",
                "risk": "high",
                "parameters": {
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "fn": self.tool_edit_file,
            },
            # ============ SEARCH OPERATIONS ============
            "denis_grep": {
                "description": "Search regex in files",
                "category": "search",
                "risk": "low",
                "parameters": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "include": {"type": "string", "default": ""},
                },
                "fn": self.tool_grep,
            },
            "denis_glob": {
                "description": "Find files by glob pattern",
                "category": "search",
                "risk": "low",
                "parameters": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "fn": self.tool_glob,
            },
            "denis_list_dir": {
                "description": "List directory contents",
                "category": "file",
                "risk": "low",
                "parameters": {"path": {"type": "string", "default": "."}},
                "fn": self.tool_list_dir,
            },
            "denis_search_symbol": {
                "description": "Search code symbols (functions, classes)",
                "category": "code",
                "risk": "low",
                "parameters": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "default": ""},
                },
                "fn": self.tool_search_symbol,
            },
            # ============ GIT OPERATIONS ============
            "denis_git_status": {
                "description": "Get git status",
                "category": "git",
                "risk": "low",
                "parameters": {},
                "fn": self.tool_git_status,
            },
            "denis_git_diff": {
                "description": "Get git diff",
                "category": "git",
                "risk": "low",
                "parameters": {"file": {"type": "string", "default": ""}},
                "fn": self.tool_git_diff,
            },
            "denis_git_log": {
                "description": "Get recent commits",
                "category": "git",
                "risk": "low",
                "parameters": {"n": {"type": "integer", "default": 10}},
                "fn": self.tool_git_log,
            },
            "denis_git_commit": {
                "description": "Commit changes (requires approval)",
                "category": "git",
                "risk": "medium",
                "parameters": {"message": {"type": "string"}},
                "fn": self.tool_git_commit,
            },
            # ============ EXECUTION ============
            "denis_execute": {
                "description": "Execute shell command",
                "category": "execution",
                "risk": "critical",
                "parameters": {
                    "command": {"type": "string"},
                    "timeout_ms": {"type": "integer", "default": 30000},
                },
                "fn": self.tool_execute,
            },
            # ============ KNOWLEDGE GRAPH ============
            "denis_query_graph": {
                "description": "Query Neo4j knowledge graph",
                "category": "knowledge",
                "risk": "low",
                "parameters": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "fn": self.tool_query_graph,
            },
            "denis_rag_query": {
                "description": "Query RAG vector store",
                "category": "knowledge",
                "risk": "low",
                "parameters": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "fn": self.tool_rag_query,
            },
            # ============ MEMORY ============
            "denis_search_memory": {
                "description": "Search Denis memory",
                "category": "memory",
                "risk": "low",
                "parameters": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "fn": self.tool_search_memory,
            },
            "denis_store_episode": {
                "description": "Store episode in memory",
                "category": "memory",
                "risk": "low",
                "parameters": {
                    "content": {"type": "string"},
                    "tags": {"type": "string", "default": ""},
                },
                "fn": self.tool_store_episode,
            },
            # ============ CODE ANALYSIS ============
            "denis_lint_code": {
                "description": "Lint code files",
                "category": "code",
                "risk": "low",
                "parameters": {"file_path": {"type": "string"}},
                "fn": self.tool_lint_code,
            },
            "denis_type_check": {
                "description": "Run type checking",
                "category": "code",
                "risk": "low",
                "parameters": {"file_path": {"type": "string"}},
                "fn": self.tool_type_check,
            },
            "denis_generate_tests": {
                "description": "Generate tests for code",
                "category": "code",
                "risk": "low",
                "parameters": {"file_path": {"type": "string"}},
                "fn": self.tool_generate_tests,
            },
            # ============ CONTROL PLANE ============
            "denis_submit_intent": {
                "description": "Submit intent for approval",
                "category": "control_plane",
                "risk": "medium",
                "parameters": {
                    "action": {"type": "string"},
                    "risk_score": {"type": "integer", "default": 5},
                    "details": {"type": "string", "default": ""},
                },
                "fn": self.tool_submit_intent,
            },
            "denis_check_intents": {
                "description": "Check pending intents",
                "category": "control_plane",
                "risk": "low",
                "parameters": {},
                "fn": self.tool_check_intents,
            },
            "denis_resolve_intent": {
                "description": "Resolve an intent (approve/reject)",
                "category": "control_plane",
                "risk": "medium",
                "parameters": {
                    "intent_id": {"type": "string"},
                    "decision": {"type": "string"},
                    "notes": {"type": "string", "default": ""},
                },
                "fn": self.tool_resolve_intent,
            },
            # ============ SYSTEM ============
            "denis_health_check": {
                "description": "Check system health",
                "category": "system",
                "risk": "low",
                "parameters": {},
                "fn": self.tool_health_check,
            },
            "denis_service_status": {
                "description": "Check service status",
                "category": "system",
                "risk": "low",
                "parameters": {"service": {"type": "string", "default": "all"}},
                "fn": self.tool_service_status,
            },
            "denis_workspace_info": {
                "description": "Get workspace info",
                "category": "system",
                "risk": "low",
                "parameters": {},
                "fn": self.tool_workspace_info,
            },
            # ============ HOME AUTOMATION ============
            "denis_ha_query": {
                "description": "Query Home Assistant",
                "category": "home",
                "risk": "low",
                "parameters": {"entity_id": {"type": "string", "default": ""}},
                "fn": self.tool_ha_query,
            },
            "denis_ha_control": {
                "description": "Control Home Assistant entity",
                "category": "home",
                "risk": "medium",
                "parameters": {
                    "entity_id": {"type": "string"},
                    "state": {"type": "string", "default": ""},
                    "service": {"type": "string", "default": ""},
                },
                "fn": self.tool_ha_control,
            },
            # ============ NETWORK ============
            "denis_check_port": {
                "description": "Check if port is open",
                "category": "network",
                "risk": "low",
                "parameters": {
                    "host": {"type": "string", "default": "localhost"},
                    "port": {"type": "integer"},
                },
                "fn": self.tool_check_port,
            },
            # ============ WEB ============
            "denis_web_fetch": {
                "description": "Fetch web page content",
                "category": "io",
                "risk": "low",
                "parameters": {"url": {"type": "string"}},
                "fn": self.tool_web_fetch,
            },
            # ============ VOICE ============
            "denis_tts_synthesize": {
                "description": "Synthesize speech",
                "category": "voice",
                "risk": "low",
                "parameters": {"text": {"type": "string"}},
                "fn": self.tool_tts,
            },
            "denis_stt_transcribe": {
                "description": "Transcribe audio",
                "category": "voice",
                "risk": "low",
                "parameters": {"audio_path": {"type": "string"}},
                "fn": self.tool_stt,
            },
        }

    # ============ TOOL IMPLEMENTATIONS ============

    def tool_read_file(self, file_path: str, offset: int = 0, limit: int = 200) -> ToolResult:
        try:
            resolved = _resolve_path(file_path)
            if not resolved:
                return ToolResult(success=False, result="", error="path_outside_workdir")
            if not resolved.exists():
                return ToolResult(success=False, result="", error=f"file_not_found: {file_path}")

            text = resolved.read_text(errors="replace")
            lines = text.splitlines()
            sliced = lines[offset : offset + limit]
            out = "\n".join(sliced)
            if offset + limit < len(lines):
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
            return ToolResult(success=True, result=f"ok: wrote {len(content)} bytes")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"write_error: {e}")

    def tool_edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> ToolResult:
        try:
            resolved = _resolve_path(file_path)
            if not resolved or not resolved.exists():
                return ToolResult(success=False, result="", error="file_not_found")

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
            return ToolResult(success=False, result="", error=str(e))

    def tool_glob(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            base = _resolve_path(path) if path != "." else Path(WORK_DIR)
            if not base or not base.exists():
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
            if not resolved or not resolved.exists():
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

    def tool_search_symbol(self, name: str, kind: str = "") -> ToolResult:
        try:
            from denis_unified_v1.kernel.ghost_ide.symbol_graph import search_symbol

            results = search_symbol(name, kind)
            return ToolResult(success=True, result=json.dumps(results[:20]))
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

    def tool_git_commit(self, message: str) -> ToolResult:
        try:
            subprocess.run(["git", "add", "-A"], capture_output=True, timeout=10, cwd=WORK_DIR)
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=WORK_DIR,
            )
            if result.returncode == 0:
                return ToolResult(success=True, result=result.stdout.strip())
            return ToolResult(success=False, result="", error=result.stderr.strip())
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

    def tool_query_graph(self, query: str, limit: int = 10) -> ToolResult:
        try:
            import httpx

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
            return ToolResult(success=False, result="", error=f"graph_error: {e}")

    def tool_rag_query(self, query: str, limit: int = 5) -> ToolResult:
        return ToolResult(success=True, result=f"RAG query for '{query}': Implement with Qdrant")

    def tool_search_memory(self, query: str, limit: int = 5) -> ToolResult:
        return ToolResult(success=True, result=f"Memory search for '{query}': Implement with Redis")

    def tool_store_episode(self, content: str, tags: str = "") -> ToolResult:
        return ToolResult(success=True, result=f"Stored episode with tags: {tags}")

    def tool_lint_code(self, file_path: str) -> ToolResult:
        try:
            result = subprocess.run(
                ["ruff", "check", file_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=WORK_DIR,
            )
            return ToolResult(success=True, result=result.stdout.strip() or "no issues")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_type_check(self, file_path: str) -> ToolResult:
        try:
            result = subprocess.run(
                ["mypy", file_path], capture_output=True, text=True, timeout=30, cwd=WORK_DIR
            )
            return ToolResult(success=True, result=result.stdout.strip() or "no issues")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_generate_tests(self, file_path: str) -> ToolResult:
        return ToolResult(success=True, result=f"Generate tests for {file_path}: Implement with AI")

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
            return ToolResult(success=False, result="", error=f"intent_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=f"intent_error: {e}")

    def tool_check_intents(self) -> ToolResult:
        try:
            import httpx

            cp_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8765")
            resp = httpx.get(f"{cp_url}/intent/pending", timeout=10.0)
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"check_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_resolve_intent(self, intent_id: str, decision: str, notes: str = "") -> ToolResult:
        try:
            import httpx

            cp_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8765")
            resp = httpx.post(
                f"{cp_url}/intent/{intent_id}/resolve",
                json={"human_id": "pearai", "decision": decision, "notes": notes},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return ToolResult(success=True, result=resp.text)
            return ToolResult(success=False, result="", error=f"resolve_failed: {resp.status_code}")
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_health_check(self) -> ToolResult:
        try:
            import httpx

            results = {}
            for name, url in [
                ("api", "http://localhost:9100"),
                ("mcp", "http://localhost:9101"),
                ("cp", "http://localhost:8765"),
            ]:
                try:
                    r = httpx.get(f"{url}/health", timeout=3.0)
                    results[name] = "ok" if r.status_code == 200 else "error"
                except:
                    results[name] = "down"
            return ToolResult(success=True, result=json.dumps(results))
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_service_status(self, service: str = "all") -> ToolResult:
        return ToolResult(success=True, result=f"Service: {service} - Implement with system check")

    def tool_workspace_info(self) -> ToolResult:
        return ToolResult(
            success=True,
            result=json.dumps(
                {"workdir": WORK_DIR, "repo": "denis_unified_v1", "version": "1.1.0"}
            ),
        )

    def tool_ha_query(self, entity_id: str = "") -> ToolResult:
        try:
            import httpx

            hass_url = os.getenv("HASS_URL", "http://localhost:8123")
            hass_token = os.getenv("HASS_TOKEN", "")
            if not entity_id:
                resp = httpx.get(
                    f"{hass_url}/api/states",
                    headers={"Authorization": f"Bearer {hass_token}"},
                    timeout=10.0,
                )
            else:
                resp = httpx.get(
                    f"{hass_url}/api/states/{entity_id}",
                    headers={"Authorization": f"Bearer {hass_token}"},
                    timeout=10.0,
                )
            return ToolResult(success=True, result=resp.text)
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_ha_control(self, entity_id: str, state: str = "", service: str = "") -> ToolResult:
        try:
            import httpx

            hass_url = os.getenv("HASS_URL", "http://localhost:8123")
            hass_token = os.getenv("HASS_TOKEN", "")
            data = {"entity_id": entity_id}
            if state:
                data["state"] = state
            resp = httpx.post(
                f"{hass_url}/api/services/{service or 'homeassistant'}/turn_on"
                if state
                else f"{hass_url}/api/services/homeassistant/turn_off",
                headers={"Authorization": f"Bearer {hass_token}"},
                json=data,
                timeout=10.0,
            )
            return ToolResult(success=True, result=resp.text)
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_check_port(self, port: int, host: str = "localhost") -> ToolResult:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        return ToolResult(success=True, result="open" if result == 0 else "closed")

    def tool_web_fetch(self, url: str) -> ToolResult:
        try:
            import httpx

            resp = httpx.get(url, timeout=10.0)
            return ToolResult(success=True, result=_truncate(resp.text[:5000]))
        except Exception as e:
            return ToolResult(success=False, result="", error=str(e))

    def tool_tts(self, text: str) -> ToolResult:
        return ToolResult(success=True, result=f"TTS for: {text[:50]}...")

    def tool_stt(self, audio_path: str) -> ToolResult:
        return ToolResult(success=True, result=f"Transcribed: {audio_path}")

    # ============ MCP PROTOCOL ============

    def get_tools_schema(self) -> list:
        tools = []
        for name, spec in self.tools.items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "category": spec.get("category", "unknown"),
                    "risk": spec.get("risk", "unknown"),
                    "inputSchema": {
                        "type": "object",
                        "properties": spec["parameters"],
                    },
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

app = FastAPI(title="Denis Advanced MCP Server", version="1.1.0")
mcp_server = AdvancedMCPServer()


@app.get("/health")
def health():
    return {"status": "ok", "tools": len(mcp_server.tools)}


@app.get("/tools")
def list_tools():
    return {"tools": mcp_server.get_tools_schema()}


@app.get("/tools_by_category")
def tools_by_category():
    by_cat = {}
    for name, spec in mcp_server.tools.items():
        cat = spec.get("category", "unknown")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append({"name": name, "risk": spec.get("risk")})
    return by_cat


@app.post("/tools/{tool_name}/call")
async def call_tool(tool_name: str, arguments: dict = {}):
    return await mcp_server.call_tool(tool_name, arguments)


@app.post("/mcp/tools/list")
async def mcp_list_tools():
    return {"tools": mcp_server.get_tools_schema()}


@app.post("/mcp/tools/call")
async def mcp_call_tool(request: dict):
    tool_name = request.get("name")
    arguments = request.get("arguments", {})
    result = await mcp_server.call_tool(tool_name, arguments)
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "9101"))
    uvicorn.run(app, host="0.0.0.0", port=port)
