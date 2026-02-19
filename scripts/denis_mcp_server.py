#!/usr/bin/env python3
"""Denis MCP Server — contexto del sistema como tools para agentes."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/media/jotah/SSD_denis/denis_unified_v1")
sys.path.insert(0, "/media/jotah/SSD_denis")


def _get_git_root(cwd: str) -> str:
    """Find git root from current working directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return cwd


def _get_workspace_base() -> dict:
    """Dynamic workspace paths based on actual cwd."""
    cwd = os.getcwd()
    git_root = _get_git_root(cwd)

    return {
        "workspace": git_root,
        "pythonpath": str(Path(git_root).parent),
        "venv": "/media/jotah/SSD_denis/.venv_oceanai/bin/python3",
        "frontend": "/media/jotah/SSD_denis/FrontDenisACTUAL",
        "ssd_root": "/media/jotah/SSD_denis",
        "node": "nodo1",
    }


def _read_session_parts() -> tuple:
    try:
        raw = open("/tmp/denis/session_id.txt").read().strip()
        parts = (raw + "||||").split("|")
        return parts[0], parts[1], parts[2] or "unknown", parts[3] or "main"
    except Exception:
        try:
            from control_plane.repo_context import RepoContext

            repo = RepoContext()
            return repo.get_session_id(), repo.repo_id, repo.repo_name, repo.branch
        except Exception:
            return "default", "", "unknown", "main"


WORKSPACE_BASE = _get_workspace_base()

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
                    {
                        "name": "get_graph_analytics",
                        "description": "GETS analytics from Neo4j graph: CP approval rates, intent patterns, session stats. Returns stats for the last N days.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "days": {
                                    "type": "integer",
                                    "description": "Number of days to look back (default 7)",
                                    "default": 7,
                                }
                            },
                        },
                    },
                    {
                        "name": "get_learned_patterns",
                        "description": "GETS learned task patterns from the graph for a specific intent. Returns tasks that Denis has learned to associate with this intent.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "intent": {
                                    "type": "string",
                                    "description": "Intent to get patterns for (e.g., 'implement_feature', 'debug_repo')",
                                },
                            },
                            "required": ["intent"],
                        },
                    },
                    # SPRINT 19: Multi-file atomic operations
                    {
                        "name": "multi_file_read_context",
                        "description": "READS multiple files with LSP semantic context. Returns file content + pyright diagnostics for each file. Use for atomic multi-file operations.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "files": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Array of file paths to read",
                                },
                                "lsp_semantic": {
                                    "type": "boolean",
                                    "description": "Include LSP diagnostics (default true)",
                                    "default": True,
                                },
                            },
                            "required": ["files"],
                        },
                    },
                    {
                        "name": "multi_file_edit",
                        "description": "ATOMIC multi-file edit with backup. Applies patches to multiple files. Creates automatic backups before modification. Returns applied/failed status.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "files": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Array of file paths to edit",
                                },
                                "patches": {
                                    "type": "object",
                                    "description": "Dict of filepath -> new content",
                                },
                                "create_backup": {
                                    "type": "boolean",
                                    "description": "Create backup before editing (default true)",
                                    "default": True,
                                },
                            },
                            "required": ["files", "patches"],
                        },
                    },
                    {
                        "name": "atomic_refactor",
                        "description": "ATOMIC refactor across multiple files using regex pattern replacement. Returns patches without applying. Use multi_file_edit to apply.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "files": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Array of file paths to refactor",
                                },
                                "pattern": {
                                    "type": "string",
                                    "description": "Regex pattern to match",
                                },
                                "replacement": {
                                    "type": "string",
                                    "description": "Replacement string",
                                },
                            },
                            "required": ["files", "pattern", "replacement"],
                        },
                    },
                    # Working Memory tools
                    {
                        "name": "working_memory_add_file",
                        "description": "ADDS file to working memory LRU cache. Keeps hot files in memory for fast access across operations.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "filepath": {
                                    "type": "string",
                                    "description": "File path to add to working memory",
                                },
                            },
                            "required": ["filepath"],
                        },
                    },
                    {
                        "name": "working_memory_get_context",
                        "description": "RETURNS current working memory context: hot_files, errors, decisions, git_diffs. Use for prompt injection.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "working_memory_add_error",
                        "description": "ADDS error to protected slot in working memory. Errors are preserved across operations.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "error": {
                                    "type": "string",
                                    "description": "Error message to store",
                                },
                            },
                            "required": ["error"],
                        },
                    },
                    {
                        "name": "working_memory_add_decision",
                        "description": "ADDS decision to protected slot in working memory. Decisions are preserved across operations.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "decision": {
                                    "type": "string",
                                    "description": "Decision description to store",
                                },
                            },
                            "required": ["decision"],
                        },
                    },
                    {
                        "name": "working_memory_clear",
                        "description": "CLEARS all working memory: hot_files, errors, decisions, git_diffs.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    # ATLAS FORK - Self-aware tools
                    {
                        "name": "atlas_self_check",
                        "description": "ATLAS FORK: Performs self-awareness check. Returns current state: mood, consciousness_level, decisions_made, last_error. Use when you need to know how Denis is feeling.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "atlas_decide",
                        "description": "ATLAS FORK: Asks Denis to make a decision. Pass intent, constraints. Returns {engine, mood, confidence, reasoning}. This is the PRIMARY way to route - don't guess, ask Denis.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "intent": {
                                    "type": "string",
                                    "description": "Intent to decide on (e.g., 'implement_feature', 'debug_repo')",
                                },
                                "constraints": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Active constraints",
                                },
                                "session_id": {
                                    "type": "string",
                                    "description": "Optional session ID",
                                },
                            },
                            "required": ["intent"],
                        },
                    },
                    {
                        "name": "atlas_learn_outcome",
                        "description": "ATLAS FORK: Tell Denis the outcome of a decision so he can learn. Updates consciousness_level based on success/failure.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "session_id": {"type": "string"},
                                "decision": {
                                    "type": "object",
                                    "description": "Decision that was made",
                                },
                                "outcome": {
                                    "type": "string",
                                    "description": "Outcome description (success/failure)",
                                },
                            },
                            "required": ["session_id", "outcome"],
                        },
                    },
                    {
                        "name": "atlas_get_knowledge",
                        "description": "ATLAS FORK: Get what Denis knows. Returns symbols in his knowledge base.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Optional session filter",
                                },
                            },
                        },
                    },
                    # Intent Router - Universal routing
                    {
                        "name": "route_input",
                        "description": "UNIVERSAL ROUTING: Takes prompt, returns routed request with model, implicit_tasks, context_prefilled. Use this instead of guessing which model to use.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "User prompt to route"},
                                "session_id": {
                                    "type": "string",
                                    "description": "Optional session ID",
                                },
                                "context_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Optional file references",
                                },
                            },
                            "required": ["prompt"],
                        },
                    },
                    # Pattern Health - RedundancyDetector validation
                    {
                        "name": "get_pattern_health",
                        "description": "RETURNS health status of learned patterns: approved, blocked, needs_review. Shows which patterns passed validation (frequency>=3, success_rate>=0.8, no conflicts, recent validation).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "validate_pattern",
                        "description": "VALIDATES a single pattern against control plane rules. Returns {is_valid, reason}. Use to check if a pattern can be auto-injected.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "pattern_name": {"type": "string"},
                                "frequency": {"type": "integer"},
                                "success_rate": {"type": "number"},
                                "last_validated": {"type": "string"},
                            },
                            "required": ["pattern_name", "frequency"],
                        },
                    },
                    # Quick context for agents
                    {
                        "name": "quick_context",
                        "description": "FAST: Returns minimal context for agents. Combines workspace_paths + do_not_touch + session_context in one call. Use this instead of multiple tool calls.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    # Control Plane - CP management
                    {
                        "name": "get_next_cp",
                        "description": "CONTROL PLANE: Gets the next pending ContextPack from the queue. Returns CP object or null if queue is empty. Use this to see what Denis has proposed.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "approve_cp",
                        "description": "CONTROL PLANE: Approves a ContextPack programmatically (without zenity popup). Marks CP as human_validated and moves it to execution queue.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "cp_id": {
                                    "type": "string",
                                    "description": "ContextPack ID to approve",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional approval notes",
                                },
                            },
                            "required": ["cp_id"],
                        },
                    },
                    {
                        "name": "upload_cp",
                        "description": "CONTROL PLANE: Uploads a ContextPack from disk file. Opens file dialog, validates JSON, shows preview, and if approved, adds to queue. Use when you have a CP saved locally.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "filepath": {
                                    "type": "string",
                                    "description": "Optional: direct path to CP JSON file. If not provided, opens file dialog.",
                                },
                            },
                        },
                    },
                    {
                        "name": "show_post_brief",
                        "description": "CONTROL PLANE: Shows POST-BRIEF popup manually. Use when you want to trigger the approval dialog for a generated CP.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "cp_id": {
                                    "type": "string",
                                    "description": "CP ID to show popup for",
                                },
                            },
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

    # SPRINT 8: Graph-centric CP tools
    if name == "mcp_get_next_cp":
        from control_plane.cp_queue import CPQueue

        q = CPQueue()
        next_cp = q.peek()
        if next_cp:
            return [{"type": "text", "text": json.dumps(next_cp.to_dict())}]
        return [{"type": "text", "text": json.dumps(None)}]

    if name == "mcp_approve_cp":
        cpid = arguments.get("cpid", "")
        notes = arguments.get("notes", "")
        from control_plane.cp_queue import CPQueue

        q = CPQueue()
        q.mark_approved(cpid, notes)
        return [{"type": "text", "text": json.dumps({"status": "approved", "cpid": cpid})}]

    if name == "mcp_get_graph_routing":
        intent = arguments.get("intent", "implement_feature")
        session_id = arguments.get("session_id", "default")
        from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

        cypher = get_symbol_cypher_router()
        engines = cypher.get_engine_for_intent(intent)
        if engines:
            engine = engines[0]
            return [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "engine_id": engine.engine_id,
                            "model": engine.model,
                            "endpoint": engine.endpoint,
                            "priority": engine.priority,
                        }
                    ),
                }
            ]
        return [{"type": "text", "text": json.dumps({"error": "No engines found"})}]

    # SPRINT 19: Multi-file atomic operations
    if name == "multi_file_read_context":
        files = arguments.get("files", [])
        lsp_semantic = arguments.get("lsp_semantic", True)
        workspace = WORKSPACE_BASE["workspace"]

        ctx = {}
        for filepath in files:
            full_path = filepath if filepath.startswith("/") else os.path.join(workspace, filepath)
            try:
                content = Path(full_path).read_text(encoding="utf-8", errors="ignore")
                lsp_data = {}
                if lsp_semantic:
                    try:
                        import subprocess

                        result = subprocess.run(
                            ["python3", "-m", "pyright", "--outputjson", full_path],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0:
                            import json as pyjson

                            lsp_data = pyjson.loads(result.stdout)
                        else:
                            lsp_data = {"errors": result.stderr[:500]}
                    except Exception as e:
                        lsp_data = {"lsp_error": str(e)[:200]}

                ctx[filepath] = {
                    "content": content,
                    "size": len(content),
                    "lsp": lsp_data,
                    "path": full_path,
                }
            except Exception as e:
                ctx[filepath] = {"error": str(e)[:200]}

        return [{"type": "text", "text": json.dumps(ctx, indent=2, ensure_ascii=False)}]

    if name == "multi_file_edit":
        files = arguments.get("files", [])
        patches = arguments.get("patches", {})
        create_backup = arguments.get("create_backup", True)
        workspace = WORKSPACE_BASE["workspace"]

        results = {"applied": [], "failed": [], "backups": {}}

        if create_backup:
            import shutil
            import tempfile

            backup_dir = tempfile.mkdtemp(prefix="denis_backup_")

        for filepath in files:
            full_path = filepath if filepath.startswith("/") else os.path.join(workspace, filepath)
            patch_content = patches.get(filepath, "")

            try:
                if create_backup:
                    backup_path = os.path.join(backup_dir, filepath.replace("/", "_") + ".bkp")
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(full_path, backup_path)
                    results["backups"][filepath] = backup_path

                Path(full_path).write_text(patch_content, encoding="utf-8")
                results["applied"].append(filepath)
            except Exception as e:
                results["failed"].append({"file": filepath, "error": str(e)[:200]})

        if create_backup and not results["applied"]:
            shutil.rmtree(backup_dir, ignore_errors=True)

        results["backup_dir"] = backup_dir if results["applied"] and create_backup else None

        return [{"type": "text", "text": json.dumps(results, indent=2)}]

    if name == "atomic_refactor":
        files = arguments.get("files", [])
        pattern = arguments.get("pattern", "")
        replacement = arguments.get("replacement", "")
        workspace = WORKSPACE_BASE["workspace"]

        import re

        patches = {}

        for filepath in files:
            full_path = filepath if filepath.startswith("/") else os.path.join(workspace, filepath)
            try:
                content = Path(full_path).read_text(encoding="utf-8", errors="ignore")
                new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
                patches[filepath] = new_content
            except Exception as e:
                return [
                    {
                        "type": "text",
                        "text": json.dumps({"error": f"Failed to read {filepath}: {str(e)[:200]}"}),
                    }
                ]

        results = {
            "pattern": pattern,
            "replacement": replacement,
            "files": files,
            "patches": patches,
        }

        return [{"type": "text", "text": json.dumps(results, indent=2)}]

    # Working Memory integration
    if name == "working_memory_add_file":
        filepath = arguments.get("filepath", "")
        workspace = WORKSPACE_BASE["workspace"]
        full_path = filepath if filepath.startswith("/") else os.path.join(workspace, filepath)

        try:
            content = Path(full_path).read_text(encoding="utf-8", errors="ignore")[:10000]
            sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
            from opencode_working_memory import get_working_memory

            wm = get_working_memory()
            wm.add_file(filepath, content)
            return [{"type": "text", "text": json.dumps({"status": "added", "file": filepath})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "working_memory_get_context":
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
            from opencode_working_memory import inject_context

            context = inject_context()
            return [{"type": "text", "text": context}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "working_memory_add_error":
        error_msg = arguments.get("error", "")
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
            from opencode_working_memory import get_working_memory

            wm = get_working_memory()
            wm.add_error({"message": error_msg})
            return [{"type": "text", "text": json.dumps({"status": "added"})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "working_memory_add_decision":
        decision = arguments.get("decision", "")
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
            from opencode_working_memory import get_working_memory

            wm = get_working_memory()
            wm.add_decision({"description": decision})
            return [{"type": "text", "text": json.dumps({"status": "added"})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "working_memory_clear":
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "plugins"))
            from opencode_working_memory import clear_working_memory

            clear_working_memory()
            return [{"type": "text", "text": json.dumps({"status": "cleared"})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    # CONTROL PLANE handlers
    if name == "get_next_cp":
        try:
            sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")
            from control_plane.cp_queue import get_cp_queue

            queue = get_cp_queue()
            cp = queue.peek()

            if cp:
                return [{"type": "text", "text": json.dumps(cp.to_dict(), indent=2, default=str)}]
            else:
                return [
                    {
                        "type": "text",
                        "text": json.dumps({"exists": False, "message": "No pending CPs in queue"}),
                    }
                ]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "approve_cp":
        try:
            sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")
            from control_plane.cp_queue import get_cp_queue

            cp_id = arguments.get("cp_id", "")
            notes = arguments.get("notes", "Approved via MCP")

            queue = get_cp_queue()
            success = queue.mark_approved(cp_id, notes)

            if success:
                # Escribir para que el agente lo lea
                import json

                with open("/tmp/denis_next_cp.json", "w") as f:
                    f.write(json.dumps({"cp_id": cp_id, "approved": True, "notes": notes}))

                return [
                    {"type": "text", "text": json.dumps({"status": "approved", "cp_id": cp_id})}
                ]
            else:
                return [
                    {
                        "type": "text",
                        "text": json.dumps({"error": f"CP {cp_id} not found in queue"}),
                    }
                ]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "upload_cp":
        try:
            sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")
            from control_plane.approval_popup import show_upload_cp_popup

            decision, cp = show_upload_cp_popup()

            if decision == "loaded" and cp:
                return [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"status": "loaded", "cp_id": cp.cp_id, "mission": cp.mission[:80]}
                        ),
                    }
                ]
            elif decision == "cancelled":
                return [{"type": "text", "text": json.dumps({"status": "cancelled"})}]
            else:
                return [{"type": "text", "text": json.dumps({"status": decision})}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

    if name == "show_post_brief":
        try:
            sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")
            from control_plane.cp_queue import get_cp_queue
            from control_plane.approval_popup import show_post_brief_popup

            cp_id = arguments.get("cp_id", "")
            queue = get_cp_queue()

            # Buscar CP en la cola
            cp = None
            for item in queue.list_pending():
                if item.cp_id == cp_id:
                    cp = item
                    break

            if not cp:
                return [{"type": "text", "text": json.dumps({"error": f"CP {cp_id} not found"})}]

            decision, feedback = show_post_brief_popup(cp)
            return [
                {"type": "text", "text": json.dumps({"decision": decision, "feedback": feedback})}
            ]

        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]

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
