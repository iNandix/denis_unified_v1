#!/usr/bin/env python3
"""Denis MCP Server — contexto del sistema como tools para agentes."""

import json
import os
import sys

sys.path.insert(0, "/media/jotah/SSD_denis/denis_unified_v1")
sys.path.insert(0, "/media/jotah/SSD_denis")


def _read_session_parts() -> tuple:
    try:
        raw = open("/tmp/denis/sessionid.txt").read().strip()
        parts = (raw + "||||").split("|")
        return parts[0], parts[1], parts[2] or "unknown", parts[3] or "main"
    except Exception:
        return "default", "", "unknown", "main"


WORKSPACE_BASE = {
    "workspace": "/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
    "pythonpath": "/media/jotah/SSD_denis/home_jotah",
    "venv": "/media/jotah/SSD_denis/.venv_oceanai/bin/python3",
    "frontend": "/media/jotah/SSD_denis/FrontDenisACTUAL",
    "ssd_root": "/media/jotah/SSD_denis",
    "node": "nodo1",
}

DO_NOT_TOUCH = [
    "service_8084.py",
    "kernel/__init__.py",
    "FrontDenisACTUAL/public/",
    "denis_unified_v1/compiler/makina_filter.py",
]


def handle_jsonrpc(request: dict) -> dict:
    """Handle JSON-RPC requests."""
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        params = request.get("params", {})
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "denis-mcp", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "get_workspace_paths",
                        "description": "RETURNS canonical workspace paths: workspace (denis_unified_v1 root), pythonpath, venv path, frontend path, ssd_root, node name. ALWAYS call this FIRST in every task to know where you are.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "description": "No parameters required. Returns full workspace config.",
                        },
                    },
                    {
                        "name": "get_do_not_touch",
                        "description": "RETURNS list of protected paths that NEVER should be modified without explicit ApprovalEngine approval. These are core system files. Always check this before editing anything.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "description": "No parameters. Returns array of protected file/directory paths.",
                        },
                    },
                    {
                        "name": "get_session_context",
                        "description": "RETURNS current session context from Neo4j: modified_paths (files changed today), do_not_touch_auto (auto-detected protected files), context_prefilled (implicit tasks for current intent). Uses session_id from /tmp/denis/session_id.txt or defaults to 'default'.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Optional. Override default session ID.",
                                }
                            },
                        },
                    },
                    {
                        "name": "find_symbol",
                        "description": "SEARCHES Neo4j graph for symbol/function/class by name. Queries Symbol nodes in Neo4j for name match. Falls back to grep if Neo4j unavailable. Returns file_path, line, category (function/class/const).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Symbol name to search (exact or partial match)",
                                },
                                "kind": {
                                    "type": "string",
                                    "enum": ["function", "class", "const", "all"],
                                    "description": "Optional filter by symbol type",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                    {
                        "name": "get_service_status",
                        "description": "CHECKS health of critical services: Neo4j (bolt://127.0.0.1:7687), Qdrant (vector store), NextCloud (file sync), service_8084 (Denis inference), intent_queue (:8765). Returns status UP/DOWN for each.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "service": {
                                    "type": "string",
                                    "enum": [
                                        "all",
                                        "neo4j",
                                        "qdrant",
                                        "nextcloud",
                                        "8084",
                                        "intent_queue",
                                    ],
                                    "description": "Optional. Specific service to check.",
                                }
                            },
                        },
                    },
                    {
                        "name": "write_cp_received",
                        "description": "TRIGGERS approval popup by writing /tmp/denis/cp_received.json. Call ONCE at start of each ContextPack AFTER reading FILES_TO_READ_FIRST and BEFORE executing any task. The popup shows mission, phases, and risks for human review.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "cpid": {
                                    "type": "string",
                                    "description": "Unique ContextPack ID (e.g., 'CP-002-INTENT')",
                                },
                                "mission": {
                                    "type": "string",
                                    "description": "Mission objective in 2 lines max",
                                },
                                "phases": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Array of phase descriptions: ['Fase 1: Discovery (~30min)', 'Fase 2: Implementation (~20min)']",
                                },
                                "risks": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Sensitive files/paths that will be touched",
                                },
                            },
                            "required": ["cpid", "mission"],
                        },
                    },
                    {
                        "name": "write_phase_complete",
                        "description": "TRIGGERS phase completion popup by writing /tmp/denis/phase_complete.json. Call AFTER completing each phase with summary of what succeeded and what failed. Shows results and proposes next phase.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "phase_num": {
                                    "type": "integer",
                                    "description": "Phase number (1, 2, 3...)",
                                },
                                "completed": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of successful tasks: ['✅ T1 Discovery — OceanAI found', '✅ T2 session_id — write/read OK']",
                                },
                                "failed": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of failed tasks: ['❌ T7 ai_consult — endpoint timeout']",
                                },
                                "next_phase_summary": {
                                    "type": "string",
                                    "description": "What will happen in next phase",
                                },
                            },
                            "required": ["phase_num", "completed", "failed", "next_phase_summary"],
                        },
                    },
                    {
                        "name": "read_next_cp",
                        "description": "READS enriched ContextPack from /tmp/denis/next_cp.json if exists (human adjusted). Call at START of each phase to check for human corrections. If file doesn't exist, continue with original CP. Removes file after reading.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "description": "No parameters. Returns {enriched: true/false, cp: {...}}",
                        },
                    },
                    {
                        "name": "get_repo_context",
                        "description": "READS current git state: repo_id (MD5 hash of workspace path), branch name, last commit hash+message, list of uncommitted files. Use to understand current working state before making changes.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "description": "No parameters. Returns git context object.",
                        },
                    },
                    {
                        "name": "get_next_cp",
                        "description": "READS next approved ContextPack from /tmp/denis_next_cp.json. This is the file written by the daemon when a CP is approved. Use to fetch the CP that should be executed next.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "description": "No parameters. Returns {cp: {...}, exists: true/false}",
                        },
                    },
                    {
                        "name": "approve_cp",
                        "description": "APPROVES a ContextPack via the Intent Queue API (:8765). Sends approval intent to Neo4j with human notes. The Intent Queue stores the decision for audit trail and learning.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "cp_id": {
                                    "type": "string",
                                    "description": "ContextPack ID to approve",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional human notes about the approval",
                                },
                            },
                            "required": ["cp_id"],
                        },
                    },
                ]
            },
        }

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})

        result = call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def call_tool(name: str, arguments: dict) -> list:
    """Execute a tool and return results."""
    import urllib.request

    if name == "get_workspace_paths":
        sid, repo_id, repo_name, branch = _read_session_parts()
        workspace = {
            **WORKSPACE_BASE,
            "sessionId": sid,
            "repoId": repo_id,
            "repoName": repo_name,
            "branch": branch,
        }
        return [{"type": "text", "text": json.dumps(workspace, indent=2)}]

    if name == "get_do_not_touch":
        return [{"type": "text", "text": json.dumps(DO_NOT_TOUCH, indent=2)}]

    if name == "get_session_context":
        session_id = "default"
        try:
            with open("/tmp/denis_session_id.txt") as f:
                session_id = f.read().strip()
        except Exception:
            pass

        try:
            from kernel.ghostide.contextharvester import ContextHarvester

            h = ContextHarvester(session_id=session_id, watch_paths=[])
            ctx = h.get_session_context()
            return [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "session_id": session_id,
                            "modified_paths": ctx.modified_paths,
                            "do_not_touch_auto": ctx.do_not_touch_auto,
                            "context_prefilled": ctx.context_prefilled,
                        },
                        indent=2,
                    ),
                }
            ]
        except Exception as e:
            return [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "session_id": session_id,
                            "modified_paths": [],
                            "do_not_touch_auto": DO_NOT_TOUCH,
                            "error": str(e)[:200],
                        },
                        indent=2,
                    ),
                }
            ]

    if name == "find_symbol":
        try:
            from kernel.ghostide.symbolgraph import SymbolGraph

            g = SymbolGraph()
            result = g.find_compatible([arguments.get("name", "")])
            return [{"type": "text", "text": json.dumps(result, indent=2)}]
        except Exception as e:
            return [{"type": "text", "text": f"Symbol not found: {e}"}]

    if name == "get_service_status":
        services = {}
        checks = {
            "nextcloud": "http://localhost:8080/status.php",
            "qdrant": "http://localhost:6333/healthz",
            "service_8084": "http://localhost:8084/health",
        }
        for svc, url in checks.items():
            try:
                urllib.request.urlopen(url, timeout=1)
                services[svc] = "UP"
            except Exception:
                services[svc] = "DOWN"
        try:
            from neo4j import GraphDatabase

            d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            d.verify_connectivity()
            services["neo4j"] = "UP"
            d.close()
        except Exception:
            services["neo4j"] = "DOWN"
        return [{"type": "text", "text": json.dumps(services, indent=2)}]

    if name == "write_cp_received":
        cpid = arguments.get("cpid", "unknown")
        mission = arguments.get("mission", "")
        phases = arguments.get("phases", [])
        risks = arguments.get("risks", [])

        os.makedirs("/tmp/denis", exist_ok=True)
        data = {
            "cp": {
                "cp_id": cpid,
                "mission": mission,
                "repo_name": "denis_unified_v1",
                "branch": "main",
                "intent": "implement_feature",
                "files_to_read": [],
                "risk_level": "MEDIUM",
                "is_checkpoint": True,
            },
            "phases": phases,
            "risks": risks,
        }
        with open("/tmp/denis/cp_received.json", "w") as f:
            json.dump(data, f)
        return [{"type": "text", "text": json.dumps({"status": "popup_triggered", "cpid": cpid})}]

    if name == "write_phase_complete":
        phase_num = arguments.get("phase_num", 1)
        completed = arguments.get("completed", [])
        failed = arguments.get("failed", [])
        next_phase_summary = arguments.get("next_phase_summary", "")

        os.makedirs("/tmp/denis", exist_ok=True)
        data = {
            "phase_num": phase_num,
            "completed": completed,
            "failed": failed,
            "next_phase_summary": next_phase_summary,
        }
        with open("/tmp/denis/phase_complete.json", "w") as f:
            json.dump(data, f)
        return [
            {"type": "text", "text": json.dumps({"status": "popup_triggered", "phase": phase_num})}
        ]

    if name == "read_next_cp":
        path = "/tmp/denis/next_cp.json"
        if os.path.exists(path):
            data = json.load(open(path))
            os.remove(path)
            return [{"type": "text", "text": json.dumps({"enriched": True, "cp": data})}]
        return [{"type": "text", "text": json.dumps({"enriched": False})}]

    if name == "get_repo_context":
        import subprocess

        ws = WORKSPACE_BASE["workspace"]
        try:
            branch = (
                subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws)
                .decode()
                .strip()
            )
            last_commit = (
                subprocess.check_output(["git", "log", "-1", "--oneline"], cwd=ws).decode().strip()
            )
            uncommitted = (
                subprocess.check_output(["git", "status", "--porcelain"], cwd=ws)
                .decode()
                .strip()
                .split("\n")
            )
        except Exception as e:
            branch, last_commit, uncommitted = "unknown", str(e), []

        import hashlib

        repo_id = hashlib.md5(ws.encode()).hexdigest()[:12]

        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "repo_id": repo_id,
                        "branch": branch,
                        "last_commit": last_commit,
                        "uncommitted_files": [f for f in uncommitted if f],
                    },
                    indent=2,
                ),
            }
        ]

    if name == "get_next_cp":
        path = "/tmp/denis_next_cp.json"
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            return [{"type": "text", "text": json.dumps({"cp": data, "exists": True})}]
        return [{"type": "text", "text": json.dumps({"exists": False})}]

    if name == "approve_cp":
        cp_id = arguments.get("cp_id", "")
        notes = arguments.get("notes", "")

        # Write to Intent Queue for approval
        try:
            import urllib.request

            req = urllib.request.Request(
                "http://127.0.0.1:8765/intent",
                data=json.dumps(
                    {
                        "agent_id": "denis_mcp",
                        "session_id": "mcp_session",
                        "semantic_delta": {"cp_id": cp_id, "action": "approve", "notes": notes},
                        "risk_score": 1,
                    }
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return [{"type": "text", "text": json.dumps({"status": "approved", "cp_id": cp_id})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"status": "error", "message": str(e)})}]

    return [{"type": "text", "text": f"Unknown tool: {name}"}]


if __name__ == "__main__":
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_jsonrpc(request)
            print(json.dumps(response), flush=True)
        except Exception as e:
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
                ),
                flush=True,
            )
