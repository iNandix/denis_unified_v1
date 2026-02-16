#!/usr/bin/env python3
"""Denis Code CLI - AI-powered code assistant with tool execution."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from denis_unified_v1.cli.tool_schema import (
    DenisResponse,
    ToolCall,
    validate_response,
    check_tool_approval_from_graph,
)
from denis_unified_v1.cognition.legacy_tools_v2 import get_tool_registry_v2
from denis_unified_v1.inference.router import build_inference_router


def detect_workspace() -> Path:
    """Detect git workspace root safely."""
    cwd = Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).resolve()
    except Exception:
        pass
    return cwd.resolve()


def build_context(workspace: Path) -> str:
    """Build initial context from workspace safely."""
    if not workspace.exists():
        return "Workspace not found"

    context_parts = []

    # Git status
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=10,
        )
        if result.stdout.strip():
            context_parts.append(f"Git status:\n{result.stdout.strip()}")
    except Exception:
        pass

    # Key files (relative paths)
    key_files = [
        "README.md",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "Dockerfile",
    ]
    for kf in key_files:
        fp = workspace / kf
        if fp.exists() and fp.is_file():
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()[:1000]  # First 1k chars
                    context_parts.append(f"{kf}:\n{content}...")
            except Exception:
                pass

    # Directory structure (safe, relative)
    try:
        result = subprocess.run(
            [
                "find",
                ".",
                "-maxdepth",
                "2",
                "-type",
                "f",
                "(",
                "-name",
                "*.py",
                "-o",
                "-name",
                "*.js",
                "-o",
                "-name",
                "*.ts",
                "-o",
                "-name",
                "*.rs",
                "-o",
                "-name",
                "*.go",
                ")",
            ],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=10,
        )
        if result.stdout.strip():
            context_parts.append(f"Code files:\n{result.stdout.strip()}")
    except Exception:
        pass

    return "\n\n".join(context_parts)


async def query_denis(messages: List[Dict[str, str]]) -> DenisResponse:
    """Query real Denis via inference router."""
    router = build_inference_router()
    request_id = f"cli-{uuid.uuid4()}"

    try:
        result = await router.route_chat(
            messages=messages,
            request_id=request_id,
            latency_budget_ms=30000,  # 30s
        )
        response_text = result.get("response", "")
        return validate_response(response_text)
    except Exception as e:
        # Fallback to mock if fails
        print(f"Denis query failed: {e}, using mock")
        return DenisResponse(
            assistant_message="Error querying Denis, using mock...",
            tool_calls=[
                ToolCall(
                    tool="list_files",
                    args={"path": "."},
                    rationale="Ver estructura del proyecto",
                    risk_level="low",
                )
            ],
            done=False,
        )


def check_tool_approval(tool_call: ToolCall) -> bool:
    """Check approval from graph."""
    approval = check_tool_approval_from_graph(tool_call)
    if approval["approved"]:
        return True
    if approval["requires_confirmation"]:
        reason = approval.get("reason", "policy")
        response = input(f"Aprobar tool '{tool_call.tool}'? Reason: {reason} (y/N): ")
        return response.lower().startswith("y")
    return False


async def execute_tool(tool_call: ToolCall, workspace: Path) -> Dict[str, Any]:
    """Execute a tool call with security checks."""
    registry = get_tool_registry_v2()
    adapter = registry.get(tool_call.tool)
    if not adapter:
        return {"error": f"Tool {tool_call.tool} not found"}

    # Security: path under workspace for read_file
    if tool_call.tool == "read_file":
        file_path = Path(tool_call.args.get("path", ""))
        if not file_path.is_absolute():
            file_path = workspace / file_path
        file_path = file_path.resolve()
        if not file_path.is_relative_to(workspace):
            return {"error": f"Path {file_path} not under workspace {workspace}"}
        tool_call.args["path"] = str(file_path)

    # Security: command allowlist for run_command
    if tool_call.tool == "run_command":
        cmd = tool_call.args.get("cmd", "")
        allowed_prefixes = [
            "pytest -q",
            "npm test",
            "npm run test",
            "ruff",
            "black",
            "mypy",
            "git status",
            "git log",
            "git diff",
        ]
        if not any(cmd.startswith(prefix) for prefix in allowed_prefixes):
            confirm = input(f"Command '{cmd}' not in allowlist. Allow? (y/N): ")
            if confirm.lower() != "y":
                return {"error": "command blocked by policy"}

    try:
        ctx = {
            "request_id": f"cli-{tool_call.tool_call_id}",
            "confidence_band": "high",  # CLI high trust
            "internet_gate": True,
            "user_id": "cli-user",
        }
        result = await adapter.run(ctx, tool_call.args)
        return {"ok": result.ok, "data": result.data, "error": result.error}
    except Exception as e:
        return {"error": str(e)}


import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from denis_unified_v1.cli.tool_schema import (
    DenisResponse,
    ToolCall,
    validate_response,
    check_tool_approval_from_graph,
)
from denis_unified_v1.cognition.legacy_tools_v2 import get_tool_registry_v2
from denis_unified_v1.inference.router import build_inference_router


def log_audit(workspace: Path, entry: Dict[str, Any]):
    """Log to .denis/audit.jsonl"""
    audit_dir = workspace / ".denis"
    audit_dir.mkdir(exist_ok=True)
    audit_file = audit_dir / "audit.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def run_research(args):
    """Run research command using PRO_SEARCH executor."""
    import time as time_module
    from denis_unified_v1.actions.pro_search_executor import run_pro_search
    from denis_unified_v1.actions.cli_trace import cli_trace_research

    start_time = time_module.time()
    session_id = os.getenv("DENIS_SESSION_ID", f"cli-research-{uuid.uuid4().hex[:8]}")
    os.environ["DENIS_SESSION_ID"] = session_id

    cli_trace_research(
        query=args.query,
        mode=args.depth.upper(),
        sources_count=0,
    )

    result = await run_pro_search(
        query=args.query,
        mode=args.mode,
        depth=args.depth,
        category=args.category,
        session_id=session_id,
    )

    duration_ms = int((time_module.time() - start_time) * 1000)

    if args.format == "json":
        output = {
            "status": result.status,
            "answer": result.answer,
            "sources": result.sources,
            "citations": result.citations,
            "reliability_score": result.reliability_score,
            "duration_ms": duration_ms,
            "decision_trace_id": result.decision_trace_id,
            "config": {
                "mode": args.mode,
                "depth": args.depth,
                "category": args.category,
            },
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 60}")
        print(f"🔍 RESEARCH: {args.query}")
        print(f"{'=' * 60}")
        print(f"Mode: {args.mode} | Depth: {args.depth} | Category: {args.category}")
        print(
            f"Duration: {duration_ms}ms | Reliability: {result.reliability_score:.2f}"
        )
        print(f"\n{result.answer}")
        print(f"\n{'─' * 60}")
        print(f"Sources ({len(result.sources)}):")
        for i, src in enumerate(result.sources[:5], 1):
            print(f"  {i}. {src}")
        print(f"\nTrace ID: {result.decision_trace_id}")
        print(f"{'=' * 60}\n")


async def main():
    parser = argparse.ArgumentParser(description="Denis Code CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Code assistant command
    code_parser = subparsers.add_parser("code", help="Code assistance")
    code_parser.add_argument("task", help="Task description")
    code_parser.add_argument("--workspace", help="Workspace path")
    code_parser.add_argument(
        "--format", choices=["human", "json"], default="human", help="Output format"
    )

    # Research command
    research_parser = subparsers.add_parser("research", help="Web research")
    research_parser.add_argument("query", help="Research query")
    research_parser.add_argument(
        "--mode",
        choices=["user_pure", "hybrid", "machine_only"],
        default="user_pure",
        help="Search mode",
    )
    research_parser.add_argument(
        "--depth",
        choices=["quick", "standard", "deep", "continuous"],
        default="standard",
        help="Search depth",
    )
    research_parser.add_argument(
        "--category",
        choices=["general", "academic", "technical", "news", "video", "reddit"],
        default="general",
        help="Search category",
    )
    research_parser.add_argument(
        "--format", choices=["human", "json"], default="human", help="Output format"
    )

    args = parser.parse_args()

    # If no subcommand, assume code task (backwards compatibility)
    if args.command is None:
        args.command = "code"
        # Shift arguments for backwards compatibility
        if hasattr(args, "task"):
            pass  # Already has task
        else:
            # Old format: denis_code_cli.py "task description"
            args.task = parser.parse_args().task if "task" in sys.argv else None

    if args.command == "research":
        await run_research(args)
        return

    # Original code assistant logic
    task = args.task if hasattr(args, "task") else None
    if task is None:
        # Try to get task from remaining args
        task = " ".join([a for a in sys.argv[1:] if not a.startswith("-")])

    workspace = Path(args.workspace).resolve() if args.workspace else detect_workspace()
    print(f"Workspace: {workspace}")

    context = build_context(workspace)
    system_prompt = f"""
You are Denis, an AI code assistant. Respond ONLY with valid JSON matching this schema:
{{
  "assistant_message": "string - message to user",
  "tool_calls": [
    {{
      "tool": "string - tool name",
      "args": "object - tool arguments",
      "rationale": "string - why needed",
      "risk_level": "low|medium|high",
      "tool_call_id": "string - uuid"
    }}
  ],
  "done": boolean
}}

Available tools: read_file, grep_search, list_files, run_command

Context:
{context}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": args.task},
    ]

    results = []
    while True:
        try:
            response = await query_denis(messages)
        except ValueError as e:
            if args.format == "json":
                print(json.dumps({"error": str(e)}))
                sys.exit(1)
            print(f"Validation error: {e}. Re-querying Denis...")
            messages.append(
                {
                    "role": "user",
                    "content": f"Error: {e}. Please respond with valid JSON only.",
                }
            )
            continue

        if args.format == "json":
            results.append(response.model_dump())
            if response.done:
                print(json.dumps({"response": results}))
                break
            continue

        # Human format
        print(f"Denis: {response.assistant_message}")

        if response.done:
            break

        executed_any = False
        for tc in response.tool_calls:
            print(f"Tool: {tc.tool} - {tc.rationale} (risk: {tc.risk_level})")
            if not check_tool_approval(tc):
                print("Tool blocked by policy")
                log_audit(
                    workspace,
                    {
                        "tool_call_id": tc.tool_call_id,
                        "tool": tc.tool,
                        "approved": False,
                        "reason": "policy_block",
                        "timestamp": time.time(),
                    },
                )
                continue

            result = await execute_tool(tc, workspace)
            executed_any = True
            if result.get("ok"):
                print(f"Result: {result.get('data')}")
                log_audit(
                    workspace,
                    {
                        "tool_call_id": tc.tool_call_id,
                        "tool": tc.tool,
                        "approved": True,
                        "success": True,
                        "output_hash": _args_hash(result.get("data", "")),
                        "timestamp": time.time(),
                    },
                )
            else:
                print(f"Error: {result.get('error')}")
                log_audit(
                    workspace,
                    {
                        "tool_call_id": tc.tool_call_id,
                        "tool": tc.tool,
                        "approved": True,
                        "success": False,
                        "error": result.get("error"),
                        "timestamp": time.time(),
                    },
                )

        if not executed_any and response.tool_calls:
            print("No tools executed")

        messages.append(
            {"role": "assistant", "content": json.dumps(response.model_dump())}
        )

    if args.format == "human":
        print("Task complete!")


if __name__ == "__main__":
    asyncio.run(main())
